# Bewerbungs-App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine lokale Weboberfläche, mit der Stellen gesichtet und ausgewählt, Bewerbungen generiert, einzelne Textblöcke nachbearbeitet oder neu erzeugt und exportiert werden können — ohne Terminal.

**Architecture:** Die bestehende Pipeline bleibt unangetastet; `generate.py` wird in ein Domänenmodul `applications.py` zerlegt und behält eine dünne Fassade für das CLI. Darüber liegt eine FastAPI-App mit server-gerendertem HTML (Jinja2) und HTMX für Teil-Updates. Langlaufende LLM- und Netzaufrufe laufen in einem ThreadPoolExecutor, dessen Status per Polling abgefragt wird.

**Tech Stack:** Python 3.13, uv, SQLite, FastAPI, Uvicorn, Jinja2, HTMX, openai-SDK (gegen lokales Ollama), pytest.

**Spec:** `docs/specs/2026-08-03-bewerbungs-app-design.md`

## Global Constraints

- Sprache aller Benutzertexte, Fehlermeldungen und Commit-Messages: **Deutsch**.
- Die App bindet **ausschließlich an `127.0.0.1`**. Kein Login, keine Benutzerverwaltung.
- **Keine externen CDN-Abhängigkeiten.** HTMX und Fonts liegen lokal unter `web/static/`. Die App muss offline laufen.
- **Kein Netz und kein echtes LLM in Tests.** LLM-Aufrufe werden über einen Fake-Client gestellt (Muster: `tests/test_generate.py:16-22`).
- Fehler enden in einer deutschen Meldung, **nie in einem Traceback** (Muster: Commit `f92bb39`).
- Das Modell erfindet keine Fakten über die Firma. Die Validierung in `llm.validate_values` bleibt unverändert in Kraft.
- Das Design der generierten Bewerbung (`templates/`) wird **nicht** angefasst.
- Python 3.13, Abhängigkeiten ausschließlich über `uv add`.
- Nach jedem Task: `uv run pytest` muss vollständig grün sein.

## File Structure

**Neu:**

| Datei | Verantwortung |
|---|---|
| `src/bewerbungs_pipeline/applications.py` | Domänenlogik: Bewerbung anlegen, Slots lesen/schreiben/neu erzeugen, rendern, exportieren |
| `src/bewerbungs_pipeline/tasks.py` | Hintergrundläufe und deren Status (In-Memory) |
| `src/bewerbungs_pipeline/web/__init__.py` | leer |
| `src/bewerbungs_pipeline/web/app.py` | FastAPI-Instanz, Mounts, Startup |
| `src/bewerbungs_pipeline/web/routes/jobs.py` | Stellen: Liste, Detail, pick/reject, fetch |
| `src/bewerbungs_pipeline/web/routes/applications.py` | Bewerbung: erzeugen, redigieren, Vorschau, exportieren |
| `src/bewerbungs_pipeline/web/routes/tasks.py` | Fortschritt abfragen |
| `src/bewerbungs_pipeline/web/templates/` | Jinja2-Seiten und HTMX-Fragmente |
| `src/bewerbungs_pipeline/web/static/` | `tokens.css`, `app.css`, `htmx.min.js`, `fonts/` |
| `tests/test_applications.py` | Unit-Tests der Domänenlogik |
| `tests/test_tasks.py` | Unit-Tests der Hintergrundläufe |
| `tests/test_web_jobs.py` | Route-Tests Stellen-Screen |
| `tests/test_web_applications.py` | Route-Tests Bewerbungs-Screen |

**Geändert:**

| Datei | Änderung |
|---|---|
| `src/bewerbungs_pipeline/db.py` | Neue Tabellen, `PRAGMA foreign_keys`, `user_version`-Migration, `STATUSES` ohne `generated` |
| `src/bewerbungs_pipeline/llm.py` | Neue Funktionen für Einzel-Slot-Erzeugung |
| `src/bewerbungs_pipeline/generate.py` | Wird zur Fassade über `applications.py` |
| `src/bewerbungs_pipeline/cli.py` | Neuer Unterbefehl `serve` |
| `tests/test_generate.py` | Drei Assertions auf `applications`-Existenz umgestellt |
| `pyproject.toml` | Neue Abhängigkeiten |

---

### Task 1: Datenbank — neue Tabellen und Status-Migration

