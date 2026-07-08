# Phase 1: Arbeitsagentur → SQLite → CLI → Slot-Füllung — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kompletter Durchstich: Stellen von der Arbeitsagentur-API holen, in SQLite verwalten, per CLI auswählen, per LLM die Slots einer HTML-Vorlage füllen und die fertige Bewerbung (+ Kopie in die CBKS-Inbox) ausgeben.

**Architecture:** Drei Stufen — `sources/arbeitsagentur.py` schreibt `JobItem`s über `db.py` in `data/jobs.db`; `cli.py` (argparse) steuert den Workflow-Status; `generate.py` orchestriert Vorlage (`slots.py`) + LLM (`llm.py`) + Ausgabe. Spec: `docs/specs/2026-07-08-bewerbungs-pipeline-design.md`.

**Tech Stack:** Python 3.13 (via uv), httpx, pydantic, openai (OpenAI-kompatibler Client), beautifulsoup4+lxml, pyyaml, python-dotenv, pytest.

## Global Constraints

- Projektwurzel: `/home/a/Dev/bewerbungs-pipeline`. Alle Pfade unten sind relativ dazu.
- Python 3.13 über uv: `uv sync` erzeugt die venv; Ausführung immer via `uv run <cmd>`.
- Tests laufen **ohne Netz** — API-/LLM-Aufrufe nur über Fixtures/Fakes.
- Secrets nur in `.env` (nie committen, `.env.example` als Muster).
- Nutzer-sichtbare CLI-Texte auf Deutsch, Code/Identifier auf Englisch.
- LLM-Regel (aus der Spec, wörtlich): „Das LLM formuliert nur aus Anzeige + Vorlagentexten; Fakten über die Firma, die nirgends stehen, werden nicht erfunden." Diese Regel steht im Prompt (Task 6).
- Statuswerte exakt: `new`, `selected`, `generated`, `rejected`.
- Commits klein, Conventional-Commit-Stil (`feat:`, `test:`, `chore:`, `docs:`).
- Die Arbeitsagentur-API ist inoffiziell dokumentiert — wenn ein Feldname in der Live-Antwort abweicht (Prüfschritt in Task 3), Parser an die Realität anpassen, nicht umgekehrt.

---

### Task 1: Projektgerüst

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/bewerbungs_pipeline/__init__.py`, `src/bewerbungs_pipeline/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `load_config() -> Config` mit Feldern `db_path: Path`, `out_dir: Path`, `template_path: Path`, `profile_path: Path`, `cbks_inbox: Path | None`, `llm_base_url: str`, `llm_api_key: str`, `llm_model: str`. Alle späteren Tasks importieren `from bewerbungs_pipeline.config import load_config`.

- [ ] **Step 1: Dateien anlegen**

`pyproject.toml`:

```toml
[project]
name = "bewerbungs-pipeline"
version = "0.1.0"
description = "Stellen finden und Bewerbungsvorlage per LLM füllen"
requires-python = ">=3.13"
dependencies = [
    "httpx",
    "pydantic",
    "openai",
    "beautifulsoup4",
    "lxml",
    "pyyaml",
    "python-dotenv",
]

[project.scripts]
jobs = "bewerbungs_pipeline.cli:main"

[dependency-groups]
dev = ["pytest"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/bewerbungs_pipeline"]
```

`.gitignore`:

```
.venv/
__pycache__/
*.egg-info/
.env
data/
out/
profile.yaml
```

`.env.example`:

```
# OpenAI-kompatibler LLM-Endpoint (GLM, Claude via Proxy, etc.)
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=

# Optional, Defaults siehe config.py
# DB_PATH=data/jobs.db
# OUT_DIR=out
# TEMPLATE_PATH=templates/vorlage.html
# PROFILE_PATH=profile.yaml
# CBKS_INBOX=/home/a/Dev/cbks/data/inbox
```

`src/bewerbungs_pipeline/__init__.py`: leere Datei.

`src/bewerbungs_pipeline/config.py`:

```python
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    db_path: Path
    out_dir: Path
    template_path: Path
    profile_path: Path
    cbks_inbox: Path | None
    llm_base_url: str
    llm_api_key: str
    llm_model: str


def load_config() -> Config:
    inbox = os.getenv("CBKS_INBOX", "")
    return Config(
        db_path=Path(os.getenv("DB_PATH", "data/jobs.db")),
        out_dir=Path(os.getenv("OUT_DIR", "out")),
        template_path=Path(os.getenv("TEMPLATE_PATH", "templates/vorlage.html")),
        profile_path=Path(os.getenv("PROFILE_PATH", "profile.yaml")),
        cbks_inbox=Path(inbox) if inbox else None,
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
    )
```

`tests/test_config.py`:

```python
from pathlib import Path

from bewerbungs_pipeline.config import load_config


def test_defaults(monkeypatch):
    for var in ("DB_PATH", "OUT_DIR", "CBKS_INBOX"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.db_path == Path("data/jobs.db")
    assert cfg.cbks_inbox is None


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("CBKS_INBOX", "/tmp/inbox")
    cfg = load_config()
    assert cfg.db_path == Path("/tmp/x.db")
    assert cfg.cbks_inbox == Path("/tmp/inbox")
```

- [ ] **Step 2: Installieren und Tests laufen lassen**

