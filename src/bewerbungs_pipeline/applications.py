import re
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import db as dbmod
from . import llm, pdf
from .config import Config
from .llm import GenerationError, generate_single_slot, generate_slot_texts
from .slots import extract_slots, fill_slots
from .sources.arbeitsagentur import fetch_details

MIN_DESCRIPTION_CHARS = 200


class ApplicationError(Exception):
    """Fachlicher Fehler mit deutscher, benutzertauglicher Meldung."""


def slugify(text: str) -> str:
    normalized = (
        text.lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "firma"


def ensure_description(conn, row) -> sqlite3.Row:
    """Holt bei zu kurzer Beschreibung den Volltext von der Quelle nach."""
    too_short = len(row["description_md"]) < MIN_DESCRIPTION_CHARS
    if too_short and row["source"] == "arbeitsagentur" and row["source_ref"]:
        try:
            payload = fetch_details(row["source_ref"])
        except Exception as exc:  # Netzfehler: mit Kurzbeschreibung weiterarbeiten
            print(f"Warnung: Details nicht abrufbar ({exc}).", file=sys.stderr)
            return row
        if payload is None:
            # Anzeige ist bei der Quelle verschwunden — vermerken und mit dem
            # arbeiten, was gespeichert ist.
            dbmod.mark_gone(conn, {row["source_ref"]})
            print("Warnung: Anzeige ist bei der Quelle nicht mehr vorhanden.", file=sys.stderr)
            return dbmod.get_job(conn, row["id"])
        text = payload.get("stellenangebotsBeschreibung") or ""
        if text:
            dbmod.update_description(conn, row["id"], text)
            return dbmod.get_job(conn, row["id"])
    return row


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_profile(cfg: Config) -> dict:
    if not cfg.profile_path.exists():
        raise ApplicationError(
            f"Profil fehlt: {cfg.profile_path} (Muster: profile.yaml.example)"
        )
    profil = yaml.safe_load(cfg.profile_path.read_text())
    offen = [
        f"{feld}: {wert}"
        for feld, wert in (profil or {}).items()
        if isinstance(wert, str) and llm.PLATZHALTER_MUSTER.search(wert)
    ]
    if offen:
        raise ApplicationError(
            f"In {cfg.profile_path} stehen noch Beispielwerte: {', '.join(offen)}. "
            "Das Modell übernimmt sie wörtlich in die Bewerbung — bitte "
            "erst ausfüllen."
        )
    return profil


def _template_slots(cfg: Config) -> tuple[str, dict[str, str]]:
    if not cfg.template_path.exists():
        raise ApplicationError(f"Vorlage fehlt: {cfg.template_path}")
    template = cfg.template_path.read_text()
    try:
        slots = extract_slots(template)
    except ValueError as exc:
        raise ApplicationError(f"Vorlage fehlerhaft: {exc}") from exc
    if not slots:
        raise ApplicationError("Vorlage enthält keine data-slot-Markierungen.")
    return template, slots


def create(conn, job_id: int, cfg: Config, client) -> int:
    row = dbmod.get_job(conn, job_id)
    if row is None:
        raise ApplicationError(f"Stelle {job_id} nicht gefunden.")
    if row["status"] != "selected":
        raise ApplicationError(
            f"Stelle {job_id} hat Status '{row['status']}' — erst auswählen."
        )

    template, slots = _template_slots(cfg)
    profile = _load_profile(cfg)
    row = ensure_description(conn, row)
    job = dbmod.row_to_item(row)

    try:
        values = generate_slot_texts(client, cfg.llm_model, job, slots, profile)
    except GenerationError as exc:
        raise ApplicationError(f"Texterzeugung fehlgeschlagen: {exc}") from exc

    now = _now()
    conn.execute(
        """INSERT INTO applications (job_id, template_path, created_at, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(job_id) DO UPDATE SET
               template_path = excluded.template_path,
               updated_at = excluded.updated_at""",
        (job_id, str(cfg.template_path), now, now),
    )
    app_id = conn.execute(
        "SELECT id FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()[0]
    conn.execute("DELETE FROM application_slots WHERE application_id = ?", (app_id,))
    conn.executemany(
        """INSERT INTO application_slots (application_id, slot, value, source, updated_at)
           VALUES (?, ?, ?, 'llm', ?)""",
        [(app_id, name, values[name], now) for name in values],
    )
    conn.commit()
    return app_id


def _row_to_application(conn, row) -> dict:
    slot_rows = conn.execute(
        """SELECT slot, value, source, updated_at FROM application_slots
           WHERE application_id = ? ORDER BY slot""",
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "job_id": row["job_id"],
        "template_path": row["template_path"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "slots": {
            r["slot"]: {
                "value": r["value"],
                "source": r["source"],
                "updated_at": r["updated_at"],
            }
            for r in slot_rows
        },
    }


def get(conn, app_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    return _row_to_application(conn, row) if row else None


def get_by_job(conn, job_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()
    return _row_to_application(conn, row) if row else None


def _update_slot(conn, app_id: int, slot: str, value: str, source: str) -> None:
    now = _now()
    conn.execute(
        """UPDATE application_slots
           SET value = ?, source = ?, updated_at = ?
           WHERE application_id = ? AND slot = ?""",
        (value, source, now, app_id, slot),
    )
    conn.execute("UPDATE applications SET updated_at = ? WHERE id = ?", (now, app_id))
    conn.commit()


def set_slot(conn, app_id: int, slot: str, value: str) -> None:
    existing = conn.execute(
        "SELECT 1 FROM application_slots WHERE application_id = ? AND slot = ?",
        (app_id, slot),
    ).fetchone()
    if existing is None:
        raise ApplicationError(f"Unbekannter Slot: {slot}")
    _update_slot(conn, app_id, slot, value, "manuell")


def render(conn, app_id: int, cfg: Config) -> str:
    application = get(conn, app_id)
    if application is None:
        raise ApplicationError(f"Bewerbung {app_id} nicht gefunden.")
    template, _ = _template_slots(cfg)
    values = {name: data["value"] for name, data in application["slots"].items()}
    try:
        return fill_slots(template, values)
    except ValueError as exc:
        raise ApplicationError(f"Vorlage fehlerhaft: {exc}") from exc


_VERWEIS_RE = re.compile(r'(?:href|src)="(?!https?:|data:|#)([^"]+)"')


def _pruefe_verweise(html_datei: Path) -> None:
    """Warnt vor Verweisen ins Leere, statt sie still mitzuexportieren.

    Eine fehlende Unterschrift oder ein fehlendes Foto faellt sonst erst im
    fertigen PDF auf — dann als kaputtes Bild beim Empfaenger.
    """
    ordner = html_datei.parent
    fehlend = [
        ziel
        for ziel in _VERWEIS_RE.findall(html_datei.read_text())
        if not (ordner / ziel).exists()
    ]
    for ziel in sorted(set(fehlend)):
        print(f"Warnung: Vorlage verweist auf {ziel} — Datei fehlt.", file=sys.stderr)


def _bewerbername(cfg: Config) -> str:
    """Name aus dem Profil für den Dateinamen; Muster wie beim bisherigen PDF."""
    name = _load_profile(cfg).get("name", "").strip()
    return name or "Bewerbung"


def export(conn, app_id: int, cfg: Config) -> Path:
    application = get(conn, app_id)
    if application is None:
        raise ApplicationError(f"Bewerbung {app_id} nicht gefunden.")
    row = dbmod.get_job(conn, application["job_id"])
    html = render(conn, app_id, cfg)

    slug = slugify(row["company"])
    out_dir = cfg.out_dir / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html)
    (out_dir / "stelle.md").write_text(
        f"# {row['title']} — {row['company']}\n\n"
        f"Ort: {row['location']}\nQuelle: {row['url']}\n\n{row['description_md']}\n"
    )

    template_css = cfg.template_path.parent / "styles.css"
    template_assets = cfg.template_path.parent / "assets"
    if template_css.exists():
        shutil.copy(template_css, out_dir / "styles.css")
    if template_assets.is_dir():
        shutil.copytree(template_assets, out_dir / "assets", dirs_exist_ok=True)

    _pruefe_verweise(out_dir / "index.html")
    pdf_datei = out_dir / f"Bewerbung_{_bewerbername(cfg)}_{row['company']}.pdf"
    try:
        pdf.erzeuge(out_dir / "index.html", pdf_datei)
    except pdf.PdfError as exc:
        raise ApplicationError(str(exc)) from exc

    if cfg.cbks_inbox is not None:
        if cfg.cbks_inbox.is_dir():
            shutil.copy(out_dir / "index.html", cfg.cbks_inbox / f"bewerbung-{slug}.html")
            shutil.copy(out_dir / "stelle.md", cfg.cbks_inbox / f"stelle-{slug}.md")
            shutil.copy(pdf_datei, cfg.cbks_inbox / pdf_datei.name)
            if template_css.exists():
                shutil.copy(template_css, cfg.cbks_inbox / "styles.css")
            if template_assets.is_dir():
                shutil.copytree(
                    template_assets, cfg.cbks_inbox / "assets", dirs_exist_ok=True
                )
        else:
            print(
                f"Warnung: CBKS-Inbox {cfg.cbks_inbox} existiert nicht — übersprungen.",
                file=sys.stderr,
            )
    return out_dir


def regenerate_slot(conn, app_id: int, slot: str, cfg: Config, client) -> str:
    application = get(conn, app_id)
    if application is None:
        raise ApplicationError(f"Bewerbung {app_id} nicht gefunden.")
    if slot not in application["slots"]:
        raise ApplicationError(f"Unbekannter Slot: {slot}")

    row = dbmod.get_job(conn, application["job_id"])
    job = dbmod.row_to_item(row)
    profile = _load_profile(cfg)
    _, vorlagen_slots = _template_slots(cfg)
    beispiel = vorlagen_slots.get(slot, application["slots"][slot]["value"])
    andere = {
        name: data["value"]
        for name, data in application["slots"].items()
        if name != slot
    }

    try:
        value = generate_single_slot(
            client, cfg.llm_model, job, slot, beispiel, profile, andere
        )
    except GenerationError as exc:
        raise ApplicationError(f"Texterzeugung fehlgeschlagen: {exc}") from exc

    _update_slot(conn, app_id, slot, value, "llm")
    return value
