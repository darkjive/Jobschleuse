import re
import sqlite3
import sys
from datetime import UTC, datetime

import yaml

from . import db as dbmod
from .config import Config
from .llm import GenerationError, generate_slot_texts
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
            text = fetch_details(row["source_ref"])
        except Exception as exc:  # Netzfehler: mit Kurzbeschreibung weiterarbeiten
            print(f"Warnung: Details nicht abrufbar ({exc}).", file=sys.stderr)
            return row
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
    return yaml.safe_load(cfg.profile_path.read_text())


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


def set_slot(conn, app_id: int, slot: str, value: str) -> None:
    existing = conn.execute(
        "SELECT 1 FROM application_slots WHERE application_id = ? AND slot = ?",
        (app_id, slot),
    ).fetchone()
    if existing is None:
        raise ApplicationError(f"Unbekannter Slot: {slot}")
    now = _now()
    conn.execute(
        """UPDATE application_slots
           SET value = ?, source = 'manuell', updated_at = ?
           WHERE application_id = ? AND slot = ?""",
        (value, now, app_id, slot),
    )
    conn.execute("UPDATE applications SET updated_at = ? WHERE id = ?", (now, app_id))
    conn.commit()


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