Run: `cd /home/a/Dev/bewerbungs-pipeline && uv sync && uv run pytest -q`
Expected: `2 passed`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml .gitignore .env.example src tests uv.lock
git commit -m "feat: Projektgerüst mit Config und uv-Setup"
```

---

### Task 2: JobItem-Modell und SQLite-Speicher mit Dedupe

**Files:**
- Create: `src/bewerbungs_pipeline/models.py`, `src/bewerbungs_pipeline/db.py`, `tests/test_db.py`

**Interfaces:**
- Produces:
  - `JobItem` (pydantic): `title: str`, `company: str`, `location: str`, `url: str`, `source: str`, `source_ref: str | None = None`, `company_website: str | None = None`, `posted_at: date | None = None`, `contact_name: str | None = None`, `contact_email: str | None = None`, `description_md: str = ""`, `scraped_at: datetime`
  - `db.connect(db_path: Path) -> sqlite3.Connection` (legt Schema an, `row_factory = sqlite3.Row`)
  - `db.insert_job(conn, item: JobItem) -> bool` (True = neu eingefügt, False = Duplikat)
  - `db.list_jobs(conn, status: str | None = None) -> list[sqlite3.Row]`
  - `db.get_job(conn, job_id: int) -> sqlite3.Row | None`
  - `db.set_status(conn, job_id: int, status: str) -> None` (ValueError bei unbekanntem Status)
  - `db.update_description(conn, job_id: int, text: str) -> None`
  - `db.row_to_item(row: sqlite3.Row) -> JobItem`

- [ ] **Step 1: Fehlschlagende Tests schreiben**

`tests/test_db.py`:

```python
from datetime import UTC, datetime

import pytest

from bewerbungs_pipeline import db
from bewerbungs_pipeline.models import JobItem


def make_item(**overrides) -> JobItem:
    base = dict(
        title="Mechatroniker (m/w/d)",
        company="AC Motoren GmbH",
        location="Eppertshausen",
        url="https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1",
        source="arbeitsagentur",
        source_ref="10001-1",
        scraped_at=datetime.now(UTC),
    )
    base.update(overrides)
    return JobItem(**base)


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "jobs.db")


def test_insert_and_read(conn):
    assert db.insert_job(conn, make_item()) is True
    rows = db.list_jobs(conn)
    assert len(rows) == 1
    assert rows[0]["status"] == "new"
    assert rows[0]["company"] == "AC Motoren GmbH"


def test_dedupe_same_url(conn):
    db.insert_job(conn, make_item())
    assert db.insert_job(conn, make_item()) is False
    assert len(db.list_jobs(conn)) == 1


def test_dedupe_cross_source_same_job(conn):
    db.insert_job(conn, make_item())
    dup = make_item(url="https://andere-quelle.de/job/1", source_ref=None, source="career:acme")
    assert db.insert_job(conn, dup) is False


def test_same_title_other_location_is_no_duplicate(conn):
    db.insert_job(conn, make_item())
    other = make_item(
        url="https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-2",
        source_ref="10001-2",
        location="Frankfurt am Main",
    )
    assert db.insert_job(conn, other) is True
    assert len(db.list_jobs(conn)) == 2


def test_status_transitions(conn):
    db.insert_job(conn, make_item())
    job_id = db.list_jobs(conn)[0]["id"]
    db.set_status(conn, job_id, "selected")
    assert db.get_job(conn, job_id)["status"] == "selected"
    with pytest.raises(ValueError):
        db.set_status(conn, job_id, "kaputt")


def test_list_filter_and_roundtrip(conn):
    db.insert_job(conn, make_item())
    job_id = db.list_jobs(conn)[0]["id"]
    db.set_status(conn, job_id, "rejected")
    assert db.list_jobs(conn, status="new") == []
    item = db.row_to_item(db.get_job(conn, job_id))
    assert item.company == "AC Motoren GmbH"
    assert item.source_ref == "10001-1"


def test_update_description(conn):
    db.insert_job(conn, make_item())
    job_id = db.list_jobs(conn)[0]["id"]
    db.update_description(conn, job_id, "Langer Anzeigentext")
    assert db.get_job(conn, job_id)["description_md"] == "Langer Anzeigentext"
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL / ERROR mit `ModuleNotFoundError: No module named 'bewerbungs_pipeline.db'`

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/models.py`:

```python
from datetime import date, datetime

from pydantic import BaseModel


class JobItem(BaseModel):
    title: str
    company: str
    location: str
    url: str
    source: str
    source_ref: str | None = None
    company_website: str | None = None
    posted_at: date | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    description_md: str = ""
    scraped_at: datetime
```

`src/bewerbungs_pipeline/db.py`:

```python
import hashlib
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import JobItem

STATUSES = {"new", "selected", "generated", "rejected"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    dedupe_hash TEXT NOT NULL UNIQUE,
    source_ref TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    company_website TEXT,
    location TEXT NOT NULL,
    source TEXT NOT NULL,
    posted_at TEXT,
    contact_name TEXT,
    contact_email TEXT,
    description_md TEXT NOT NULL DEFAULT '',
    scraped_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'
)
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def dedupe_hash(item: JobItem) -> str:
    key = "|".join(s.strip().lower() for s in (item.company, item.title, item.location))
    return hashlib.sha256(key.encode()).hexdigest()