**Files:**
- Modify: `src/bewerbungs_pipeline/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `db.STATUSES == {"new", "selected", "rejected"}`
  - `db.SCHEMA_VERSION: int` (Wert `1`)
  - Tabellen `applications`, `application_slots`
  - `db.connect(db_path)` aktiviert `PRAGMA foreign_keys = ON` und migriert

- [ ] **Step 1: Write the failing tests**

An `tests/test_db.py` anhängen:

```python
def test_connect_creates_application_tables(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "applications" in tables
    assert "application_slots" in tables


def test_connect_enables_foreign_keys(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connect_migrates_generated_status_to_selected(tmp_path):
    db_path = tmp_path / "jobs.db"
    conn = db.connect(db_path)
    conn.execute(
        """INSERT INTO jobs (url, dedupe_hash, title, company, location,
                             source, scraped_at, status)
           VALUES ('u', 'h', 't', 'c', 'l', 's', '2026-01-01', 'generated')"""
    )
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    conn = db.connect(db_path)
    assert conn.execute("SELECT status FROM jobs").fetchone()[0] == "selected"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_set_status_rejects_generated(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    conn.execute(
        """INSERT INTO jobs (url, dedupe_hash, title, company, location,
                             source, scraped_at)
           VALUES ('u', 'h', 't', 'c', 'l', 's', '2026-01-01')"""
    )
    conn.commit()
    job_id = conn.execute("SELECT id FROM jobs").fetchone()[0]
    with pytest.raises(ValueError):
        db.set_status(conn, job_id, "generated")
```

Sicherstellen, dass `import pytest` oben in der Datei steht.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `applications` fehlt in `tables`, `foreign_keys` ist `0`, `AttributeError: SCHEMA_VERSION`.

- [ ] **Step 3: Implement**

In `src/bewerbungs_pipeline/db.py`, `STATUSES` ersetzen und nach `SCHEMA` einfügen:

```python
STATUSES = {"new", "selected", "rejected"}

SCHEMA_VERSION = 1

SCHEMA_APPLICATIONS = """
CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER NOT NULL REFERENCES jobs(id),
    template_path TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(job_id)
)
"""

SCHEMA_APPLICATION_SLOTS = """
CREATE TABLE IF NOT EXISTS application_slots (
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    slot           TEXT NOT NULL,
    value          TEXT NOT NULL,
    source         TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (application_id, slot)
)
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Führt Schemaschritte aus, die über CREATE TABLE hinausgehen."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        conn.execute("UPDATE jobs SET status = 'selected' WHERE status = 'generated'")
    if version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
```

`connect()` ersetzen:

```python
def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(SCHEMA)
    conn.execute(SCHEMA_APPLICATIONS)
    conn.execute(SCHEMA_APPLICATION_SLOTS)
    _migrate(conn)
    return conn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (alle, auch die bestehenden).

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/db.py tests/test_db.py
git commit -m "feat(db): Tabellen für Bewerbungen, Fremdschlüssel und Schema-Migration"
```

---

### Task 2: `applications.py` — anlegen, lesen, Slot speichern, rendern

**Files:**
- Create: `src/bewerbungs_pipeline/applications.py`
- Create: `tests/test_applications.py`
- Modify: `src/bewerbungs_pipeline/generate.py`

**Interfaces:**
- Consumes: `db.connect`, `db.get_job`, `db.row_to_item`, `db.update_description`, `slots.extract_slots`, `slots.fill_slots`, `llm.generate_slot_texts`, `sources.arbeitsagentur.fetch_details`
- Produces:
  - `class ApplicationError(Exception)`
  - `slugify(text: str) -> str`
  - `ensure_description(conn, row) -> sqlite3.Row`
  - `create(conn, job_id: int, cfg: Config, client) -> int` (gibt `application_id` zurück)
  - `get(conn, app_id: int) -> dict | None` — Form: `{"id", "job_id", "template_path", "created_at", "updated_at", "slots": {name: {"value", "source", "updated_at"}}}`
  - `get_by_job(conn, job_id: int) -> dict | None`
  - `set_slot(conn, app_id: int, slot: str, value: str) -> None`
  - `render(conn, app_id: int, cfg: Config) -> str` (fertiges HTML)

- [ ] **Step 1: Write the failing tests**

`tests/test_applications.py` anlegen:

```python
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bewerbungs_pipeline import applications, db
from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.models import JobItem

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"

GOOD = {
    "titel": "Bewerbung — Beispiel AG",
    "firma": "Beispiel AG",
    "einstieg": "Ihre Anzeige als Servicetechniker bei der Beispiel AG hat mich überzeugt.",
    "motivation": "Wartung und Service sind genau mein Feld.",
}


class FakeClient:
    def __init__(self, payload: dict):
        message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: response)
        )


def make_cfg(tmp_path, cbks_inbox=None) -> Config:
    profile = tmp_path / "profile.yaml"
    profile.write_text("name: Alain Ritter\nemail: cosmwave@gmail.com\n")
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=TEMPLATE,
        profile_path=profile,
        cbks_inbox=cbks_inbox,
        llm_base_url="http://localhost",
        llm_api_key="test",
        llm_model="test-model",
    )


def seed(cfg, status="selected") -> int:
    conn = db.connect(cfg.db_path)
    db.insert_job(
        conn,
        JobItem(
            title="Servicetechniker (m/w/d)",
            company="Beispiel AG",
            location="Frankfurt am Main",
            url="https://example.org/job/1",
            source="arbeitsagentur",
            description_md="Wir suchen Verstärkung im Service.",
            scraped_at=datetime.now(UTC),
        ),
    )
    job_id = db.list_jobs(conn)[0]["id"]
    db.set_status(conn, job_id, status)
    conn.close()
    return job_id


def test_create_stores_slots(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    application = applications.get(conn, app_id)
    assert application["job_id"] == job_id
    assert set(application["slots"]) == set(GOOD)
    assert application["slots"]["firma"]["value"] == "Beispiel AG"
    assert application["slots"]["firma"]["source"] == "llm"


def test_create_twice_replaces_existing(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    first = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    second = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    assert first == second
    rows = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    assert rows == 1


def test_create_requires_selected_status(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg, status="new")
    conn = db.connect(cfg.db_path)
    with pytest.raises(applications.ApplicationError, match="auswählen"):
        applications.create(conn, job_id, cfg, FakeClient(GOOD))


def test_create_reports_malformed_template(tmp_path):
    cfg = make_cfg(tmp_path)
    broken = tmp_path / "broken.html"
    broken.write_text('<p data-slot="x">kaputt')
    cfg = replace(cfg, template_path=broken)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    with pytest.raises(applications.ApplicationError, match="Vorlage fehlerhaft"):
        applications.create(conn, job_id, cfg, FakeClient(GOOD))


def test_set_slot_marks_source_manuell(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.set_slot(conn, app_id, "motivation", "Von Hand geschrieben.")
    slot = applications.get(conn, app_id)["slots"]["motivation"]
    assert slot["value"] == "Von Hand geschrieben."
    assert slot["source"] == "manuell"


def test_set_slot_rejects_unknown_slot(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    with pytest.raises(applications.ApplicationError, match="Unbekannter Slot"):
        applications.set_slot(conn, app_id, "gibtsnicht", "x")


def test_render_uses_current_slot_values(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.set_slot(conn, app_id, "motivation", "Neuer Text von Hand.")
    html = applications.render(conn, app_id, cfg)
    assert "Neuer Text von Hand." in html
    assert "Dieser Text ist statisch und bleibt unverändert." in html


def test_get_by_job_returns_none_without_application(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    assert applications.get_by_job(conn, job_id) is None


def test_slugify():
    assert applications.slugify("AC Motoren GmbH & Co. KG") == "ac-motoren-gmbh-co-kg"
    assert applications.slugify("Müllerößä") != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_applications.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'bewerbungs_pipeline.applications'`.

- [ ] **Step 3: Implement `applications.py`**

`src/bewerbungs_pipeline/applications.py` anlegen:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_applications.py -v`
Expected: PASS (10 Tests).

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/applications.py tests/test_applications.py
git commit -m "feat(applications): Bewerbungen anlegen, Slots speichern und rendern"
```

---

### Task 3: Export und CLI-Fassade

**Files:**
- Modify: `src/bewerbungs_pipeline/applications.py`
- Modify: `src/bewerbungs_pipeline/generate.py`
- Modify: `tests/test_generate.py:68-123`
- Test: `tests/test_applications.py`

**Interfaces:**
- Consumes: `applications.create`, `applications.render`, `applications.get`, `applications.slugify`
- Produces:
  - `applications.export(conn, app_id: int, cfg: Config) -> Path` (Ausgabeverzeichnis)
  - `generate.generate_application(conn, job_id: int, cfg: Config, client) -> Path` — unveränderte Signatur, wirft weiterhin `SystemExit` mit deutscher Meldung

- [ ] **Step 1: Write the failing tests**

An `tests/test_applications.py` anhängen:

```python
def test_export_writes_html_and_stelle(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    out_dir = applications.export(conn, app_id, cfg)
    assert "Beispiel AG" in (out_dir / "index.html").read_text()
    assert "Servicetechniker" in (out_dir / "stelle.md").read_text()


def test_export_copies_to_cbks_inbox(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    cfg = make_cfg(tmp_path, cbks_inbox=inbox)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.export(conn, app_id, cfg)
    names = {p.name for p in inbox.iterdir()}
    assert names == {"bewerbung-beispiel-ag.html", "stelle-beispiel-ag.md"}


def test_export_missing_inbox_warns_but_succeeds(tmp_path, capsys):
    cfg = make_cfg(tmp_path, cbks_inbox=tmp_path / "gibtsnicht")
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.export(conn, app_id, cfg)
    assert "CBKS-Inbox" in capsys.readouterr().err
```

In `tests/test_generate.py` die drei betroffenen Stellen ersetzen. Zuerst oben ergänzen:

```python
from bewerbungs_pipeline import applications
```

Dann Zeile 78 (`assert db.get_job(...)["status"] == "generated"`) ersetzen durch:

```python
    assert applications.get_by_job(conn, job_id) is not None
```

Ebenso Zeile 98 in `test_generate_missing_inbox_warns_but_succeeds`.

`test_generate_requires_selected_status` bleibt inhaltlich gleich — der Status `new` muss weiterhin zu `SystemExit` führen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_applications.py tests/test_generate.py -v`
Expected: FAIL — `AttributeError: module 'bewerbungs_pipeline.applications' has no attribute 'export'`.

- [ ] **Step 3: Implement**

In `applications.py` `import shutil` ergänzen und ans Dateiende anfügen:

```python
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

    if cfg.cbks_inbox is not None:
        if cfg.cbks_inbox.is_dir():
            shutil.copy(out_dir / "index.html", cfg.cbks_inbox / f"bewerbung-{slug}.html")
            shutil.copy(out_dir / "stelle.md", cfg.cbks_inbox / f"stelle-{slug}.md")
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
```

`from pathlib import Path` in den Importen ergänzen.

`src/bewerbungs_pipeline/generate.py` **vollständig ersetzen**:

```python
from pathlib import Path

from . import applications
from .applications import ApplicationError, slugify  # noqa: F401  (Re-Export fürs CLI)
from .config import Config


def generate_application(conn, job_id: int, cfg: Config, client) -> Path:
    """Fassade fürs CLI: Bewerbung erzeugen und sofort exportieren."""
    try:
        app_id = applications.create(conn, job_id, cfg, client)
        return applications.export(conn, app_id, cfg)
    except ApplicationError as exc:
        raise SystemExit(str(exc)) from exc
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS — alle Test-Module, inklusive der angepassten in `test_generate.py`.

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/applications.py src/bewerbungs_pipeline/generate.py tests/
git commit -m "refactor(generate): Export nach applications.py, generate.py wird Fassade"
```

---

### Task 4: Einzelnen Slot neu erzeugen

**Files:**
- Modify: `src/bewerbungs_pipeline/llm.py`
- Modify: `src/bewerbungs_pipeline/applications.py`
- Test: `tests/test_llm.py`, `tests/test_applications.py`

**Interfaces:**
- Consumes: `llm.build_prompt`-Muster, `applications.get`
- Produces:
  - `llm.build_single_slot_prompt(job: JobItem, slot: str, beispiel: str, profile: dict, andere: dict[str, str]) -> str`
  - `llm.generate_single_slot(client, model: str, job: JobItem, slot: str, beispiel: str, profile: dict, andere: dict[str, str]) -> str`
  - `applications.regenerate_slot(conn, app_id: int, slot: str, cfg: Config, client) -> str` (neuer Text)

**Hinweis für den Umsetzenden:** `llm.validate_values` prüft, dass der Firmenname in mindestens einem Slot vorkommt. Für einen einzelnen Slot ist diese Prüfung falsch — ein Datums- oder Anrede-Slot enthält keinen Firmennamen. Deshalb bekommt die Einzel-Slot-Erzeugung eine eigene, schwächere Validierung: Text ist ein nicht-leerer String. `validate_values` bleibt unverändert.

- [ ] **Step 1: Write the failing tests**

An `tests/test_llm.py` anhängen (`FakeClient` aus der Datei wiederverwenden; falls dort nicht vorhanden, die Variante aus `tests/test_applications.py` kopieren):

```python
def test_build_single_slot_prompt_names_slot_and_others():
    job = JobItem(
        title="Servicetechniker (m/w/d)",
        company="Beispiel AG",
        location="Frankfurt am Main",
        url="https://example.org/job/1",
        source="arbeitsagentur",
        description_md="Wir suchen Verstärkung.",
        scraped_at=datetime.now(UTC),
    )
    prompt = llm.build_single_slot_prompt(
        job, "motivation", "Beispieltext", {"name": "Alain"}, {"firma": "Beispiel AG"}
    )
    assert "motivation" in prompt
    assert "Beispieltext" in prompt
    assert "Beispiel AG" in prompt


def test_generate_single_slot_returns_text():
    job = JobItem(
        title="Servicetechniker (m/w/d)",
        company="Beispiel AG",
        location="Frankfurt am Main",
        url="https://example.org/job/1",
        source="arbeitsagentur",
        description_md="Wir suchen Verstärkung.",
        scraped_at=datetime.now(UTC),
    )
    client = FakeClient({"motivation": "Frisch formulierter Text."})
    text = llm.generate_single_slot(
        client, "test-model", job, "motivation", "alt", {"name": "Alain"}, {}
    )
    assert text == "Frisch formulierter Text."


def test_generate_single_slot_rejects_empty_answer():
    job = JobItem(
        title="Servicetechniker (m/w/d)",
        company="Beispiel AG",
        location="Frankfurt am Main",
        url="https://example.org/job/1",
        source="arbeitsagentur",
        description_md="Wir suchen Verstärkung.",
        scraped_at=datetime.now(UTC),
    )
    client = FakeClient({"motivation": "   "})
    with pytest.raises(llm.GenerationError):
        llm.generate_single_slot(
            client, "test-model", job, "motivation", "alt", {"name": "Alain"}, {}
        )
```

Nötige Importe in `tests/test_llm.py` sicherstellen: `pytest`, `datetime.UTC`, `datetime.datetime`, `JobItem`, `llm`.

An `tests/test_applications.py` anhängen:

```python
def test_regenerate_slot_replaces_value_and_marks_llm(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.set_slot(conn, app_id, "motivation", "Von Hand.")
    neu = applications.regenerate_slot(
        conn, app_id, "motivation", cfg, FakeClient({"motivation": "Neu vom Modell."})
    )
    slot = applications.get(conn, app_id)["slots"]["motivation"]
    assert neu == "Neu vom Modell."
    assert slot["value"] == "Neu vom Modell."
    assert slot["source"] == "llm"


def test_regenerate_slot_rejects_unknown_slot(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    with pytest.raises(applications.ApplicationError, match="Unbekannter Slot"):
        applications.regenerate_slot(conn, app_id, "gibtsnicht", cfg, FakeClient({}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm.py tests/test_applications.py -v`
Expected: FAIL — `AttributeError: module 'bewerbungs_pipeline.llm' has no attribute 'build_single_slot_prompt'`.

- [ ] **Step 3: Implement**

In `src/bewerbungs_pipeline/llm.py` ans Dateiende anfügen:

```python
SINGLE_SLOT_PROMPT = """Du überarbeitest EINEN Textblock einer deutschen Bewerbung.

## Stellenanzeige
Titel: {title}
Firma: {company}
Ort: {location}
Ansprechpartner: {contact_name}
Heutiges Datum: {today}

{description}

## Bewerberprofil
{profile}

## Die übrigen Textblöcke der Bewerbung (nur als Kontext, nicht ändern)
{andere}

## Zu überarbeitender Block
Name: {slot}
Bisheriger Text: {beispiel}

## Auftrag
Schreibe diesen einen Block neu — im selben Stil und in ungefähr derselben Länge,
zugeschnitten auf diese Stelle und diese Firma.

Regeln:
- Formuliere nur aus Stellenanzeige, Bewerberprofil und den vorhandenen Texten.
- Erfinde keine Fakten über die Firma, die nirgends stehen.
- Wiederhole nicht wörtlich, was in den übrigen Blöcken schon steht.
- Antworte NUR mit einem JSON-Objekt: {{"{slot}": "neuer Text"}}
  ohne weitere Erklärungen.
"""


def build_single_slot_prompt(
    job: JobItem, slot: str, beispiel: str, profile: dict, andere: dict[str, str]
) -> str:
    return SINGLE_SLOT_PROMPT.format(
        title=job.title,
        company=job.company,
        location=job.location,
        contact_name=job.contact_name or "nicht bekannt",
        today=date.today().strftime("%d.%m.%Y"),
        description=job.description_md or "(keine Beschreibung vorhanden)",
        profile=json.dumps(profile, ensure_ascii=False, indent=2),
        andere=json.dumps(andere, ensure_ascii=False, indent=2),
        slot=slot,
        beispiel=beispiel,
    )


def generate_single_slot(
    client,
    model: str,
    job: JobItem,
    slot: str,
    beispiel: str,
    profile: dict,
    andere: dict[str, str],
) -> str:
    """Erzeugt genau einen Slot-Text.

    Bewusst schwächere Validierung als validate_values: ein einzelner Block
    muss den Firmennamen nicht enthalten (z. B. ein Datums- oder Anrede-Block).
    """
    prompt = build_single_slot_prompt(job, slot, beispiel, profile, andere)
    problem = ""
    for _attempt in range(2):
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        text = response.choices[0].message.content or ""
        try:
            values = parse_response(text)
        except (json.JSONDecodeError, IndexError):
            problem = "Antwort war kein gültiges JSON"
        else:
            value = values.get(slot)
            if isinstance(value, str) and value.strip():
                return value
            problem = f"Slot '{slot}' fehlte oder war leer"
        prompt = build_single_slot_prompt(job, slot, beispiel, profile, andere) + (
            f"\n\nDein letzter Versuch hatte diesen Fehler: {problem}. Korrigiere ihn."
        )
    raise GenerationError(f"LLM-Ausgabe nach 2 Versuchen ungültig: {problem}")
```

In `applications.py` den Import erweitern und ans Dateiende anfügen:

```python
from .llm import GenerationError, generate_single_slot, generate_slot_texts
```

```python
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

    now = _now()
    conn.execute(
        """UPDATE application_slots
           SET value = ?, source = 'llm', updated_at = ?
           WHERE application_id = ? AND slot = ?""",
        (value, now, app_id, slot),
    )
    conn.execute("UPDATE applications SET updated_at = ? WHERE id = ?", (now, app_id))
    conn.commit()
    return value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/llm.py src/bewerbungs_pipeline/applications.py tests/
git commit -m "feat(applications): einzelnen Textblock neu erzeugen"
```

---

### Task 5: Hintergrundläufe

**Files:**
- Create: `src/bewerbungs_pipeline/tasks.py`
- Create: `tests/test_tasks.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `class Task` mit Feldern `id: str`, `status: str` (`"läuft"` / `"fertig"` / `"fehler"`), `meldung: str`, `ergebnis: object | None`
  - `tasks.start(beschreibung: str, fn, *args, **kwargs) -> str` (Task-ID)
  - `tasks.get(task_id: str) -> Task | None`
  - `tasks.shutdown() -> None`

**Hinweis:** IDs werden über einen Zähler vergeben, nicht über `uuid` — das macht Tests deterministisch. Der Zustand liegt im Speicher und überlebt keinen Neustart; das ist eine bewusste Entscheidung der Spec.

- [ ] **Step 1: Write the failing tests**

`tests/test_tasks.py` anlegen:

```python
import time

from bewerbungs_pipeline import tasks


def _warte_auf_ende(task_id: str, timeout: float = 5.0) -> tasks.Task:
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.01)
    raise AssertionError(f"Task {task_id} wurde nicht fertig")


def test_start_runs_function_and_stores_result():
    task_id = tasks.start("Testlauf", lambda a, b: a + b, 2, 3)
    task = _warte_auf_ende(task_id)
    assert task.status == "fertig"
    assert task.ergebnis == 5


def test_failing_function_is_reported_as_error():
    def kaputt():
        raise ValueError("etwas ging schief")

    task_id = tasks.start("Testlauf", kaputt)
    task = _warte_auf_ende(task_id)
    assert task.status == "fehler"
    assert "etwas ging schief" in task.meldung


def test_get_unknown_task_returns_none():
    assert tasks.get("gibtsnicht") is None


def test_beschreibung_is_kept():
    task_id = tasks.start("Stellen werden gesucht", lambda: None)
    _warte_auf_ende(task_id)
    assert tasks.get(task_id).beschreibung == "Stellen werden gesucht"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tasks.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'bewerbungs_pipeline.tasks'`.

- [ ] **Step 3: Implement**

`src/bewerbungs_pipeline/tasks.py` anlegen:

```python
"""Hintergrundläufe für langsame Aufrufe (LLM, Arbeitsagentur).

Bewusst minimal: der Zustand liegt im Speicher und überlebt keinen Neustart
der App. Für den Einzelbetrieb ist das ausreichend — persistente Queues wären
Infrastruktur ohne Gegenwert.
"""

import itertools
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bewerbung")
_lock = threading.Lock()
_tasks: dict[str, "Task"] = {}
_counter = itertools.count(1)


@dataclass
class Task:
    id: str
    beschreibung: str
    status: str = "läuft"          # "läuft" | "fertig" | "fehler"
    meldung: str = ""
    ergebnis: object | None = field(default=None)


def start(beschreibung: str, fn, *args, **kwargs) -> str:
    task_id = str(next(_counter))
    task = Task(id=task_id, beschreibung=beschreibung)
    with _lock:
        _tasks[task_id] = task

    def lauf() -> None:
        try:
            ergebnis = fn(*args, **kwargs)
        except Exception as exc:
            with _lock:
                task.status = "fehler"
                task.meldung = str(exc)
        else:
            with _lock:
                task.status = "fertig"
                task.ergebnis = ergebnis

    _executor.submit(lauf)
    return task_id


def get(task_id: str) -> Task | None:
    with _lock:
        return _tasks.get(task_id)


def shutdown() -> None:
    _executor.shutdown(wait=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tasks.py -v`
Expected: PASS (4 Tests).

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/tasks.py tests/test_tasks.py
git commit -m "feat(tasks): Hintergrundläufe mit Statusabfrage"
```

---

### Task 6: Web-Gerüst, Design-Assets und `serve`-Befehl

**Files:**
- Modify: `pyproject.toml`
- Create: `src/bewerbungs_pipeline/web/__init__.py`
- Create: `src/bewerbungs_pipeline/web/app.py`
- Create: `src/bewerbungs_pipeline/web/templates/basis.html`
- Create: `src/bewerbungs_pipeline/web/static/tokens.css`
- Create: `src/bewerbungs_pipeline/web/static/app.css`
- Create: `src/bewerbungs_pipeline/web/static/htmx.min.js`
- Create: `src/bewerbungs_pipeline/web/static/fonts/Satoshi-Variable.woff2`
- Modify: `src/bewerbungs_pipeline/cli.py`
- Create: `tests/test_web_app.py`

**Interfaces:**
- Consumes: `config.load_config`, `db.connect`
- Produces:
  - `web.app.create_app(cfg: Config) -> FastAPI`
  - `web.app.get_conn(request) -> sqlite3.Connection` (FastAPI-Dependency)
  - `web.app.templates` (Jinja2Templates-Instanz)
  - CLI: `jobs serve [--port PORT] [--no-browser]`

**Zwei Fallstricke, die der Umsetzende kennen muss:**

1. **SQLite und Threads.** Eine `sqlite3.Connection` darf nicht über Threads hinweg benutzt werden. Jede Request-Behandlung öffnet ihre eigene Verbindung über die Dependency; **jede Funktion, die über `tasks.start()` in einem Hintergrund-Thread läuft, muss selbst `db.connect(cfg.db_path)` aufrufen** und die Verbindung am Ende schließen. Niemals eine Verbindung in einen Task hineinreichen.
2. **Keine CDN-Referenzen.** HTMX wird als Datei abgelegt. Bezugsquelle: `https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js` — einmalig herunterladen und ins Repo legen.

- [ ] **Step 1: Abhängigkeiten installieren**

```bash
uv add fastapi uvicorn jinja2 python-multipart
uv add --dev httpx
```

Erwartete Ausgabe: `uv` schreibt die Pakete in `pyproject.toml` und aktualisiert `uv.lock`.

- [ ] **Step 2: Design-Assets aus dem Vault kopieren**

```bash
mkdir -p src/bewerbungs_pipeline/web/static/fonts
cp /home/a/Dev/vault/vendor/fonts/Satoshi-Variable.woff2 src/bewerbungs_pipeline/web/static/fonts/
cp /home/a/Dev/vault/vendor/fonts/Satoshi-VariableItalic.woff2 src/bewerbungs_pipeline/web/static/fonts/
curl -sSL https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js -o src/bewerbungs_pipeline/web/static/htmx.min.js
```

Prüfen: `ls -la src/bewerbungs_pipeline/web/static/` zeigt beide Fonts und `htmx.min.js` (~50 KB).

`src/bewerbungs_pipeline/web/static/tokens.css` anlegen — Werte wörtlich aus `/home/a/Dev/vault/src/styles/global.css` übernommen:

```css
/* Design-Tokens, übernommen aus /home/a/Dev/vault/src/styles/global.css
   (Stand 2026-08-03). Kopie, kein Import — der Vault ist ein eigenes Repo. */

@font-face {
  font-family: 'Satoshi';
  src: url('/static/fonts/Satoshi-Variable.woff2') format('woff2-variations');
  font-weight: 300 900;
  font-display: swap;
}

@font-face {
  font-family: 'Satoshi';
  src: url('/static/fonts/Satoshi-VariableItalic.woff2') format('woff2-variations');
  font-weight: 300 900;
  font-style: italic;
  font-display: swap;
}

:root {
  --font-sans: 'Satoshi', -apple-system, 'Segoe UI', Roboto, sans-serif;
  --font-mono: ui-monospace, 'JetBrains Mono', 'Cascadia Mono', Menlo, Consolas, monospace;

  --bg: #0d1017;
  --bg-sidebar: #080a0f;
  --bg-elevated: #161b22;
  --bg-hover: #1c232e;
  --bg-active: #232b38;

  --accent: #d4a574;
  --accent-bright: #e8b985;
  --accent-dim: #8a6b4d;
  --accent-glow: rgba(212, 165, 116, 0.12);
  --accent-glow-strong: rgba(212, 165, 116, 0.22);

  --text: #e6e1d8;
  --text-dim: #9a948a;
  --text-muted: #5c5852;

  --border: rgba(212, 165, 116, 0.08);
  --border-strong: rgba(212, 165, 116, 0.2);

  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 14px;

  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 14px rgba(0, 0, 0, 0.4), 0 0 1px rgba(212, 165, 116, 0.08);
  --shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.55), 0 0 2px rgba(212, 165, 116, 0.12);
  --shadow-accent: 0 0 24px rgba(212, 165, 116, 0.15);

  --z-base: 1;
  --z-sticky: 10;
  --z-sidebar: 20;
  --z-overlay: 30;
}
```

`src/bewerbungs_pipeline/web/static/app.css` anlegen:

```css
*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.55;
}

a { color: var(--accent); }

.kopf {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1.25rem;
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
}

.kopf h1 { font-size: 1rem; font-weight: 700; margin: 0; letter-spacing: 0.01em; }

.knopf {
  font: inherit;
  color: var(--text);
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  padding: 0.4rem 0.8rem;
  cursor: pointer;
}

.knopf:hover { background: var(--bg-hover); }
.knopf:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.knopf--haupt {
  background: var(--accent);
  color: #16110b;
  border-color: var(--accent-bright);
  font-weight: 600;
}

.meldung {
  padding: 0.6rem 0.9rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-strong);
  background: var(--bg-elevated);
}

.meldung--fehler { border-color: #a8524a; color: #f0c4bf; }
```

- [ ] **Step 3: Write the failing test**

`tests/test_web_app.py` anlegen:

```python
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.web.app import create_app

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"


def make_cfg(tmp_path) -> Config:
    profile = tmp_path / "profile.yaml"
    profile.write_text("name: Alain Ritter\n")
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=TEMPLATE,
        profile_path=profile,
        cbks_inbox=None,
        llm_base_url="http://localhost",
        llm_api_key="test",
        llm_model="test-model",
    )


def test_static_files_are_served(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.get("/static/tokens.css")
    assert antwort.status_code == 200
    assert "--accent" in antwort.text


def test_index_renders(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "Bewerbungen" in antwort.text
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_web_app.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'bewerbungs_pipeline.web'`.

- [ ] **Step 5: Implement**

`src/bewerbungs_pipeline/web/__init__.py` anlegen (leer).

`src/bewerbungs_pipeline/web/templates/basis.html` anlegen:

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titel %}Bewerbungen{% endblock %}</title>
  <link rel="stylesheet" href="/static/tokens.css">
  <link rel="stylesheet" href="/static/app.css">
  <script src="/static/htmx.min.js" defer></script>
</head>
<body>
  <header class="kopf">
    <h1>Bewerbungen</h1>
    {% block kopfaktionen %}{% endblock %}
  </header>
  <main>
    {% block inhalt %}{% endblock %}
  </main>
</body>
</html>
```

`src/bewerbungs_pipeline/web/app.py` anlegen:

```python
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import db
from ..config import Config

HIER = Path(__file__).parent
templates = Jinja2Templates(directory=str(HIER / "templates"))


def get_conn(request: Request):
    """Eine eigene Verbindung pro Anfrage — SQLite ist nicht thread-sicher.

    Generator-Dependency: FastAPI schließt die Verbindung nach der Antwort.
    """
    conn = db.connect(request.app.state.cfg.db_path)
    try:
        yield conn
    finally:
        conn.close()


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="Bewerbungs-App")
    app.state.cfg = cfg
    app.mount("/static", StaticFiles(directory=str(HIER / "static")), name="static")

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request, "basis.html", {})

    return app
```

In `src/bewerbungs_pipeline/cli.py` ergänzen — Funktion vor `main()`:

```python
def _cmd_serve(args: argparse.Namespace) -> int:
    import webbrowser

    import uvicorn

    from .web.app import create_app

    cfg = load_config()
    app = create_app(cfg)
    adresse = f"http://127.0.0.1:{args.port}"
    print(f"Bewerbungs-App läuft auf {adresse} — mit Strg+C beenden.")
    if not args.no_browser:
        webbrowser.open(adresse)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0
```

und in `main()` nach dem `generate`-Parser:

```python
    p_serve = sub.add_parser("serve", help="Weboberfläche starten")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--no-browser", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_web_app.py -v`
Expected: PASS (2 Tests).

- [ ] **Step 7: Von Hand prüfen**

Run: `uv run jobs serve --no-browser`
Erwartet: Meldung `Bewerbungs-App läuft auf http://127.0.0.1:8765`. Seite im Browser öffnen — dunkler Hintergrund, Satoshi-Schrift, Überschrift „Bewerbungen". Danach Strg+C.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/bewerbungs_pipeline/web src/bewerbungs_pipeline/cli.py tests/test_web_app.py
git commit -m "feat(web): FastAPI-Gerüst, Design-Tokens aus dem Vault, serve-Befehl"
```

---

### Task 7: Stellen-Screen — Liste, Filter, Detail, auswählen/aussortieren

**Files:**
- Create: `src/bewerbungs_pipeline/web/routes/__init__.py`
- Create: `src/bewerbungs_pipeline/web/routes/jobs.py`
- Create: `src/bewerbungs_pipeline/web/templates/stellen.html`
- Create: `src/bewerbungs_pipeline/web/templates/_stellenliste.html`
- Create: `src/bewerbungs_pipeline/web/templates/_stellendetail.html`
- Modify: `src/bewerbungs_pipeline/web/app.py`
- Modify: `src/bewerbungs_pipeline/db.py`
- Modify: `src/bewerbungs_pipeline/web/static/app.css`
- Create: `tests/test_web_jobs.py`

**Interfaces:**
- Consumes: `web.app.get_conn`, `web.app.templates`, `db.list_jobs`, `db.get_job`, `db.set_status`, `applications.get_by_job`
- Produces:
  - `db.suche_jobs(conn, status: str | None = None, q: str | None = None, ort: str | None = None) -> list[sqlite3.Row]`
  - Router unter `routes/jobs.py` mit `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/pick`, `POST /jobs/{id}/reject`
  - `GET /` rendert `stellen.html`

- [ ] **Step 1: Write the failing tests**

`tests/test_web_jobs.py` anlegen:

```python
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from bewerbungs_pipeline import db
from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.models import JobItem
from bewerbungs_pipeline.web.app import create_app

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"


def make_cfg(tmp_path) -> Config:
    profile = tmp_path / "profile.yaml"
    profile.write_text("name: Alain Ritter\n")
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=TEMPLATE,
        profile_path=profile,
        cbks_inbox=None,
        llm_base_url="http://localhost",
        llm_api_key="test",
        llm_model="test-model",
    )


def seed(cfg) -> dict[str, int]:
    conn = db.connect(cfg.db_path)
    for nr, (titel, firma, ort) in enumerate(
        [
            ("Frontend Entwickler (m/w/d)", "Beispiel AG", "Darmstadt"),
            ("Mechatroniker (m/w/d)", "Andere GmbH", "Frankfurt am Main"),
        ],
        start=1,
    ):
        db.insert_job(
            conn,
            JobItem(
                title=titel,
                company=firma,
                location=ort,
                url=f"https://example.org/job/{nr}",
                source="arbeitsagentur",
                description_md=f"Beschreibung für {titel}.",
                scraped_at=datetime.now(UTC),
            ),
        )
    ids = {row["title"]: row["id"] for row in db.list_jobs(conn)}
    conn.close()
    return ids


def test_liste_zeigt_alle_stellen(tmp_path):
    cfg = make_cfg(tmp_path)
    seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get("/jobs")
    assert antwort.status_code == 200
    assert "Frontend Entwickler" in antwort.text
    assert "Mechatroniker" in antwort.text


def test_liste_filtert_nach_volltext(tmp_path):
    cfg = make_cfg(tmp_path)
    seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get("/jobs", params={"q": "frontend"})
    assert "Frontend Entwickler" in antwort.text
    assert "Mechatroniker" not in antwort.text


def test_liste_filtert_nach_ort(tmp_path):
    cfg = make_cfg(tmp_path)
    seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get("/jobs", params={"ort": "Darmstadt"})
    assert "Frontend Entwickler" in antwort.text
    assert "Mechatroniker" not in antwort.text


def test_liste_filtert_nach_status(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    conn = db.connect(cfg.db_path)
    db.set_status(conn, ids["Frontend Entwickler (m/w/d)"], "selected")
    conn.close()
    client = TestClient(create_app(cfg))
    antwort = client.get("/jobs", params={"status": "selected"})
    assert "Frontend Entwickler" in antwort.text
    assert "Mechatroniker" not in antwort.text


def test_detail_zeigt_beschreibung(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/jobs/{ids['Frontend Entwickler (m/w/d)']}")
    assert "Beschreibung für Frontend Entwickler" in antwort.text


def test_detail_unbekannte_stelle_meldet_deutsch(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/jobs/999")
    assert antwort.status_code == 404
    assert "nicht gefunden" in antwort.text


def test_pick_setzt_status(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    job_id = ids["Frontend Entwickler (m/w/d)"]
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/jobs/{job_id}/pick")
    assert antwort.status_code == 200
    conn = db.connect(cfg.db_path)
    assert db.get_job(conn, job_id)["status"] == "selected"


def test_reject_setzt_status(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    job_id = ids["Mechatroniker (m/w/d)"]
    client = TestClient(create_app(cfg))
    client.post(f"/jobs/{job_id}/reject")
    conn = db.connect(cfg.db_path)
    assert db.get_job(conn, job_id)["status"] == "rejected"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_web_jobs.py -v`
Expected: FAIL — alle Anfragen liefern 404, weil die Routen fehlen.

- [ ] **Step 3: Suchfunktion in `db.py` ergänzen**

Ans Ende von `src/bewerbungs_pipeline/db.py`:

```python
def suche_jobs(
    conn: sqlite3.Connection,
    status: str | None = None,
    q: str | None = None,
    ort: str | None = None,
) -> list[sqlite3.Row]:
    """Stellenliste mit optionalen Filtern.

    `q` sucht in Titel und Firma, `ort` im Ort — beides ohne
    Beachtung der Groß-/Kleinschreibung.
    """
    sql = "SELECT * FROM jobs WHERE 1=1"
    werte: list[str] = []
    if status:
        sql += " AND status = ?"
        werte.append(status)
    if q:
        sql += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"
        werte.extend([f"%{q.lower()}%"] * 2)
    if ort:
        sql += " AND LOWER(location) LIKE ?"
        werte.append(f"%{ort.lower()}%")
    sql += " ORDER BY id DESC"
    return conn.execute(sql, werte).fetchall()
```

- [ ] **Step 4: Templates anlegen**

`src/bewerbungs_pipeline/web/templates/stellen.html`:

```html
{% extends "basis.html" %}

{% block inhalt %}
<div class="spalten">
  <aside class="filter">
    <form hx-get="/jobs" hx-target="#stellenliste" hx-trigger="submit, change delay:300ms">
      <label>Status
        <select name="status">
          <option value="">alle</option>
          <option value="new" selected>neu</option>
          <option value="selected">ausgewählt</option>
          <option value="rejected">aussortiert</option>
        </select>
      </label>
      <label>Suche
        <input type="search" name="q" placeholder="Titel oder Firma">
      </label>
      <label>Ort
        <input type="search" name="ort" placeholder="z. B. Darmstadt">
      </label>
    </form>
  </aside>

  <section id="stellenliste" hx-get="/jobs?status=new" hx-trigger="load">
    <p class="meldung">Liste wird geladen …</p>
  </section>

  <section id="stellendetail" class="detail">
    <p class="meldung">Wähle links eine Stelle aus.</p>
  </section>
</div>
{% endblock %}
```

`src/bewerbungs_pipeline/web/templates/_stellenliste.html`:

```html
{% if not stellen %}
  <p class="meldung">Keine Stellen gefunden.</p>
{% else %}
  <ul class="stellen">
    {% for stelle in stellen %}
      <li class="stelle" id="stelle-{{ stelle.id }}">
        <button class="stelle__titel" hx-get="/jobs/{{ stelle.id }}"
                hx-target="#stellendetail">
          {{ stelle.title }}
        </button>
        <span class="stelle__meta">{{ stelle.company }} · {{ stelle.location }}</span>
        <span class="stelle__status stelle__status--{{ stelle.status }}">
          {{ stelle.status }}
        </span>
      </li>
    {% endfor %}
  </ul>
{% endif %}
```

`src/bewerbungs_pipeline/web/templates/_stellendetail.html`:

```html
<article class="detail__inhalt">
  <h2>{{ stelle.title }}</h2>
  <p class="stelle__meta">{{ stelle.company }} · {{ stelle.location }}</p>
  <p><a href="{{ stelle.url }}" target="_blank" rel="noreferrer">Anzeige bei der Quelle</a></p>

  <div class="detail__aktionen">
    <button class="knopf" hx-post="/jobs/{{ stelle.id }}/pick"
            hx-target="#stellendetail">Auswählen</button>
    <button class="knopf" hx-post="/jobs/{{ stelle.id }}/reject"
            hx-target="#stellendetail">Aussortieren</button>
  </div>

  <pre class="detail__text">{{ stelle.description_md }}</pre>
</article>
```

- [ ] **Step 5: Router implementieren**

`src/bewerbungs_pipeline/web/routes/__init__.py` anlegen (leer).

`src/bewerbungs_pipeline/web/routes/jobs.py` anlegen:

```python
import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ... import db
from ..app import get_conn, templates

router = APIRouter()


def _detail(request: Request, conn: sqlite3.Connection, job_id: int) -> HTMLResponse:
    stelle = db.get_job(conn, job_id)
    if stelle is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Stelle nicht gefunden.</p>',
            status_code=404,
        )
    return templates.TemplateResponse(
        request, "_stellendetail.html", {"stelle": stelle}
    )


@router.get("/jobs", response_class=HTMLResponse)
def liste(
    request: Request,
    status: str = "",
    q: str = "",
    ort: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
):
    stellen = db.suche_jobs(conn, status=status or None, q=q or None, ort=ort or None)
    return templates.TemplateResponse(
        request, "_stellenliste.html", {"stellen": stellen}
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def detail(
    request: Request, job_id: int, conn: sqlite3.Connection = Depends(get_conn)
):
    return _detail(request, conn, job_id)


@router.post("/jobs/{job_id}/pick", response_class=HTMLResponse)
def pick(
    request: Request, job_id: int, conn: sqlite3.Connection = Depends(get_conn)
):
    if db.get_job(conn, job_id) is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Stelle nicht gefunden.</p>',
            status_code=404,
        )
    db.set_status(conn, job_id, "selected")
    return _detail(request, conn, job_id)


@router.post("/jobs/{job_id}/reject", response_class=HTMLResponse)
def reject(
    request: Request, job_id: int, conn: sqlite3.Connection = Depends(get_conn)
):
    if db.get_job(conn, job_id) is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Stelle nicht gefunden.</p>',
            status_code=404,
        )
    db.set_status(conn, job_id, "rejected")
    return _detail(request, conn, job_id)
```

In `src/bewerbungs_pipeline/web/app.py` die `index`-Route ersetzen und den Router einhängen:

```python
def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="Bewerbungs-App")
    app.state.cfg = cfg
    app.mount("/static", StaticFiles(directory=str(HIER / "static")), name="static")

    from .routes import jobs as jobs_routen

    app.include_router(jobs_routen.router)

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request, "stellen.html", {})

    return app
```

- [ ] **Step 6: CSS für das Drei-Spalten-Layout ergänzen**

An `src/bewerbungs_pipeline/web/static/app.css` anhängen:

```css
.spalten {
  display: grid;
  grid-template-columns: 15rem minmax(20rem, 1fr) minmax(20rem, 1.2fr);
  gap: 1px;
  background: var(--border);
  height: calc(100vh - 3.25rem);
}

.spalten > * { background: var(--bg); overflow-y: auto; padding: 1rem; }

.filter { background: var(--bg-sidebar); }
.filter label { display: block; margin-bottom: 0.9rem; font-size: 0.85rem; color: var(--text-dim); }
.filter input, .filter select {
  display: block;
  width: 100%;
  margin-top: 0.3rem;
  font: inherit;
  color: var(--text);
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0.35rem 0.5rem;
}

.stellen { list-style: none; margin: 0; padding: 0; }

.stelle {
  display: grid;
  gap: 0.15rem;
  padding: 0.6rem 0.7rem;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
}

.stelle:hover { background: var(--bg-hover); border-color: var(--border); }

.stelle__titel {
  font: inherit;
  font-weight: 600;
  text-align: left;
  color: var(--text);
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
}

.stelle__titel:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.stelle__meta { font-size: 0.82rem; color: var(--text-dim); }

.stelle__status {
  justify-self: start;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.stelle__status--selected { color: var(--accent); }

.detail__aktionen { display: flex; gap: 0.5rem; margin: 1rem 0; }

.detail__text {
  white-space: pre-wrap;
  font-family: var(--font-sans);
  font-size: 0.9rem;
  color: var(--text-dim);
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_web_jobs.py -v`
Expected: PASS (8 Tests).

- [ ] **Step 8: Commit**

```bash
git add src/bewerbungs_pipeline/web src/bewerbungs_pipeline/db.py tests/test_web_jobs.py
git commit -m "feat(web): Stellen-Screen mit Filter, Detail und Auswahl"
```

---

### Task 8: Suche starten und Fortschritt anzeigen

**Files:**
- Create: `src/bewerbungs_pipeline/web/routes/tasks.py`
- Create: `src/bewerbungs_pipeline/web/templates/_fortschritt.html`
- Modify: `src/bewerbungs_pipeline/web/routes/jobs.py`
- Modify: `src/bewerbungs_pipeline/web/templates/stellen.html`
- Modify: `src/bewerbungs_pipeline/web/app.py`
- Test: `tests/test_web_jobs.py`

**Interfaces:**
- Consumes: `tasks.start`, `tasks.get`, `sources.arbeitsagentur.fetch_jobs`, `db.insert_job`
- Produces:
  - `POST /jobs/fetch` (Formularfelder `was`, `wo`, `umkreis`) → Fortschritts-Fragment
  - `GET /tasks/{task_id}` → Fortschritts-Fragment
  - `web.routes.jobs.suche_ausfuehren(cfg, was: str, wo: str, umkreis: int) -> str` (Ergebnismeldung)

**Wichtig:** `suche_ausfuehren` läuft im Hintergrund-Thread und öffnet deshalb **selbst** eine DB-Verbindung.

- [ ] **Step 1: Write the failing tests**

An `tests/test_web_jobs.py` anhängen:

```python
def test_suche_ausfuehren_schreibt_stellen(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import jobs as jobs_routen

    cfg = make_cfg(tmp_path)
    db.connect(cfg.db_path).close()

    def fake_fetch(was, wo, umkreis=25, max_pages=5):
        return [
            JobItem(
                title="Neue Stelle (m/w/d)",
                company="Frisch GmbH",
                location="Mainz",
                url="https://example.org/job/neu",
                source="arbeitsagentur",
                description_md="Text.",
                scraped_at=datetime.now(UTC),
            )
        ]

    monkeypatch.setattr(jobs_routen.arbeitsagentur, "fetch_jobs", fake_fetch)
    meldung = jobs_routen.suche_ausfuehren(cfg, "Entwickler", "Mainz", 25)

    assert "1" in meldung
    conn = db.connect(cfg.db_path)
    assert any(r["title"] == "Neue Stelle (m/w/d)" for r in db.list_jobs(conn))


def test_fetch_liefert_fortschritt_mit_task_id(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import jobs as jobs_routen

    cfg = make_cfg(tmp_path)
    monkeypatch.setattr(
        jobs_routen.arbeitsagentur, "fetch_jobs", lambda **kw: []
    )
    client = TestClient(create_app(cfg))
    antwort = client.post(
        "/jobs/fetch", data={"was": "Entwickler", "wo": "Mainz", "umkreis": "25"}
    )
    assert antwort.status_code == 200
    assert "/tasks/" in antwort.text


def test_task_status_unbekannt_meldet_deutsch(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/tasks/gibtsnicht")
    assert antwort.status_code == 404
    assert "nicht gefunden" in antwort.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_web_jobs.py -k "suche or fetch or task" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'arbeitsagentur'` bzw. 404 auf `/jobs/fetch`.

- [ ] **Step 3: Fortschritts-Fragment anlegen**

`src/bewerbungs_pipeline/web/templates/_fortschritt.html`:

```html
{% if task.status == "läuft" %}
  <p class="meldung"
     hx-get="/tasks/{{ task.id }}?ziel={{ ziel|urlencode }}&ziel_element={{ ziel_element|urlencode }}"
     hx-trigger="load delay:1s" hx-swap="outerHTML">
    {{ task.beschreibung }} … läuft
  </p>
{% elif task.status == "fehler" %}
  <p class="meldung meldung--fehler">{{ task.beschreibung }}: {{ task.meldung }}</p>
{% else %}
  <p class="meldung" {% if ziel %}hx-get="{{ ziel }}" hx-target="{{ ziel_element }}"
     hx-trigger="load"{% endif %}>
    {{ task.ergebnis or "Fertig." }}
  </p>
{% endif %}
```

- [ ] **Step 4: Routen implementieren**

In `src/bewerbungs_pipeline/web/routes/jobs.py` die Importe erweitern:

```python
from fastapi import APIRouter, Depends, Form, Request

from ... import db, tasks
from ...config import Config
from ...sources import arbeitsagentur
```

und ans Dateiende anfügen:

```python
def suche_ausfuehren(cfg: Config, was: str, wo: str, umkreis: int) -> str:
    """Läuft im Hintergrund-Thread — öffnet deshalb eine eigene Verbindung."""
    items = arbeitsagentur.fetch_jobs(was=was, wo=wo, umkreis=umkreis)
    conn = db.connect(cfg.db_path)
    try:
        neu = sum(1 for item in items if db.insert_job(conn, item))
    finally:
        conn.close()
    return f"{len(items)} Stellen geholt, {neu} neu."


@router.post("/jobs/fetch", response_class=HTMLResponse)
def fetch(
    request: Request,
    was: str = Form(...),
    wo: str = Form(...),
    umkreis: int = Form(25),
):
    cfg = request.app.state.cfg
    task_id = tasks.start(
        f"Suche „{was}“ in {wo}", suche_ausfuehren, cfg, was, wo, umkreis
    )
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {
            "task": tasks.get(task_id),
            "ziel": "/jobs?status=new",
            "ziel_element": "#stellenliste",
        },
    )
```

`src/bewerbungs_pipeline/web/routes/tasks.py` anlegen:

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ... import tasks as tasks_modul
from ..app import templates

router = APIRouter()


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def status(request: Request, task_id: str, ziel: str = "", ziel_element: str = ""):
    task = tasks_modul.get(task_id)
    if task is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Vorgang nicht gefunden.</p>',
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {"task": task, "ziel": ziel, "ziel_element": ziel_element},
    )
```

In `web/app.py` den zweiten Router einhängen:

```python
    from .routes import jobs as jobs_routen
    from .routes import tasks as tasks_routen

    app.include_router(jobs_routen.router)
    app.include_router(tasks_routen.router)
```

- [ ] **Step 5: Suchformular in `stellen.html` ergänzen**

Im Block `kopfaktionen` von `stellen.html` einfügen (Block neu anlegen, direkt nach `{% block inhalt %}` … davor):

```html
{% block kopfaktionen %}
<form class="suchform" hx-post="/jobs/fetch" hx-target="#fortschritt">
  <input type="search" name="was" placeholder="Was, z. B. Frontend Entwickler" required>
  <input type="search" name="wo" placeholder="Wo, z. B. Darmstadt" required>
  <input type="number" name="umkreis" value="50" min="0" max="200" aria-label="Umkreis in km">
  <button class="knopf knopf--haupt" type="submit">Stellen suchen</button>
</form>
<div id="fortschritt"></div>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_web_jobs.py -v`
Expected: PASS (11 Tests).

- [ ] **Step 7: Commit**

```bash
git add src/bewerbungs_pipeline/web tests/test_web_jobs.py
git commit -m "feat(web): Stellensuche als Hintergrundlauf mit Fortschrittsanzeige"
```

---

### Task 9: Bewerbungs-Screen — erzeugen, redigieren, Vorschau, exportieren

**Files:**
- Create: `src/bewerbungs_pipeline/web/routes/applications.py`
- Create: `src/bewerbungs_pipeline/web/templates/bewerbung.html`
- Create: `src/bewerbungs_pipeline/web/templates/_slot.html`
- Modify: `src/bewerbungs_pipeline/web/templates/_stellendetail.html`
- Modify: `src/bewerbungs_pipeline/web/app.py`
- Modify: `src/bewerbungs_pipeline/web/static/app.css`
- Create: `tests/test_web_applications.py`

**Interfaces:**
- Consumes: `applications.create`, `applications.get`, `applications.get_by_job`, `applications.set_slot`, `applications.regenerate_slot`, `applications.render`, `applications.export`, `applications.ApplicationError`, `tasks.start`, `llm.make_client`
- Produces:
  - `POST /applications` (Formularfeld `job_id`) → Fortschritts-Fragment
  - `GET /bewerbung/{app_id}` → volle Seite
  - `PUT /applications/{app_id}/slots/{slot}` (Formularfeld `value`) → Slot-Fragment
  - `POST /applications/{app_id}/slots/{slot}/regenerate` → Fortschritts-Fragment
  - `GET /applications/{app_id}/preview` → gerendertes Bewerbungs-HTML
  - `POST /applications/{app_id}/export` → Meldungs-Fragment
  - `web.routes.applications.bewerbung_erzeugen(cfg, job_id: int) -> int`
  - `web.routes.applications.slot_erzeugen(cfg, app_id: int, slot: str) -> str`

**Wichtig:** `bewerbung_erzeugen` und `slot_erzeugen` laufen im Hintergrund-Thread und öffnen **je eine eigene** DB-Verbindung sowie einen eigenen LLM-Client.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_applications.py` anlegen:

```python
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from bewerbungs_pipeline import applications, db
from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.models import JobItem
from bewerbungs_pipeline.web.app import create_app

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"

GOOD = {
    "titel": "Bewerbung — Beispiel AG",
    "firma": "Beispiel AG",
    "einstieg": "Ihre Anzeige hat mich überzeugt.",
    "motivation": "Wartung und Service sind mein Feld.",
}


class FakeClient:
    def __init__(self, payload: dict):
        message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: response)
        )


def make_cfg(tmp_path) -> Config:
    profile = tmp_path / "profile.yaml"
    profile.write_text("name: Alain Ritter\n")
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=TEMPLATE,
        profile_path=profile,
        cbks_inbox=None,
        llm_base_url="http://localhost",
        llm_api_key="test",
        llm_model="test-model",
    )


def seed(cfg) -> int:
    conn = db.connect(cfg.db_path)
    db.insert_job(
        conn,
        JobItem(
            title="Servicetechniker (m/w/d)",
            company="Beispiel AG",
            location="Frankfurt am Main",
            url="https://example.org/job/1",
            source="arbeitsagentur",
            description_md="Wir suchen Verstärkung im Service.",
            scraped_at=datetime.now(UTC),
        ),
    )
    job_id = db.list_jobs(conn)[0]["id"]
    db.set_status(conn, job_id, "selected")
    conn.close()
    return job_id


def bewerbung_anlegen(cfg, job_id) -> int:
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    conn.close()
    return app_id


def test_bewerbung_erzeugen_legt_datensatz_an(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import applications as app_routen

    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    monkeypatch.setattr(app_routen, "make_client", lambda *a, **k: FakeClient(GOOD))
    app_id = app_routen.bewerbung_erzeugen(cfg, job_id)
    conn = db.connect(cfg.db_path)
    assert applications.get(conn, app_id) is not None


def test_bewerbungsseite_zeigt_slots(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/bewerbung/{app_id}")
    assert antwort.status_code == 200
    assert "motivation" in antwort.text
    assert "Wartung und Service sind mein Feld." in antwort.text


def test_bewerbungsseite_unbekannt_meldet_deutsch(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/bewerbung/999")
    assert antwort.status_code == 404
    assert "nicht gefunden" in antwort.text


def test_slot_speichern(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(
        f"/applications/{app_id}/slots/motivation", data={"value": "Neu von Hand."}
    )
    assert antwort.status_code == 200
    conn = db.connect(cfg.db_path)
    slot = applications.get(conn, app_id)["slots"]["motivation"]
    assert slot["value"] == "Neu von Hand."
    assert slot["source"] == "manuell"


def test_slot_speichern_unbekannt_meldet_deutsch(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(
        f"/applications/{app_id}/slots/gibtsnicht", data={"value": "x"}
    )
    assert antwort.status_code == 400
    assert "Unbekannter Slot" in antwort.text


def test_vorschau_liefert_gefuelltes_html(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/applications/{app_id}/preview")
    assert antwort.status_code == 200
    assert "Beispiel AG" in antwort.text
    assert "Dieser Text ist statisch und bleibt unverändert." in antwort.text


def test_export_schreibt_dateien(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/applications/{app_id}/export")
    assert antwort.status_code == 200
    assert (cfg.out_dir / "beispiel-ag" / "index.html").exists()


def test_slot_erzeugen_setzt_neuen_text(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import applications as app_routen

    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    monkeypatch.setattr(
        app_routen,
        "make_client",
        lambda *a, **k: FakeClient({"motivation": "Frisch erzeugt."}),
    )
    text = app_routen.slot_erzeugen(cfg, app_id, "motivation")
    assert text == "Frisch erzeugt."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_web_applications.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bewerbungs_pipeline.web.routes.applications'`.

- [ ] **Step 3: Templates anlegen**

`src/bewerbungs_pipeline/web/templates/_slot.html`:

```html
<li class="slot" id="slot-{{ name }}">
  <div class="slot__kopf">
    <label for="feld-{{ name }}"><code>{{ name }}</code></label>
    <span class="slot__quelle slot__quelle--{{ daten.source }}">
      {% if daten.source == "llm" %}vom Modell{% else %}von Hand{% endif %}
    </span>
    <button class="knopf" hx-post="/applications/{{ app_id }}/slots/{{ name }}/regenerate"
            hx-target="#fortschritt-{{ name }}">Neu erzeugen</button>
  </div>
  <form hx-put="/applications/{{ app_id }}/slots/{{ name }}"
        hx-target="#slot-{{ name }}" hx-swap="outerHTML">
    <textarea id="feld-{{ name }}" name="value" rows="4">{{ daten.value }}</textarea>
    <button class="knopf" type="submit">Speichern</button>
  </form>
  <div id="fortschritt-{{ name }}"></div>
</li>
```

`src/bewerbungs_pipeline/web/templates/bewerbung.html`:

```html
{% extends "basis.html" %}

{% block titel %}Bewerbung — {{ stelle.company }}{% endblock %}

{% block kopfaktionen %}
<a class="knopf" href="/">Zurück zu den Stellen</a>
<button class="knopf knopf--haupt" hx-post="/applications/{{ bewerbung.id }}/export"
        hx-target="#exportmeldung">Exportieren</button>
<div id="exportmeldung"></div>
{% endblock %}

{% block inhalt %}
<div class="bewerbung">
  <section class="bewerbung__editor">
    <h2>{{ stelle.title }} — {{ stelle.company }}</h2>
    <ul class="slots">
      {% for name, daten in bewerbung.slots.items() %}
        {% include "_slot.html" %}
      {% endfor %}
    </ul>
  </section>

  <section class="bewerbung__vorschau">
    <iframe id="vorschau" title="Vorschau der Bewerbung"
            src="/applications/{{ bewerbung.id }}/preview"></iframe>
  </section>
</div>
{% endblock %}
```

**Hinweis:** `{% include %}` erbt den Schleifenkontext, `name` und `daten` sind darin verfügbar; `app_id` wird als eigene Variable an die Seite übergeben.

In `_stellendetail.html` den Aktionsblock erweitern:

```html
  <div class="detail__aktionen">
    <button class="knopf" hx-post="/jobs/{{ stelle.id }}/pick"
            hx-target="#stellendetail">Auswählen</button>
    <button class="knopf" hx-post="/jobs/{{ stelle.id }}/reject"
            hx-target="#stellendetail">Aussortieren</button>
    {% if bewerbung %}
      <a class="knopf knopf--haupt" href="/bewerbung/{{ bewerbung.id }}">Bewerbung öffnen</a>
    {% elif stelle.status == "selected" %}
      <form hx-post="/applications" hx-target="#bewerbungsfortschritt">
        <input type="hidden" name="job_id" value="{{ stelle.id }}">
        <button class="knopf knopf--haupt" type="submit">Bewerbung erstellen</button>
      </form>
    {% endif %}
  </div>
  <div id="bewerbungsfortschritt"></div>
```

In `routes/jobs.py` muss `_detail` die Bewerbung mitgeben:

```python
def _detail(request: Request, conn: sqlite3.Connection, job_id: int) -> HTMLResponse:
    stelle = db.get_job(conn, job_id)
    if stelle is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Stelle nicht gefunden.</p>',
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "_stellendetail.html",
        {"stelle": stelle, "bewerbung": applications.get_by_job(conn, job_id)},
    )
```

Dafür in `routes/jobs.py` ergänzen: `from ... import applications`.

- [ ] **Step 4: Router implementieren**

`src/bewerbungs_pipeline/web/routes/applications.py` anlegen:

```python
import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from ... import applications, db, tasks
from ...applications import ApplicationError
from ...config import Config
from ...llm import make_client
from ..app import get_conn, templates

router = APIRouter()


def _client(cfg: Config):
    if not (cfg.llm_base_url and cfg.llm_api_key and cfg.llm_model):
        raise ApplicationError("LLM_BASE_URL, LLM_API_KEY und LLM_MODEL in .env setzen.")
    return make_client(cfg.llm_base_url, cfg.llm_api_key)


def bewerbung_erzeugen(cfg: Config, job_id: int) -> int:
    """Hintergrund-Thread: eigene Verbindung, eigener Client."""
    conn = db.connect(cfg.db_path)
    try:
        return applications.create(conn, job_id, cfg, _client(cfg))
    finally:
        conn.close()


def slot_erzeugen(cfg: Config, app_id: int, slot: str) -> str:
    """Hintergrund-Thread: eigene Verbindung, eigener Client."""
    conn = db.connect(cfg.db_path)
    try:
        return applications.regenerate_slot(conn, app_id, slot, cfg, _client(cfg))
    finally:
        conn.close()


@router.post("/applications", response_class=HTMLResponse)
def erzeugen(request: Request, job_id: int = Form(...)):
    cfg = request.app.state.cfg
    task_id = tasks.start("Bewerbung wird geschrieben", bewerbung_erzeugen, cfg, job_id)
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {"task": tasks.get(task_id), "ziel": "", "ziel_element": ""},
    )


@router.get("/bewerbung/{app_id}", response_class=HTMLResponse)
def seite(request: Request, app_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    bewerbung = applications.get(conn, app_id)
    if bewerbung is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Bewerbung nicht gefunden.</p>',
            status_code=404,
        )
    stelle = db.get_job(conn, bewerbung["job_id"])
    return templates.TemplateResponse(
        request,
        "bewerbung.html",
        {"bewerbung": bewerbung, "stelle": stelle, "app_id": app_id},
    )


@router.put("/applications/{app_id}/slots/{slot}", response_class=HTMLResponse)
def slot_speichern(
    request: Request,
    app_id: int,
    slot: str,
    value: str = Form(...),
    conn: sqlite3.Connection = Depends(get_conn),
):
    try:
        applications.set_slot(conn, app_id, slot, value)
    except ApplicationError as exc:
        return HTMLResponse(
            f'<p class="meldung meldung--fehler">{exc}</p>', status_code=400
        )
    daten = applications.get(conn, app_id)["slots"][slot]
    return templates.TemplateResponse(
        request, "_slot.html", {"name": slot, "daten": daten, "app_id": app_id}
    )


@router.post(
    "/applications/{app_id}/slots/{slot}/regenerate", response_class=HTMLResponse
)
def slot_neu(request: Request, app_id: int, slot: str):
    cfg = request.app.state.cfg
    task_id = tasks.start(
        f"Block „{slot}“ wird neu geschrieben", slot_erzeugen, cfg, app_id, slot
    )
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {"task": tasks.get(task_id), "ziel": "", "ziel_element": ""},
    )


@router.get("/applications/{app_id}/preview", response_class=HTMLResponse)
def vorschau(request: Request, app_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    cfg = request.app.state.cfg
    try:
        html = applications.render(conn, app_id, cfg)
    except ApplicationError as exc:
        return HTMLResponse(
            f'<p class="meldung meldung--fehler">{exc}</p>', status_code=400
        )
    return HTMLResponse(html)


@router.post("/applications/{app_id}/export", response_class=HTMLResponse)
def exportieren(app_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    cfg = request.app.state.cfg
    try:
        ziel = applications.export(conn, app_id, cfg)
    except ApplicationError as exc:
        return HTMLResponse(
            f'<p class="meldung meldung--fehler">{exc}</p>', status_code=400
        )
    return HTMLResponse(f'<p class="meldung">Exportiert nach {ziel}</p>')
```

In `web/app.py` den dritten Router einhängen:

```python
    from .routes import applications as bewerbungs_routen

    app.include_router(bewerbungs_routen.router)
```

- [ ] **Step 5: CSS ergänzen**

An `app.css` anhängen:

```css
.bewerbung {
  display: grid;
  grid-template-columns: minmax(22rem, 1fr) minmax(24rem, 1.1fr);
  gap: 1px;
  background: var(--border);
  height: calc(100vh - 3.25rem);
}

.bewerbung > * { background: var(--bg); overflow-y: auto; padding: 1.25rem; }

.slots { list-style: none; margin: 0; padding: 0; display: grid; gap: 1.25rem; }

.slot {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 0.9rem;
  background: var(--bg-elevated);
}

.slot__kopf { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.5rem; }
.slot__kopf label { font-family: var(--font-mono); font-size: 0.8rem; }
.slot__kopf .knopf { margin-left: auto; }

.slot__quelle { font-size: 0.72rem; color: var(--text-muted); }
.slot__quelle--llm { color: var(--accent-dim); }

.slot textarea {
  width: 100%;
  font: inherit;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  padding: 0.5rem 0.6rem;
  resize: vertical;
}

.slot textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

.bewerbung__vorschau { padding: 0; }

#vorschau { width: 100%; height: 100%; border: 0; background: #fff; }

.suchform { display: flex; gap: 0.4rem; margin-left: auto; }
.suchform input {
  font: inherit;
  color: var(--text);
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0.3rem 0.5rem;
}
.suchform input[name="umkreis"] { width: 5rem; }
```

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -v`
Expected: PASS — alle Module.

- [ ] **Step 7: Commit**

```bash
git add src/bewerbungs_pipeline/web tests/test_web_applications.py
git commit -m "feat(web): Bewerbungs-Screen mit Editor, Vorschau und Export"
```

---

### Task 10: Vorlagen-Assets in der Vorschau auflösen

**Files:**
- Modify: `src/bewerbungs_pipeline/web/app.py`
- Modify: `src/bewerbungs_pipeline/web/routes/applications.py`
- Test: `tests/test_web_applications.py`

**Interfaces:**
- Consumes: `applications.render`
- Produces:
  - Mount `/template-assets` auf `cfg.template_path.parent`
  - `web.routes.applications.pfade_umschreiben(html: str) -> str`

**Problem:** Die Vorlage verweist relativ auf `styles.css` und `assets/…`. Im `iframe` unter `/applications/{id}/preview` lösen diese Pfade nicht auf. Beim Export bleibt alles wie bisher — dort liegen die Dateien daneben.

- [ ] **Step 1: Write the failing tests**

An `tests/test_web_applications.py` anhängen:

```python
def test_pfade_umschreiben_setzt_praefix():
    from bewerbungs_pipeline.web.routes import applications as app_routen

    html = '<link rel="stylesheet" href="styles.css"><img src="assets/foto.png">'
    ergebnis = app_routen.pfade_umschreiben(html)
    assert 'href="/template-assets/styles.css"' in ergebnis
    assert 'src="/template-assets/assets/foto.png"' in ergebnis


def test_pfade_umschreiben_laesst_absolute_pfade_in_ruhe():
    from bewerbungs_pipeline.web.routes import applications as app_routen

    html = '<img src="https://example.org/x.png"><img src="/schon-absolut.png">'
    assert app_routen.pfade_umschreiben(html) == html


def test_vorschau_schreibt_assetpfade_um(tmp_path):
    from dataclasses import replace

    cfg = replace(make_cfg(tmp_path), template_path=TEMPLATE_MIT_ASSETS)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/applications/{app_id}/preview")
    assert '/template-assets/styles.css' in antwort.text
```

Dafür oben in der Datei ergänzen:

```python
TEMPLATE_MIT_ASSETS = Path(__file__).parent / "fixtures" / "template_assets.html"
```

**Eigene Fixture, nicht die geteilte ändern:** `template_mini.html` wird von
`test_generate.py`, `test_applications.py` und `test_slots.py` benutzt — ein
zusätzlicher `<link>` dort wäre ein unnötiges Risiko für fremde Tests. Deshalb
`tests/fixtures/template_assets.html` neu anlegen:

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="styles.css">
  <title data-slot="titel">Bewerbung — AC Motoren</title>
</head>
<body>
  <h1 data-slot="firma">AC Motoren GmbH</h1>
  <p data-slot="einstieg">Mit großem Interesse habe ich Ihre Anzeige gelesen.</p>
  <p>Dieser Text ist statisch und bleibt unverändert.</p>
  <p data-slot="motivation">Ihre Produkte begeistern mich.</p>
</body>
</html>
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_web_applications.py -k "pfade or assetpfade" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'pfade_umschreiben'`.

- [ ] **Step 3: Implement**

In `routes/applications.py` `import re` ergänzen und einfügen:

```python
_ASSET_RE = re.compile(r'(?P<attr>\b(?:href|src)=")(?P<pfad>(?!https?:|/|data:|#)[^"]+)"')


def pfade_umschreiben(html: str) -> str:
    """Macht relative Vorlagen-Pfade im iframe auflösbar.

    Betrifft nur die Vorschau — die exportierte Datei in out/ bleibt
    unverändert, dort liegen styles.css und assets/ daneben.
    """
    return _ASSET_RE.sub(r'\g<attr>/template-assets/\g<pfad>"', html)
```

und die Vorschau-Route anpassen:

```python
    return HTMLResponse(pfade_umschreiben(html))
```

In `web/app.py` innerhalb von `create_app` nach dem `/static`-Mount:

```python
    vorlagen_ordner = cfg.template_path.parent
    if vorlagen_ordner.is_dir():
        app.mount(
            "/template-assets",
            StaticFiles(directory=str(vorlagen_ordner)),
            name="template-assets",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS.

- [ ] **Step 5: Von Hand prüfen**

```bash
uv run jobs serve --no-browser
```

Im Browser eine ausgewählte Stelle öffnen, Bewerbung erstellen, warten bis der Fortschritt „fertig" meldet, Bewerbungsseite öffnen. Erwartet: rechts erscheint die Bewerbung **mit** Schrift und Bildern der Vorlage. Einen Block ändern, speichern — die Vorschau lädt neu und zeigt den neuen Text.

- [ ] **Step 6: Commit**

```bash
git add src/bewerbungs_pipeline/web tests/
git commit -m "feat(web): Vorlagen-Assets in der Vorschau auflösen"
```

---

### Task 11: Vorschau nach dem Speichern neu laden, Abschluss-Audit, Doku

**Files:**
- Modify: `src/bewerbungs_pipeline/web/templates/_slot.html`
- Modify: `src/bewerbungs_pipeline/web/templates/bewerbung.html`
- Modify: `README.md`

**Interfaces:**
- Consumes: alles Vorherige
- Produces: keine neuen Schnittstellen

- [ ] **Step 1: Vorschau-Neuladen einbauen**

In `_slot.html` das Formular um ein Ereignis erweitern:

```html
  <form hx-put="/applications/{{ app_id }}/slots/{{ name }}"
        hx-target="#slot-{{ name }}" hx-swap="outerHTML"
        hx-on::after-request="document.getElementById('vorschau').contentWindow.location.reload()">
```

- [ ] **Step 2: Von Hand prüfen**

`uv run jobs serve --no-browser`, Bewerbung öffnen, einen Block ändern und speichern.
Erwartet: die Vorschau rechts zeigt den neuen Text ohne manuelles Neuladen.

- [ ] **Step 3: Barrierefreiheits- und UI-Audit**

Die Skill `web-design-guidelines` aus `/home/a/Dev/vault/.agents/skills/web-design-guidelines/SKILL.md` lesen und die Templates dagegen prüfen. Mindestens sicherstellen:

- jedes Eingabefeld hat ein `label` oder `aria-label`
- Fokus ist überall sichtbar (`:focus-visible`, bereits im CSS angelegt)
- der `iframe` hat ein `title`-Attribut (bereits gesetzt)
- Knöpfe sind `<button>`, Navigation ist `<a>` — keine klickbaren `div`s
- Kontrast von `--text-dim` auf `--bg` prüfen; falls unter 4.5:1, in `app.css` auf `--text` anheben

Gefundene Verstöße direkt beheben.

- [ ] **Step 4: README ergänzen**

In `README.md` nach dem Abschnitt „Benutzung" einfügen:

```markdown
## Weboberfläche

    uv run jobs serve            # → http://127.0.0.1:8765

Stellen sichten und auswählen, Bewerbung erzeugen, einzelne Textblöcke
nachbearbeiten oder neu erzeugen lassen, Vorschau ansehen, exportieren.
Läuft ausschließlich lokal, ohne Login.

Das CLI bleibt unverändert nutzbar.
```

- [ ] **Step 5: Gesamtlauf**

Run: `uv run pytest -v`
Expected: PASS — alle Module.

- [ ] **Step 6: Commit**

```bash
git add src/bewerbungs_pipeline/web README.md
git commit -m "feat(web): Vorschau nach Speichern neu laden, A11y-Audit, README"
```
