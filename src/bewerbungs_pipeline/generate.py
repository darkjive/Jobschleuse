import re
import shutil
import sys
from pathlib import Path

import yaml

from . import db as dbmod
from .config import Config
from .llm import generate_slot_texts
from .slots import extract_slots, fill_slots
from .sources.arbeitsagentur import fetch_details

MIN_DESCRIPTION_CHARS = 200


def slugify(text: str) -> str:
    normalized = (
        text.lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "firma"


def _ensure_description(conn, row) -> "dbmod.sqlite3.Row":
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


def generate_application(conn, job_id: int, cfg: Config, client) -> Path:
    row = dbmod.get_job(conn, job_id)
    if row is None:
        raise SystemExit(f"Job {job_id} nicht gefunden.")
    if row["status"] not in ("selected", "generated"):
        raise SystemExit(
            f"Job {job_id} hat Status '{row['status']}' — erst mit `jobs pick {job_id}` auswählen."
        )
    if not cfg.template_path.exists():
        raise SystemExit(f"Vorlage fehlt: {cfg.template_path}")
    if not cfg.profile_path.exists():
        raise SystemExit(
            f"Profil fehlt: {cfg.profile_path} (Muster: profile.yaml.example)"
        )

    row = _ensure_description(conn, row)
    template = cfg.template_path.read_text()
    try:
        slots = extract_slots(template)
    except ValueError as exc:
        raise SystemExit(f"Vorlage fehlerhaft: {exc}") from exc
    if not slots:
        raise SystemExit("Vorlage enthält keine data-slot-Markierungen.")
    profile = yaml.safe_load(cfg.profile_path.read_text())
    job = dbmod.row_to_item(row)

    values = generate_slot_texts(client, cfg.llm_model, job, slots, profile)
    try:
        html = fill_slots(template, values)
    except ValueError as exc:
        raise SystemExit(f"Vorlage fehlerhaft: {exc}") from exc

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

    if cfg.cbks_inbox is not None:
        if cfg.cbks_inbox.is_dir():
            shutil.copy(out_dir / "index.html", cfg.cbks_inbox / f"bewerbung-{slug}.html")
            shutil.copy(out_dir / "stelle.md", cfg.cbks_inbox / f"stelle-{slug}.md")
            if template_css.exists():
                shutil.copy(template_css, cfg.cbks_inbox / "styles.css")
            if template_assets.is_dir():
                shutil.copytree(template_assets, cfg.cbks_inbox / "assets", dirs_exist_ok=True)
        else:
            print(
                f"Warnung: CBKS-Inbox {cfg.cbks_inbox} existiert nicht — übersprungen.",
                file=sys.stderr,
            )

    dbmod.set_status(conn, job_id, "generated")
    return out_dir