def insert_job(conn: sqlite3.Connection, item: JobItem) -> bool:
    cur = conn.execute(
        """INSERT OR IGNORE INTO jobs
           (url, dedupe_hash, source_ref, title, company, company_website,
            location, source, posted_at, contact_name, contact_email,
            description_md, scraped_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item.url,
            dedupe_hash(item),
            item.source_ref,
            item.title,
            item.company,
            item.company_website,
            item.location,
            item.source,
            item.posted_at.isoformat() if item.posted_at else None,
            item.contact_name,
            item.contact_email,
            item.description_md,
            item.scraped_at.isoformat(),
        ),
    )
    conn.commit()
    return cur.rowcount == 1


def list_jobs(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status is not None:
        return conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
    return conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()


def get_job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def set_status(conn: sqlite3.Connection, job_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unbekannter Status: {status}")
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()


def update_description(conn: sqlite3.Connection, job_id: int, text: str) -> None:
    conn.execute("UPDATE jobs SET description_md = ? WHERE id = ?", (text, job_id))
    conn.commit()


def row_to_item(row: sqlite3.Row) -> JobItem:
    return JobItem(
        title=row["title"],
        company=row["company"],
        location=row["location"],
        url=row["url"],
        source=row["source"],
        source_ref=row["source_ref"],
        company_website=row["company_website"],
        posted_at=date.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
        contact_name=row["contact_name"],
        contact_email=row["contact_email"],
        description_md=row["description_md"],
        scraped_at=datetime.fromisoformat(row["scraped_at"]),
    )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_db.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/models.py src/bewerbungs_pipeline/db.py tests/test_db.py
git commit -m "feat: JobItem-Modell und SQLite-Speicher mit zweistufigem Dedupe"
```

---

### Task 3: Arbeitsagentur-Client

**Files:**
- Create: `src/bewerbungs_pipeline/sources/__init__.py`, `src/bewerbungs_pipeline/sources/arbeitsagentur.py`, `tests/fixtures/aa_search_response.json`, `tests/test_arbeitsagentur.py`

**Interfaces:**
- Consumes: `JobItem` aus Task 2.
- Produces:
  - `arbeitsagentur.parse_jobs(payload: dict) -> list[JobItem]`
  - `arbeitsagentur.fetch_jobs(was: str, wo: str, umkreis: int = 25, max_pages: int = 5) -> list[JobItem]` (Netzwerk)
  - `arbeitsagentur.fetch_details(refnr: str) -> str` (Netzwerk, Klartext der Anzeige oder `""`)

- [ ] **Step 1: Fixture und fehlschlagende Tests schreiben**

`tests/fixtures/aa_search_response.json`:

```json
{
  "stellenangebote": [
    {
      "titel": "Mechatroniker (m/w/d)",
      "refnr": "10001-1000012345-S",
      "arbeitgeber": "AC Motoren GmbH",
      "aktuelleVeroeffentlichungsdatum": "2026-07-01",
      "arbeitsort": {"plz": "64859", "ort": "Eppertshausen", "region": "Hessen"},
      "externeUrl": null
    },
    {
      "titel": "Servicetechniker (m/w/d)",
      "refnr": "10001-1000067890-S",
      "arbeitgeber": "Beispiel AG",
      "aktuelleVeroeffentlichungsdatum": "2026-07-05",
      "arbeitsort": {"plz": "60311", "ort": "Frankfurt am Main", "region": "Hessen"},
      "externeUrl": "https://karriere.beispiel.de/job/42"
    }
  ],
  "maxErgebnisse": 2
}
```

`tests/test_arbeitsagentur.py`:

```python
import json
from pathlib import Path

from bewerbungs_pipeline.sources import arbeitsagentur

FIXTURE = Path(__file__).parent / "fixtures" / "aa_search_response.json"


def load_payload() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parse_jobs_maps_fields():
    items = arbeitsagentur.parse_jobs(load_payload())
    assert len(items) == 2
    first = items[0]
    assert first.title == "Mechatroniker (m/w/d)"
    assert first.company == "AC Motoren GmbH"
    assert first.location == "Eppertshausen"
    assert first.source == "arbeitsagentur"
    assert first.source_ref == "10001-1000012345-S"
    assert first.posted_at.isoformat() == "2026-07-01"
    assert first.url == (
        "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1000012345-S"
    )


def test_parse_jobs_prefers_externe_url():
    items = arbeitsagentur.parse_jobs(load_payload())
    assert items[1].url == "https://karriere.beispiel.de/job/42"


def test_parse_jobs_empty_payload():
    assert arbeitsagentur.parse_jobs({}) == []
    assert arbeitsagentur.parse_jobs({"stellenangebote": []}) == []


def test_parse_jobs_skips_entry_without_refnr_and_url():
    payload = {"stellenangebote": [{"titel": "Kaputt", "arbeitgeber": "X"}]}
    assert arbeitsagentur.parse_jobs(payload) == []
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `uv run pytest tests/test_arbeitsagentur.py -q`
Expected: FAIL mit `ModuleNotFoundError`

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/sources/__init__.py`: leere Datei.

`src/bewerbungs_pipeline/sources/arbeitsagentur.py`:

```python
import base64
from datetime import UTC, date, datetime

import httpx

from ..models import JobItem

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-KEY": "jobboerse-jobsuche"}
DETAIL_PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
TIMEOUT = 30.0


def parse_jobs(payload: dict) -> list[JobItem]:
    items: list[JobItem] = []
    for entry in payload.get("stellenangebote", []):
        refnr = entry.get("refnr")
        url = entry.get("externeUrl") or (DETAIL_PAGE.format(refnr=refnr) if refnr else None)
        if not url:
            continue
        posted = entry.get("aktuelleVeroeffentlichungsdatum")
        items.append(
            JobItem(
                title=(entry.get("titel") or "").strip() or "(ohne Titel)",
                company=(entry.get("arbeitgeber") or "").strip() or "(unbekannt)",
                location=((entry.get("arbeitsort") or {}).get("ort") or "").strip(),
                url=url,
                source="arbeitsagentur",
                source_ref=refnr,
                posted_at=date.fromisoformat(posted[:10]) if posted else None,
                scraped_at=datetime.now(UTC),
            )
        )
    return items


def _search_page(client: httpx.Client, was: str, wo: str, umkreis: int, page: int) -> dict:
    response = client.get(
        f"{BASE_URL}/pc/v6/jobs",
        params={"was": was, "wo": wo, "umkreis": umkreis, "size": 100, "page": page},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def fetch_jobs(was: str, wo: str, umkreis: int = 25, max_pages: int = 5) -> list[JobItem]:
    items: list[JobItem] = []
    with httpx.Client() as client:
        for page in range(1, max_pages + 1):
            batch = parse_jobs(_search_page(client, was, wo, umkreis, page))
            if not batch:
                break
            items.extend(batch)
    return items


def fetch_details(refnr: str) -> str:
    encoded = base64.b64encode(refnr.encode()).decode()
    with httpx.Client() as client:
        response = client.get(
            f"{BASE_URL}/pc/v4/jobdetails/{encoded}", headers=HEADERS, timeout=TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    return payload.get("stellenbeschreibung") or ""
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_arbeitsagentur.py -q`
Expected: `4 passed`

- [ ] **Step 5: Live-Antwort gegen Fixture prüfen (einmalig, außerhalb der Tests)**

Run:

```bash
curl -s -H 'X-API-KEY: jobboerse-jobsuche' \
  'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs?was=Mechatroniker&wo=Frankfurt&size=2' \
  | python3 -m json.tool | head -60
```

Expected: JSON mit `stellenangebote`-Liste; Einträge enthalten `titel`, `refnr`, `arbeitgeber`, `arbeitsort.ort`.

Falls Feldnamen abweichen oder `/pc/v6/jobs` 404 liefert: `/pc/v4/jobs` mit denselben Parametern probieren; Fixture UND Parser an die echten Feldnamen anpassen, Tests erneut laufen lassen. Falls die API gar nicht erreichbar ist (Netzproblem): Schritt notieren und weitermachen — die Tests decken den Parser ab.

- [ ] **Step 6: Commit**

```bash
git add src/bewerbungs_pipeline/sources tests/fixtures/aa_search_response.json tests/test_arbeitsagentur.py
git commit -m "feat: Arbeitsagentur-Client mit Parser und Detail-Abruf"
```

---

### Task 4: CLI — fetch, list, pick, reject

**Files:**
- Create: `src/bewerbungs_pipeline/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config()` (Task 1), `db.*` (Task 2), `arbeitsagentur.fetch_jobs` (Task 3).
- Produces: `cli.main(argv: list[str] | None = None) -> int` und Entry-Point `jobs` (aus `pyproject.toml`, Task 1). `generate` wird hier als Subcommand registriert, ruft aber bis Task 7 nur eine Fehlermeldung auf — Task 7 ersetzt den Platzhalter `_cmd_generate`.

- [ ] **Step 1: Fehlschlagende Tests schreiben**

`tests/test_cli.py`:

```python
from datetime import UTC, datetime

import pytest

from bewerbungs_pipeline import cli, db
from bewerbungs_pipeline.models import JobItem


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "jobs.db"))
    return tmp_path


def seed(db_path) -> int:
    conn = db.connect(db_path)
    db.insert_job(
        conn,
        JobItem(
            title="Mechatroniker (m/w/d)",
            company="AC Motoren GmbH",
            location="Eppertshausen",
            url="https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1",
            source="arbeitsagentur",
            scraped_at=datetime.now(UTC),
        ),
    )
    job_id = db.list_jobs(conn)[0]["id"]
    conn.close()
    return job_id


def test_fetch_inserts_jobs(env, monkeypatch, capsys):
    fake_items = [
        JobItem(
            title="Elektroniker (m/w/d)",
            company="Beispiel AG",
            location="Frankfurt am Main",
            url="https://example.org/job/1",
            source="arbeitsagentur",
            scraped_at=datetime.now(UTC),
        )
    ]
    monkeypatch.setattr(cli.arbeitsagentur, "fetch_jobs", lambda **kw: fake_items)
    rc = cli.main(["fetch", "--was", "Elektroniker", "--wo", "Frankfurt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "1 neu" in out


def test_list_shows_job(env, capsys):
    seed(env / "jobs.db")
    rc = cli.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "AC Motoren GmbH" in out
    assert "new" in out


def test_pick_and_reject(env, capsys):
    job_id = seed(env / "jobs.db")
    assert cli.main(["pick", str(job_id)]) == 0
    conn = db.connect(env / "jobs.db")
    assert db.get_job(conn, job_id)["status"] == "selected"
    conn.close()
    assert cli.main(["reject", str(job_id)]) == 0
    conn = db.connect(env / "jobs.db")
    assert db.get_job(conn, job_id)["status"] == "rejected"
    conn.close()


def test_pick_unknown_id_fails(env, capsys):
    seed(env / "jobs.db")
    rc = cli.main(["pick", "999"])
    assert rc == 1
    assert "nicht gefunden" in capsys.readouterr().err
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `uv run pytest tests/test_cli.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'bewerbungs_pipeline.cli'`

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/cli.py`:

```python
import argparse
import sys

from . import db
from .config import load_config
from .sources import arbeitsagentur


def _cmd_fetch(args: argparse.Namespace) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    items = arbeitsagentur.fetch_jobs(was=args.was, wo=args.wo, umkreis=args.umkreis)
    inserted = sum(1 for item in items if db.insert_job(conn, item))
    print(f"{len(items)} Stellen geholt, {inserted} neu.")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    rows = db.list_jobs(conn, status=args.status)
    if not rows:
        print("Keine Stellen gefunden.")
        return 0
    print(f"{'ID':>4}  {'Status':<9} {'Titel':<40} {'Firma':<30} Ort")
    for row in rows:
        print(
            f"{row['id']:>4}  {row['status']:<9} "
            f"{row['title'][:40]:<40} {row['company'][:30]:<30} {row['location']}"
        )
    return 0


def _set_status(job_id: int, status: str) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    if db.get_job(conn, job_id) is None:
        print(f"Job {job_id} nicht gefunden.", file=sys.stderr)
        return 1
    db.set_status(conn, job_id, status)
    print(f"Job {job_id} → {status}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    print("generate ist noch nicht implementiert (kommt in Task 7).", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobs", description="Bewerbungs-Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="Stellen von der Arbeitsagentur holen")
    p_fetch.add_argument("--was", required=True, help="Suchbegriff, z. B. Beruf")
    p_fetch.add_argument("--wo", required=True, help="Ort")
    p_fetch.add_argument("--umkreis", type=int, default=25, help="Umkreis in km")
    p_fetch.set_defaults(func=_cmd_fetch)

    p_list = sub.add_parser("list", help="Stellen anzeigen")
    p_list.add_argument("--status", choices=sorted(db.STATUSES), default=None)
    p_list.set_defaults(func=_cmd_list)

    p_pick = sub.add_parser("pick", help="Stelle auswählen")
    p_pick.add_argument("id", type=int)
    p_pick.set_defaults(func=lambda a: _set_status(a.id, "selected"))

    p_reject = sub.add_parser("reject", help="Stelle aussortieren")
    p_reject.add_argument("id", type=int)
    p_reject.set_defaults(func=lambda a: _set_status(a.id, "rejected"))

    p_gen = sub.add_parser("generate", help="Bewerbung für ausgewählte Stelle erzeugen")
    p_gen.add_argument("id", type=int)
    p_gen.set_defaults(func=_cmd_generate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_cli.py -q`
Expected: `4 passed`

- [ ] **Step 5: CLI von Hand prüfen (mit Netz)**

Run: `uv run jobs fetch --was "Mechatroniker" --wo "Frankfurt" && uv run jobs list | head -10`
Expected: „N Stellen geholt, M neu." und eine Tabelle mit echten Stellen. Bei Netz-/API-Fehler: Fehlermeldung notieren, Tests bleiben maßgeblich.

- [ ] **Step 6: Commit**

```bash
git add src/bewerbungs_pipeline/cli.py tests/test_cli.py
git commit -m "feat: CLI mit fetch/list/pick/reject"
```

---

### Task 5: Slot-Extraktion und -Füllung

**Files:**
- Create: `src/bewerbungs_pipeline/slots.py`, `tests/test_slots.py`, `tests/fixtures/template_mini.html`

**Interfaces:**
- Produces:
  - `slots.extract_slots(html: str) -> dict[str, str]` (Slot-Name → aktueller Text; ValueError bei doppeltem Slot-Namen)
  - `slots.fill_slots(html: str, values: dict[str, str]) -> str` (ValueError, wenn ein Key in `values` keinen Slot in der Vorlage hat)

- [ ] **Step 1: Fixture und fehlschlagende Tests schreiben**

`tests/fixtures/template_mini.html`:

```html
<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title data-slot="titel">Bewerbung — AC Motoren</title></head>
<body>
  <h1 data-slot="firma">AC Motoren GmbH</h1>
  <p class="intro" data-slot="einstieg">Mit großem Interesse habe ich Ihre Anzeige gelesen.</p>
  <p>Dieser Text ist statisch und bleibt unverändert.</p>
  <section>
    <p data-slot="motivation">Ihre Produkte begeistern mich, <strong>weil</strong> sie robust sind.</p>
  </section>
</body>
</html>
```

`tests/test_slots.py`:

```python
from pathlib import Path

import pytest

from bewerbungs_pipeline.slots import extract_slots, fill_slots

TEMPLATE = (Path(__file__).parent / "fixtures" / "template_mini.html").read_text()


def test_extract_slots():
    slots = extract_slots(TEMPLATE)
    assert set(slots) == {"titel", "firma", "einstieg", "motivation"}
    assert slots["firma"] == "AC Motoren GmbH"
    assert slots["einstieg"].startswith("Mit großem Interesse")


def test_extract_duplicate_slot_raises():
    html = '<p data-slot="x">a</p><p data-slot="x">b</p>'
    with pytest.raises(ValueError, match="doppelt"):
        extract_slots(html)


def test_fill_slots_replaces_only_slots():
    result = fill_slots(
        TEMPLATE,
        {"firma": "Beispiel AG", "einstieg": "Neuer Einstieg.", "titel": "Bewerbung — Beispiel AG", "motivation": "Neue Motivation."},
    )
    assert "Beispiel AG" in result
    assert "AC Motoren GmbH" not in result
    assert "Dieser Text ist statisch und bleibt unverändert." in result
    assert "robust" not in result  # alter Slot-Inhalt inkl. Markup ersetzt


def test_fill_slots_partial_is_allowed():
    result = fill_slots(TEMPLATE, {"firma": "Beispiel AG"})
    assert "Beispiel AG" in result
    assert "Mit großem Interesse" in result  # nicht übergebene Slots bleiben


def test_fill_unknown_slot_raises():
    with pytest.raises(ValueError, match="nicht in Vorlage"):
        fill_slots(TEMPLATE, {"gibtsnicht": "x"})
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `uv run pytest tests/test_slots.py -q`
Expected: FAIL mit `ModuleNotFoundError`

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/slots.py`:

```python
from bs4 import BeautifulSoup


def extract_slots(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    slots: dict[str, str] = {}
    for element in soup.select("[data-slot]"):
        name = element["data-slot"]
        if name in slots:
            raise ValueError(f"Slot doppelt vergeben: {name}")
        slots[name] = element.get_text(" ", strip=True)
    return slots


def fill_slots(html: str, values: dict[str, str]) -> str:
    soup = BeautifulSoup(html, "lxml")
    filled: set[str] = set()
    for element in soup.select("[data-slot]"):
        name = element["data-slot"]
        if name in values:
            element.clear()
            element.append(values[name])
            filled.add(name)
    unknown = set(values) - filled
    if unknown:
        raise ValueError(f"Slots nicht in Vorlage: {sorted(unknown)}")
    return str(soup)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_slots.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/slots.py tests/test_slots.py tests/fixtures/template_mini.html
git commit -m "feat: Slot-Extraktion und -Füllung über data-slot-Attribute"
```

---

### Task 6: LLM-Generierung mit Validierung und einem Retry

**Files:**
- Create: `src/bewerbungs_pipeline/llm.py`, `tests/test_llm.py`

**Interfaces:**
- Consumes: `JobItem` (Task 2).
- Produces:
  - `llm.GenerationError(Exception)`
  - `llm.make_client(base_url: str, api_key: str) -> openai.OpenAI`
  - `llm.generate_slot_texts(client, model: str, job: JobItem, slots: dict[str, str], profile: dict) -> dict[str, str]` — genau ein Retry bei Validierungsfehler, danach `GenerationError`.
  - Intern testbar: `llm.parse_response(text: str) -> dict`, `llm.validate_values(values: dict, slots: dict, company: str) -> list[str]` (leere Liste = ok)

- [ ] **Step 1: Fehlschlagende Tests schreiben**

`tests/test_llm.py`:

```python
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from bewerbungs_pipeline import llm
from bewerbungs_pipeline.models import JobItem

JOB = JobItem(
    title="Mechatroniker (m/w/d)",
    company="Beispiel AG",
    location="Frankfurt am Main",
    url="https://example.org/job/1",
    source="arbeitsagentur",
    description_md="Wir suchen einen Mechatroniker für Wartung und Instandhaltung.",
    scraped_at=datetime.now(UTC),
)
SLOTS = {"firma": "AC Motoren GmbH", "einstieg": "Mit großem Interesse …"}
PROFILE = {"name": "Alain Ritter", "email": "cosmwave@gmail.com"}


class FakeClient:
    """Gibt vorbereitete Antworten in Reihenfolge zurück und zählt Aufrufe."""

    def __init__(self, responses: list[str]):
        self.calls = 0
        self._responses = responses
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        text = self._responses[self.calls]
        self.calls += 1
        message = SimpleNamespace(content=text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def good_response() -> str:
    return json.dumps(
        {"firma": "Beispiel AG", "einstieg": "Ihre Anzeige bei der Beispiel AG hat mich überzeugt."}
    )


def test_parse_response_strips_code_fence():
    fenced = "```json\n{\"a\": \"b\"}\n```"
    assert llm.parse_response(fenced) == {"a": "b"}


def test_validate_ok():
    values = json.loads(good_response())
    assert llm.validate_values(values, SLOTS, "Beispiel AG") == []


def test_validate_catches_problems():
    assert llm.validate_values({"firma": "x"}, SLOTS, "Beispiel AG")  # Slot fehlt
    bad_empty = {"firma": "", "einstieg": "y"}
    assert llm.validate_values(bad_empty, SLOTS, "Beispiel AG")  # leerer Slot
    no_company = {"firma": "Anders GmbH", "einstieg": "Text ohne Firmenbezug."}
    assert llm.validate_values(no_company, SLOTS, "Beispiel AG")  # Firmenname fehlt


def test_generate_success_first_try():
    client = FakeClient([good_response()])
    values = llm.generate_slot_texts(client, "test-model", JOB, SLOTS, PROFILE)
    assert values["firma"] == "Beispiel AG"
    assert client.calls == 1


def test_generate_retries_once_then_succeeds():
    client = FakeClient(["kein json", good_response()])
    values = llm.generate_slot_texts(client, "test-model", JOB, SLOTS, PROFILE)
    assert values["einstieg"].startswith("Ihre Anzeige")
    assert client.calls == 2


def test_generate_fails_after_two_attempts():
    client = FakeClient(["kein json", "immer noch kein json"])
    with pytest.raises(llm.GenerationError):
        llm.generate_slot_texts(client, "test-model", JOB, SLOTS, PROFILE)
    assert client.calls == 2
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `uv run pytest tests/test_llm.py -q`
Expected: FAIL mit `ModuleNotFoundError`

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/llm.py`:

```python
import json

from openai import OpenAI

from .models import JobItem


class GenerationError(Exception):
    pass


PROMPT_TEMPLATE = """Du personalisierst eine deutsche Bewerbungsvorlage für eine konkrete Stelle.

## Stellenanzeige
Titel: {title}
Firma: {company}
Ort: {location}

{description}

## Bewerberprofil
{profile}

## Slots der Vorlage (Name → bisheriger Beispieltext)
{slots}

## Auftrag
Schreibe für jeden Slot einen neuen Text im Stil und in ungefähr der Länge des Beispieltexts,
zugeschnitten auf diese Stelle und diese Firma.

Regeln:
- Formuliere nur aus Stellenanzeige, Bewerberprofil und den Beispieltexten.
- Erfinde keine Fakten über die Firma, die nirgends stehen.
- Der Firmenname "{company}" muss in mindestens einem Slot-Text vorkommen.
- Antworte NUR mit einem JSON-Objekt: {{"slotname": "neuer Text", ...}}
  mit exakt denselben Slot-Namen wie oben, ohne weitere Erklärungen.
"""


def make_client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key)


def build_prompt(job: JobItem, slots: dict[str, str], profile: dict) -> str:
    return PROMPT_TEMPLATE.format(
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description_md or "(keine Beschreibung vorhanden)",
        profile=json.dumps(profile, ensure_ascii=False, indent=2),
        slots=json.dumps(slots, ensure_ascii=False, indent=2),
    )


def parse_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    return json.loads(cleaned)


def validate_values(values: dict, slots: dict[str, str], company: str) -> list[str]:
    problems: list[str] = []
    if set(values) != set(slots):
        problems.append(
            f"Slot-Namen stimmen nicht überein: erwartet {sorted(slots)}, bekommen {sorted(values)}"
        )
    empty = [k for k, v in values.items() if not isinstance(v, str) or not v.strip()]
    if empty:
        problems.append(f"Leere Slots: {empty}")
    joined = " ".join(str(v) for v in values.values()).lower()
    if company.lower() not in joined:
        problems.append(f"Firmenname '{company}' kommt in keinem Slot vor")
    return problems


def generate_slot_texts(
    client, model: str, job: JobItem, slots: dict[str, str], profile: dict
) -> dict[str, str]:
    prompt = build_prompt(job, slots, profile)
    last_problems: list[str] = []
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
            last_problems = ["Antwort war kein gültiges JSON"]
        else:
            last_problems = validate_values(values, slots, job.company)
            if not last_problems:
                return values
        prompt = build_prompt(job, slots, profile) + (
            f"\n\nDein letzter Versuch hatte diese Fehler: {last_problems}. Korrigiere sie."
        )
    raise GenerationError(f"LLM-Ausgabe nach 2 Versuchen ungültig: {last_problems}")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_llm.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/llm.py tests/test_llm.py
git commit -m "feat: LLM-Slot-Generierung mit Validierung und einem Retry"
```

---

### Task 7: generate-Orchestrierung, profile.yaml, CBKS-Inbox

**Files:**
- Create: `src/bewerbungs_pipeline/generate.py`, `templates/beispiel.html`, `profile.yaml.example`, `tests/test_generate.py`
- Modify: `src/bewerbungs_pipeline/cli.py` (Funktion `_cmd_generate` ersetzen, Import ergänzen)

**Interfaces:**
- Consumes: alles aus Task 1–6.
- Produces: `generate.generate_application(conn, job_id: int, cfg: Config, client) -> Path` (gibt Ausgabeverzeichnis zurück; `SystemExit` mit Meldung bei Bedienfehlern). `generate.slugify(text: str) -> str`.

- [ ] **Step 1: Beispieldateien anlegen**

`templates/beispiel.html` (Kopie von `tests/fixtures/template_mini.html` — kleine Demo-Vorlage, bis der Nutzer seine echte Vorlage markiert hat):

```html
<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title data-slot="titel">Bewerbung — AC Motoren</title></head>
<body>
  <h1 data-slot="firma">AC Motoren GmbH</h1>
  <p class="intro" data-slot="einstieg">Mit großem Interesse habe ich Ihre Anzeige gelesen.</p>
  <p>Dieser Text ist statisch und bleibt unverändert.</p>
  <section>
    <p data-slot="motivation">Ihre Produkte begeistern mich, <strong>weil</strong> sie robust sind.</p>
  </section>
</body>
</html>
```

`profile.yaml.example`:

```yaml
name: Alain Ritter
adresse: "Straße Hausnr, PLZ Ort"
email: cosmwave@gmail.com
telefon: "+49 ..."
```

- [ ] **Step 2: Fehlschlagende Tests schreiben**

`tests/test_generate.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bewerbungs_pipeline import db, generate
from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.models import JobItem

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"


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


def seed(cfg, status="selected", description="Wir suchen Verstärkung im Service.") -> int:
    conn = db.connect(cfg.db_path)
    db.insert_job(
        conn,
        JobItem(
            title="Servicetechniker (m/w/d)",
            company="Beispiel AG",
            location="Frankfurt am Main",
            url="https://example.org/job/1",
            source="arbeitsagentur",
            description_md=description,
            scraped_at=datetime.now(UTC),
        ),
    )
    job_id = db.list_jobs(conn)[0]["id"]
    db.set_status(conn, job_id, status)
    conn.close()
    return job_id


GOOD = {
    "titel": "Bewerbung — Beispiel AG",
    "firma": "Beispiel AG",
    "einstieg": "Ihre Anzeige als Servicetechniker bei der Beispiel AG hat mich überzeugt.",
    "motivation": "Wartung und Service sind genau mein Feld.",
}


def test_generate_writes_output_and_sets_status(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    out_dir = generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))
    html = (out_dir / "index.html").read_text()
    assert "Beispiel AG" in html
    assert "Dieser Text ist statisch und bleibt unverändert." in html
    stelle = (out_dir / "stelle.md").read_text()
    assert "Servicetechniker" in stelle
    assert db.get_job(conn, job_id)["status"] == "generated"


def test_generate_copies_to_cbks_inbox(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    cfg = make_cfg(tmp_path, cbks_inbox=inbox)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))
    names = {p.name for p in inbox.iterdir()}
    assert names == {"bewerbung-beispiel-ag.html", "stelle-beispiel-ag.md"}


def test_generate_missing_inbox_warns_but_succeeds(tmp_path, capsys):
    cfg = make_cfg(tmp_path, cbks_inbox=tmp_path / "gibtsnicht")
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))
    assert "CBKS-Inbox" in capsys.readouterr().err
    assert db.get_job(conn, job_id)["status"] == "generated"


def test_generate_requires_selected_status(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg, status="new")
    conn = db.connect(cfg.db_path)
    with pytest.raises(SystemExit):
        generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))


def test_slugify():
    assert generate.slugify("AC Motoren GmbH & Co. KG") == "ac-motoren-gmbh-co-kg"
    assert generate.slugify("Müllerößä") != ""
```

- [ ] **Step 3: Tests laufen lassen — müssen fehlschlagen**

Run: `uv run pytest tests/test_generate.py -q`
Expected: FAIL mit `ModuleNotFoundError`

- [ ] **Step 4: Implementieren**

`src/bewerbungs_pipeline/generate.py`:

```python
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
    slots = extract_slots(template)
    if not slots:
        raise SystemExit("Vorlage enthält keine data-slot-Markierungen.")
    profile = yaml.safe_load(cfg.profile_path.read_text())
    job = dbmod.row_to_item(row)

    values = generate_slot_texts(client, cfg.llm_model, job, slots, profile)
    html = fill_slots(template, values)

    slug = slugify(row["company"])
    out_dir = cfg.out_dir / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html)
    (out_dir / "stelle.md").write_text(
        f"# {row['title']} — {row['company']}\n\n"
        f"Ort: {row['location']}\nQuelle: {row['url']}\n\n{row['description_md']}\n"
    )

    if cfg.cbks_inbox is not None:
        if cfg.cbks_inbox.is_dir():
            shutil.copy(out_dir / "index.html", cfg.cbks_inbox / f"bewerbung-{slug}.html")
            shutil.copy(out_dir / "stelle.md", cfg.cbks_inbox / f"stelle-{slug}.md")
        else:
            print(
                f"Warnung: CBKS-Inbox {cfg.cbks_inbox} existiert nicht — übersprungen.",
                file=sys.stderr,
            )

    dbmod.set_status(conn, job_id, "generated")
    return out_dir
```

In `src/bewerbungs_pipeline/cli.py` die Platzhalter-Funktion `_cmd_generate` ersetzen durch:

```python
def _cmd_generate(args: argparse.Namespace) -> int:
    from .generate import generate_application
    from .llm import make_client

    cfg = load_config()
    if not (cfg.llm_base_url and cfg.llm_api_key and cfg.llm_model):
        print("LLM_BASE_URL, LLM_API_KEY und LLM_MODEL in .env setzen.", file=sys.stderr)
        return 1
    conn = db.connect(cfg.db_path)
    client = make_client(cfg.llm_base_url, cfg.llm_api_key)
    out_dir = generate_application(conn, args.id, cfg, client)
    print(f"Fertig: {out_dir / 'index.html'}")
    return 0
```

- [ ] **Step 5: Alle Tests laufen lassen**

Run: `uv run pytest -q`
Expected: alle Tests grün (`33 passed`; exakte Zahl kann leicht abweichen, wichtig: 0 failed)

- [ ] **Step 6: Commit**

```bash
git add src/bewerbungs_pipeline/generate.py src/bewerbungs_pipeline/cli.py \
  templates/beispiel.html profile.yaml.example tests/test_generate.py
git commit -m "feat: generate-Kommando mit Profil, Ausgabe und CBKS-Inbox-Kopie"
```

---

### Task 8: README und Ende-zu-Ende-Probe

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: das komplette CLI aus Task 4/7.

- [ ] **Step 1: README schreiben**

`README.md`:

```markdown
# Bewerbungs-Pipeline

Stellen finden → Shortlist → Bewerbungsvorlage per LLM füllen.
Spec: `docs/specs/2026-07-08-bewerbungs-pipeline-design.md`.

## Setup

    uv sync
    cp .env.example .env        # LLM_BASE_URL, LLM_API_KEY, LLM_MODEL eintragen
    cp profile.yaml.example profile.yaml   # persönliche Daten eintragen

## Eigene Vorlage anschließen

1. Claude-Design-HTML kopieren, z. B.:
   `cp /home/a/Dev/ac-motoren/index.html templates/vorlage.html`
2. In der Kopie jeden Textblock, der pro Bewerbung wechseln soll, mit
   `data-slot="name"` markieren (eindeutige Namen). Alles ohne `data-slot`
   bleibt unverändert.
3. `TEMPLATE_PATH=templates/vorlage.html` in `.env` setzen.
   Ohne eigenen Schritt läuft alles mit der Demo-Vorlage `templates/beispiel.html`
   (`TEMPLATE_PATH=templates/beispiel.html`).

## Benutzung

    uv run jobs fetch --was "Mechatroniker" --wo "Frankfurt" --umkreis 50
    uv run jobs list --status new
    uv run jobs pick 3
    uv run jobs generate 3      # → out/<firma>/index.html

Mit `CBKS_INBOX=/home/a/Dev/cbks/data/inbox` in `.env` landet jede fertige
Bewerbung zusätzlich als Kopie in der CBKS-Inbox.
```

- [ ] **Step 2: Ende-zu-Ende-Probe (mit Netz und echtem LLM-Key)**

Voraussetzung: `.env` mit gültigen `LLM_*`-Werten und `TEMPLATE_PATH=templates/beispiel.html`, `profile.yaml` vorhanden.

```bash
uv run jobs fetch --was "Mechatroniker" --wo "Frankfurt"
uv run jobs list --status new | head -5
uv run jobs pick <ID-aus-Liste>
uv run jobs generate <ID>
```

Expected: `Fertig: out/<firma>/index.html`; Datei öffnen und prüfen, dass Firmenname der echten Stelle in den Slot-Texten steht und der statische Text unverändert ist. Falls kein LLM-Key verfügbar: Schritt dokumentiert überspringen — die Fake-Client-Tests aus Task 7 decken die Logik ab.

- [ ] **Step 3: Gesamte Testsuite final laufen lassen**

Run: `uv run pytest -q`
Expected: 0 failed

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README mit Setup, Vorlagen-Anleitung und Benutzung"
```
