# Jobschleuse JSON-API (Phase 1 von 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alle bestehenden HTML/HTMX-Endpunkte der Jobschleuse-Weboberfläche
als äquivalente JSON-Endpunkte unter `/api/*` bereitstellen, ohne die
bestehende HTML-Oberfläche anzufassen — sie bleibt während dieser Phase
unverändert benutzbar.

**Architecture:** Neue Route-Module (`web/routes/api_jobs.py`,
`web/routes/api_tasks.py`, `web/routes/api_applications.py`) rufen exakt
dieselbe Business-Logik auf wie die bestehenden HTML-Routen
(`applications.py`, `db.py`, `tasks.py`, sowie die Hintergrundlauf-Funktionen
aus `web/routes/jobs.py` und `web/routes/applications.py`) — keine Logik
wird dupliziert, nur eine zweite, JSON-basierte Route-Schicht kommt hinzu.
Antwortformen sind Pydantic-Modelle in einem neuen `web/schemas.py`.

**Tech Stack:** FastAPI (bestehend), Pydantic v2 (bestehend über
`fastapi`/`models.py`), pytest + `fastapi.testclient.TestClient` (bestehend).
Keine neuen Abhängigkeiten.

**Spec:** `docs/specs/2026-08-27-shadcn-umbau-design.md`

## Global Constraints

- Python `>=3.13`, src-layout, Package-Manager `uv` — Setup/Tests laufen
  ausschließlich über `uv run ...` (siehe `CLAUDE.md`).
- Tests: `uv run pytest`. `filterwarnings = ["error"]` ist scharf gestellt —
  jede neue, nicht whitelistete Warnung lässt die Suite fehlschlagen.
- Business-Logik (`applications.py`, `db.py`, `tasks.py`) wird unverändert
  wiederverwendet, nicht dupliziert — neue Route-Module rufen sie nur auf.
- Kein String-Interpolieren von Nutzereingaben in SQL. Sortierspalten laufen
  über eine feste Whitelist.
- Die bestehenden HTML-Routen und ihre Tests (`routes/jobs.py`,
  `routes/applications.py`, `routes/tasks.py`,
  `tests/test_web_{app,jobs,applications}.py`) bleiben in dieser Phase
  vollständig unangetastet — sie werden erst in Phase 3 entfernt.
- Deutsche Bezeichner und Fehlermeldungen, wie im gesamten Projekt üblich.
- Git-Workflow: Commits direkt auf `master`, keine Feature-Branches.

---

## Datei-Übersicht

| Datei | Aktion | Zweck |
|---|---|---|
| `src/bewerbungs_pipeline/db.py` | ändern | `suche_jobs` bekommt `sort`/`order`; neue Funktion `set_status_bulk` |
| `src/bewerbungs_pipeline/web/schemas.py` | neu | Pydantic-Antwort-/Request-Modelle für `/api/*` |
| `src/bewerbungs_pipeline/web/routes/api_jobs.py` | neu | `GET/POST /api/jobs*` |
| `src/bewerbungs_pipeline/web/routes/api_tasks.py` | neu | `GET /api/tasks/{id}` |
| `src/bewerbungs_pipeline/web/routes/api_applications.py` | neu | `POST/GET/PUT /api/applications*` |
| `src/bewerbungs_pipeline/web/app.py` | ändern | die drei neuen Router registrieren |
| `tests/test_db.py` | ändern | Tests für Sortierung + Bulk-Status |
| `tests/test_web_schemas.py` | neu | Tests für die `*_out`-Konvertierungen |
| `tests/test_api_jobs.py` | neu | Tests für `/api/jobs*` |
| `tests/test_api_tasks.py` | neu | Tests für `/api/tasks/{id}` |
| `tests/test_api_applications.py` | neu | Tests für `/api/applications*` |

---

### Task 1: `db.py` — Sortierung in `suche_jobs`, neue `set_status_bulk`

**Files:**
- Modify: `src/bewerbungs_pipeline/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `suche_jobs(conn, status=None, q=None, ort=None, mit_verschwundenen=False, sort="id", order="desc") -> list[sqlite3.Row]` (bisherige Signatur + zwei neue optionale Parameter, Default-Verhalten unverändert). `set_status_bulk(conn, job_ids: list[int], status: str) -> int` — liefert Anzahl geänderter Zeilen, wirft `ValueError` bei unbekanntem Status.

- [ ] **Step 1: Fehlschlagende Tests schreiben**

An `tests/test_db.py` anhängen (Datei importiert bereits `pytest`, `db`, `JobItem`, hat bereits `make_item()` und die `conn`-Fixture — nichts davon neu schreiben):

```python
def test_suche_jobs_default_bleibt_id_absteigend(conn):
    db.insert_job(conn, make_item(url="http://a"))
    db.insert_job(conn, make_item(url="http://b", title="Zweite"))
    rows = db.suche_jobs(conn)
    assert [r["id"] for r in rows] == [2, 1]


def test_suche_jobs_sortiert_nach_titel_aufsteigend(conn):
    db.insert_job(conn, make_item(url="http://a", title="Zebra", company="Firma A"))
    db.insert_job(conn, make_item(url="http://b", title="Anton", company="Firma B"))
    rows = db.suche_jobs(conn, sort="title", order="asc")
    assert [r["title"] for r in rows] == ["Anton", "Zebra"]


def test_suche_jobs_sortiert_nach_entfernung(conn):
    db.insert_job(conn, make_item(url="http://a", distance_km=50))
    db.insert_job(conn, make_item(url="http://b", distance_km=10, title="Andere"))
    rows = db.suche_jobs(conn, sort="distance_km", order="asc")
    assert [r["distance_km"] for r in rows] == [10, 50]


def test_suche_jobs_unbekannte_sortierung_faellt_auf_id_zurueck(conn):
    db.insert_job(conn, make_item(url="http://a"))
    db.insert_job(conn, make_item(url="http://b", title="Zweite"))
    rows = db.suche_jobs(conn, sort="does-not-exist; DROP TABLE jobs")
    assert [r["id"] for r in rows] == [2, 1]


def test_set_status_bulk_aktualisiert_mehrere(conn):
    db.insert_job(conn, make_item(url="http://a"))
    db.insert_job(conn, make_item(url="http://b", title="Zweite"))
    ids = [r["id"] for r in db.list_jobs(conn)]
    geaendert = db.set_status_bulk(conn, ids, "selected")
    assert geaendert == 2
    assert all(r["status"] == "selected" for r in db.list_jobs(conn))


def test_set_status_bulk_leere_liste(conn):
    assert db.set_status_bulk(conn, [], "selected") == 0


def test_set_status_bulk_lehnt_unbekannten_status_ab(conn):
    db.insert_job(conn, make_item(url="http://a"))
    job_id = db.list_jobs(conn)[0]["id"]
    with pytest.raises(ValueError):
        db.set_status_bulk(conn, [job_id], "geloescht")
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `uv run pytest tests/test_db.py -v -k "sortier or bulk or default_bleibt"`
Expected: FAIL — `suche_jobs() got an unexpected keyword argument 'sort'` bzw.
`AttributeError: module 'bewerbungs_pipeline.db' has no attribute 'set_status_bulk'`

- [ ] **Step 3: Implementieren**

In `src/bewerbungs_pipeline/db.py` nach der Konstante `STATUSES` einfügen:

```python
# Whitelist statt String-Interpolation: `sort` kommt aus der URL und darf
# niemals direkt in die SQL-Anweisung wandern.
_SORT_SPALTEN = {
    "id": "id",
    "frische": "COALESCE(changed_at, posted_at)",
    "distance_km": "distance_km",
    "company": "company",
    "title": "title",
}
```

`suche_jobs` ersetzen durch:

```python
def suche_jobs(
    conn: sqlite3.Connection,
    status: str | None = None,
    q: str | None = None,
    ort: str | None = None,
    mit_verschwundenen: bool = False,
    sort: str = "id",
    order: str = "desc",
) -> list[sqlite3.Row]:
    """Stellenliste mit optionalen Filtern.

    `q` sucht in Titel und Firma, `ort` im Ort — beides ohne
    Beachtung der Groß-/Kleinschreibung. Stellen, deren Anzeige bei der
    Quelle verschwunden ist, bleiben aussen vor, solange
    `mit_verschwundenen` nicht gesetzt ist. `sort` läuft über eine feste
    Spalten-Whitelist; unbekannte Werte fallen still auf `id` zurück.
    """
    spalte = _SORT_SPALTEN.get(sort, "id")
    richtung = "ASC" if order == "asc" else "DESC"
    sql = "SELECT * FROM jobs WHERE 1=1"
    werte: list[str] = []
    if not mit_verschwundenen:
        sql += " AND gone_at IS NULL"
    if status:
        sql += " AND status = ?"
        werte.append(status)
    if q:
        sql += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"
        werte.extend([f"%{q.lower()}%"] * 2)
    if ort:
        sql += " AND LOWER(location) LIKE ?"
        werte.append(f"%{ort.lower()}%")
    sql += f" ORDER BY {spalte} {richtung}"
    return conn.execute(sql, werte).fetchall()
```

Nach `set_status` einfügen:

```python
def set_status_bulk(conn: sqlite3.Connection, job_ids: list[int], status: str) -> int:
    """Setzt den Status mehrerer Stellen in einer Transaktion."""
    if status not in STATUSES:
        raise ValueError(f"Unbekannter Status: {status}")
    if not job_ids:
        return 0
    platzhalter = ",".join("?" * len(job_ids))
    cur = conn.execute(
        f"UPDATE jobs SET status = ? WHERE id IN ({platzhalter})",
        (status, *job_ids),
    )
    conn.commit()
    return cur.rowcount
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (alle Tests der Datei, auch die vorher schon bestehenden)

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/db.py tests/test_db.py
git commit -m "feat(db): Sortierung in suche_jobs, set_status_bulk für Bulk-Aktionen"
```

---

### Task 2: `web/schemas.py` — Pydantic-Modelle für die JSON-API

**Files:**
- Create: `src/bewerbungs_pipeline/web/schemas.py`
- Test: `tests/test_web_schemas.py`

**Interfaces:**
- Consumes: `db.connect`, `db.insert_job`, `db.list_jobs` (Task 1/bestehend); `tasks.start`, `tasks.get` (bestehend, `tasks.Task`-Dataclass mit Feldern `id, beschreibung, status, meldung, ergebnis`).
- Produces: `JobOut`, `SlotOut`, `ApplicationOut`, `ApplicationDetail`, `TaskOut`, `TaskRef` (Pydantic-Modelle); `job_out(row, application_id=None) -> JobOut`; Request-Modelle `StatusUpdate`, `BulkStatusUpdate`, `SlotValue`, `ApplicationCreate`, `FetchRequest`. Diese Namen werden von Task 3–6 importiert.

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`tests/test_web_schemas.py`:

```python
import time
from datetime import UTC, datetime

from bewerbungs_pipeline import db, tasks as tasks_modul
from bewerbungs_pipeline.models import JobItem
from bewerbungs_pipeline.web.schemas import ApplicationOut, TaskOut, job_out


def _job(conn, **overrides):
    base = {
        "title": "Titel",
        "company": "Firma",
        "location": "Ort",
        "url": "https://example.org/1",
        "source": "arbeitsagentur",
        "description_md": "Text.",
        "scraped_at": datetime.now(UTC),
    }
    base.update(overrides)
    db.insert_job(conn, JobItem(**base))
    return db.list_jobs(conn)[0]


def test_job_out_liest_pflichtfelder(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    row = _job(conn)
    out = job_out(row)
    assert out.title == "Titel"
    assert out.application_id is None
    conn.close()


def test_job_out_traegt_application_id_ein(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    row = _job(conn)
    out = job_out(row, application_id=7)
    assert out.application_id == 7
    conn.close()


def test_job_out_gibt_optionale_felder_als_none_weiter(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    row = _job(conn)
    out = job_out(row)
    assert out.salary is None
    assert out.distance_km is None
    conn.close()


def _warte_auf_task(task_id: str, timeout: float = 5.0):
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks_modul.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.01)
    raise AssertionError("Task nicht fertig geworden")


def test_task_out_aus_task_objekt():
    task_id = tasks_modul.start("Testlauf", lambda: "fertig")
    _warte_auf_task(task_id)
    out = TaskOut.model_validate(tasks_modul.get(task_id))
    assert out.status == "fertig"
    assert out.ergebnis == "fertig"


def test_application_out_verschachtelt_slots():
    daten = {
        "id": 1,
        "job_id": 2,
        "template_path": "t.html",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "slots": {
            "motivation": {
                "value": "x",
                "source": "llm",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        },
    }
    out = ApplicationOut.model_validate(daten)
    assert out.slots["motivation"].value == "x"
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `uv run pytest tests/test_web_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bewerbungs_pipeline.web.schemas'`

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/web/schemas.py`:

```python
"""Pydantic-Antwort- und Request-Modelle für die JSON-API unter /api.

sqlite3.Row unterstützt keinen Attributzugriff (nur `row["x"]`) — die
*_out-Hilfsfunktionen gehen deshalb über `dict(row)` statt über
`model_validate(row, from_attributes=True)`.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

Status = Literal["new", "selected", "rejected"]


class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: str
    url: str
    source: str
    status: str
    source_ref: str | None = None
    posted_at: date | None = None
    description_md: str
    job_kind: str | None = None
    employer_kind: str | None = None
    source_partner: str | None = None
    external_host: str | None = None
    homeoffice: str | None = None
    salary: str | None = None
    contract: str | None = None
    worktime: str | None = None
    distance_km: int | None = None
    start_date: date | None = None
    changed_at: datetime | None = None
    street: str | None = None
    plz: str | None = None
    education: str | None = None
    gone_at: datetime | None = None
    scraped_at: datetime
    application_id: int | None = None


def job_out(row, application_id: int | None = None) -> JobOut:
    return JobOut.model_validate({**dict(row), "application_id": application_id})


class SlotOut(BaseModel):
    value: str
    source: str
    updated_at: str


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    template_path: str
    created_at: str
    updated_at: str
    slots: dict[str, SlotOut]


class ApplicationDetail(BaseModel):
    application: ApplicationOut
    stelle: JobOut


class TaskOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    beschreibung: str
    status: str
    meldung: str = ""
    ergebnis: Any = None


class TaskRef(BaseModel):
    task_id: str


class StatusUpdate(BaseModel):
    status: Status


class BulkStatusUpdate(BaseModel):
    ids: list[int]
    status: Status


class SlotValue(BaseModel):
    value: str


class ApplicationCreate(BaseModel):
    job_id: int


class FetchRequest(BaseModel):
    was: str
    wo: str
    umkreis: int = 25
    seit: int | None = None
    ohne_zeitarbeit: bool = False
    nur_arbeit: bool = False
    quelle: Literal["arbeitsagentur", "indeed"] = "arbeitsagentur"
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `uv run pytest tests/test_web_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/web/schemas.py tests/test_web_schemas.py
git commit -m "feat(web): Pydantic-Antwortmodelle für die künftige JSON-API"
```

---

### Task 3: `GET/POST /api/jobs*` — Liste, Detail, Status, Bulk-Status

**Files:**
- Create: `src/bewerbungs_pipeline/web/routes/api_jobs.py`
- Modify: `src/bewerbungs_pipeline/web/app.py`
- Test: `tests/test_api_jobs.py`

**Interfaces:**
- Consumes: `db.suche_jobs`, `db.get_job`, `db.set_status`, `db.set_status_bulk` (Task 1); `applications.get_by_job` (bestehend); `job_out`, `JobOut`, `StatusUpdate`, `BulkStatusUpdate` (Task 2); `get_conn` aus `web/app.py` (bestehend).
- Produces: `router` (FastAPI `APIRouter`, Modulattribut `api_jobs.router`) — wird von Task 4 (im selben Modul erweitert) und von `web/app.py` konsumiert.

- [ ] **Step 1: Fehlschlagende Tests schreiben**

`tests/test_api_jobs.py`:

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


def test_liste_liefert_json(tmp_path):
    cfg = make_cfg(tmp_path)
    seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/jobs")
    assert antwort.status_code == 200
    titel = {job["title"] for job in antwort.json()}
    assert titel == {"Frontend Entwickler (m/w/d)", "Mechatroniker (m/w/d)"}


def test_liste_filtert_nach_volltext(tmp_path):
    cfg = make_cfg(tmp_path)
    seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/jobs", params={"q": "frontend"})
    titel = [job["title"] for job in antwort.json()]
    assert titel == ["Frontend Entwickler (m/w/d)"]


def test_liste_sortiert_nach_firma(tmp_path):
    cfg = make_cfg(tmp_path)
    seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/jobs", params={"sort": "company", "order": "asc"})
    firmen = [job["company"] for job in antwort.json()]
    assert firmen == ["Andere GmbH", "Beispiel AG"]


def test_liste_begrenzt_mit_limit(tmp_path):
    cfg = make_cfg(tmp_path)
    seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/jobs", params={"limit": 1})
    assert len(antwort.json()) == 1


def test_detail_liefert_stelle(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/jobs/{ids['Frontend Entwickler (m/w/d)']}")
    assert antwort.status_code == 200
    body = antwort.json()
    assert body["title"] == "Frontend Entwickler (m/w/d)"
    assert body["application_id"] is None


def test_detail_zeigt_application_id_wenn_vorhanden(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    job_id = ids["Frontend Entwickler (m/w/d)"]
    conn = db.connect(cfg.db_path)
    conn.execute(
        "INSERT INTO applications (job_id, template_path, created_at, updated_at)"
        " VALUES (?, 't.html', '2026-01-01T00:00:00+00:00',"
        " '2026-01-01T00:00:00+00:00')",
        (job_id,),
    )
    conn.commit()
    app_id = conn.execute(
        "SELECT id FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()["id"]
    conn.close()

    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/jobs/{job_id}")
    assert antwort.json()["application_id"] == app_id


def test_detail_unbekannte_stelle_gibt_404(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/jobs/999")
    assert antwort.status_code == 404


def test_status_setzen(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    job_id = ids["Frontend Entwickler (m/w/d)"]
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/api/jobs/{job_id}/status", json={"status": "selected"})
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "selected"
    conn = db.connect(cfg.db_path)
    assert db.get_job(conn, job_id)["status"] == "selected"


def test_status_setzen_unbekannte_stelle_gibt_404(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.post("/api/jobs/999/status", json={"status": "selected"})
    assert antwort.status_code == 404


def test_status_setzen_lehnt_unbekannten_wert_ab(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    job_id = ids["Frontend Entwickler (m/w/d)"]
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/api/jobs/{job_id}/status", json={"status": "geloescht"})
    assert antwort.status_code == 422


def test_status_bulk_aktualisiert_mehrere(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    client = TestClient(create_app(cfg))
    antwort = client.post(
        "/api/jobs/status", json={"ids": list(ids.values()), "status": "rejected"}
    )
    assert antwort.status_code == 200
    assert antwort.json() == {"aktualisiert": 2}
    conn = db.connect(cfg.db_path)
    assert all(r["status"] == "rejected" for r in db.list_jobs(conn))
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `uv run pytest tests/test_api_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bewerbungs_pipeline.web.routes.api_jobs'`
(nach Erstellen der leeren Datei stattdessen: 404 auf alle `/api/jobs*`-Pfade,
da der Router noch nicht in `web/app.py` registriert ist)

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/web/routes/api_jobs.py`:

```python
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ... import applications, db
from ..app import get_conn
from ..schemas import BulkStatusUpdate, JobOut, StatusUpdate, job_out

router = APIRouter(prefix="/api")


@router.get("/jobs")
def liste(
    status: str = "",
    q: str = "",
    ort: str = "",
    verschwunden: str = "",
    sort: str = "id",
    order: str = "desc",
    limit: int | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[JobOut]:
    stellen = db.suche_jobs(
        conn,
        status=status or None,
        q=q or None,
        ort=ort or None,
        mit_verschwundenen=bool(verschwunden),
        sort=sort,
        order=order,
    )
    if limit is not None:
        stellen = stellen[:limit]
    return [job_out(row) for row in stellen]


@router.get("/jobs/{job_id}")
def detail(job_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> JobOut:
    row = db.get_job(conn, job_id)
    if row is None:
        raise HTTPException(404, "Stelle nicht gefunden.")
    bewerbung = applications.get_by_job(conn, job_id)
    return job_out(row, application_id=bewerbung["id"] if bewerbung else None)


@router.post("/jobs/{job_id}/status")
def status_setzen(
    job_id: int, body: StatusUpdate, conn: sqlite3.Connection = Depends(get_conn)
) -> JobOut:
    if db.get_job(conn, job_id) is None:
        raise HTTPException(404, "Stelle nicht gefunden.")
    db.set_status(conn, job_id, body.status)
    return job_out(db.get_job(conn, job_id))


@router.post("/jobs/status")
def status_bulk(
    body: BulkStatusUpdate, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, int]:
    return {"aktualisiert": db.set_status_bulk(conn, body.ids, body.status)}
```

In `src/bewerbungs_pipeline/web/app.py` innerhalb von `create_app`, direkt
neben den bestehenden lokalen Router-Importen (Grund für den lokalen Import
ist dort bereits dokumentiert: zirkulärer Import über `get_conn`/`templates`):

```python
    from .routes import api_jobs as api_jobs_routen
    from .routes import applications as bewerbungs_routen
    from .routes import jobs as jobs_routen
    from .routes import tasks as tasks_routen

    app.include_router(jobs_routen.router)
    app.include_router(tasks_routen.router)
    app.include_router(bewerbungs_routen.router)
    app.include_router(api_jobs_routen.router)
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `uv run pytest tests/test_api_jobs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/web/routes/api_jobs.py \
        src/bewerbungs_pipeline/web/app.py tests/test_api_jobs.py
git commit -m "feat(web): JSON-API für Stellenliste, Detail und Statuswechsel"
```

---

### Task 4: `POST /api/jobs/fetch` — Suche auslösen (Arbeitsagentur + Indeed)

**Files:**
- Modify: `src/bewerbungs_pipeline/web/routes/api_jobs.py`
- Test: `tests/test_api_jobs.py`

**Interfaces:**
- Consumes: `suche_ausfuehren`, `suche_indeed_ausfuehren` aus
  `web/routes/jobs.py` (bestehend, unverändert); `tasks.start` (bestehend);
  `FetchRequest`, `TaskRef` (Task 2).
- Produces: `POST /api/jobs/fetch` → `{"task_id": str}`.

- [ ] **Step 1: Fehlschlagende Tests schreiben**

An den Kopf von `tests/test_api_jobs.py` ergänzen (zu den bestehenden
Imports hinzufügen):

```python
import time

from bewerbungs_pipeline import tasks as tasks_modul
from bewerbungs_pipeline.web.routes import jobs as jobs_routen
```

Ans Ende der Datei anhängen:

```python
def _warte_auf_task(task_id: str, timeout: float = 5.0):
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks_modul.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.01)
    raise AssertionError(f"Vorgang {task_id} wurde nicht fertig")


def test_fetch_liefert_task_id(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path)
    monkeypatch.setattr(jobs_routen.arbeitsagentur, "fetch_jobs", lambda **kw: [])
    monkeypatch.setattr(jobs_routen.arbeitsagentur, "check_alive", lambda refnrs: set())
    client = TestClient(create_app(cfg))
    antwort = client.post(
        "/api/jobs/fetch", json={"was": "Entwickler", "wo": "Mainz", "umkreis": 25}
    )
    assert antwort.status_code == 200
    task_id = antwort.json()["task_id"]
    assert _warte_auf_task(task_id).status == "fertig"


def test_fetch_verzweigt_auf_indeed(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path)
    monkeypatch.setattr(jobs_routen.indeed, "fetch_jobs", lambda **kw: [])
    client = TestClient(create_app(cfg))
    antwort = client.post(
        "/api/jobs/fetch",
        json={"was": "Entwickler", "wo": "Mainz", "umkreis": 25, "quelle": "indeed"},
    )
    assert antwort.status_code == 200
    task_id = antwort.json()["task_id"]
    assert _warte_auf_task(task_id).status == "fertig"
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `uv run pytest tests/test_api_jobs.py -k fetch -v`
Expected: FAIL mit 404 (Route existiert noch nicht)

- [ ] **Step 3: Implementieren**

In `src/bewerbungs_pipeline/web/routes/api_jobs.py` die Imports am Kopf
ersetzen durch:

```python
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ... import applications, db, tasks
from ..app import get_conn
from ..schemas import (
    BulkStatusUpdate,
    FetchRequest,
    JobOut,
    StatusUpdate,
    TaskRef,
    job_out,
)
from .jobs import suche_ausfuehren, suche_indeed_ausfuehren
```

Und ans Ende der Datei (nach `status_bulk`) anfügen:

```python
@router.post("/jobs/fetch")
def fetch(body: FetchRequest, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    if body.quelle == "indeed":
        task_id = tasks.start(
            f"Indeed-Suche „{body.was}“ in {body.wo}",
            suche_indeed_ausfuehren,
            cfg,
            body.was,
            body.wo,
            body.umkreis,
            body.seit,
        )
    else:
        task_id = tasks.start(
            f"Suche „{body.was}“ in {body.wo}",
            suche_ausfuehren,
            cfg,
            body.was,
            body.wo,
            body.umkreis,
            body.seit,
            body.ohne_zeitarbeit,
            body.nur_arbeit,
        )
    return TaskRef(task_id=task_id)
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `uv run pytest tests/test_api_jobs.py -v`
Expected: PASS (komplette Datei, auch die Tests aus Task 3)

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/web/routes/api_jobs.py tests/test_api_jobs.py
git commit -m "feat(web): JSON-Endpunkt für Stellensuche (Arbeitsagentur + Indeed)"
```

---

### Task 5: `GET /api/tasks/{id}`

**Files:**
- Create: `src/bewerbungs_pipeline/web/routes/api_tasks.py`
- Modify: `src/bewerbungs_pipeline/web/app.py`
- Test: `tests/test_api_tasks.py`

**Interfaces:**
- Consumes: `tasks.get` (bestehend); `TaskOut` (Task 2).
- Produces: `router` (Modulattribut `api_tasks.router`) — von `web/app.py`
  konsumiert. Kein `ziel`/`ziel_element`/`ziel_swap` mehr: das Frontend
  pollt selbst und reagiert im eigenen State, ein serverseitiges
  Nachlade-Ziel entfällt ersatzlos (siehe Spec, Abschnitt „API-Schnitt").

- [ ] **Step 1: Fehlschlagende Tests schreiben**

`tests/test_api_tasks.py`:

```python
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from bewerbungs_pipeline import tasks as tasks_modul
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


def _warte_auf_task(task_id: str, timeout: float = 5.0):
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks_modul.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.01)
    raise AssertionError("Task nicht fertig geworden")


def test_status_liefert_laufenden_task(tmp_path):
    cfg = make_cfg(tmp_path)
    gate = threading.Event()
    task_id = tasks_modul.start("Testlauf", lambda: gate.wait() and "fertig")
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/tasks/{task_id}")
    gate.set()
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "läuft"


def test_status_liefert_fertigen_task(tmp_path):
    cfg = make_cfg(tmp_path)
    task_id = tasks_modul.start("Testlauf", lambda: "fertig")
    _warte_auf_task(task_id)
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/tasks/{task_id}")
    assert antwort.status_code == 200
    body = antwort.json()
    assert body["status"] == "fertig"
    assert body["ergebnis"] == "fertig"


def test_status_unbekannter_task_gibt_404(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/tasks/gibtsnicht")
    assert antwort.status_code == 404
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `uv run pytest tests/test_api_tasks.py -v`
Expected: FAIL — 404 auf `/api/tasks/*`, da weder Modul noch Router existieren

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/web/routes/api_tasks.py`:

```python
from fastapi import APIRouter, HTTPException

from ... import tasks as tasks_modul
from ..schemas import TaskOut

router = APIRouter(prefix="/api")


@router.get("/tasks/{task_id}")
def status(task_id: str) -> TaskOut:
    task = tasks_modul.get(task_id)
    if task is None:
        raise HTTPException(404, "Vorgang nicht gefunden.")
    return TaskOut.model_validate(task)
```

In `src/bewerbungs_pipeline/web/app.py` den lokalen Import-Block erweitern:

```python
    from .routes import api_jobs as api_jobs_routen
    from .routes import api_tasks as api_tasks_routen
    from .routes import applications as bewerbungs_routen
    from .routes import jobs as jobs_routen
    from .routes import tasks as tasks_routen

    app.include_router(jobs_routen.router)
    app.include_router(tasks_routen.router)
    app.include_router(bewerbungs_routen.router)
    app.include_router(api_jobs_routen.router)
    app.include_router(api_tasks_routen.router)
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `uv run pytest tests/test_api_tasks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/web/routes/api_tasks.py \
        src/bewerbungs_pipeline/web/app.py tests/test_api_tasks.py
git commit -m "feat(web): JSON-Endpunkt für Task-Status"
```

---

### Task 6: `/api/applications/*` — Erzeugen, Detail, Slots, Regenerieren, Export

**Files:**
- Create: `src/bewerbungs_pipeline/web/routes/api_applications.py`
- Modify: `src/bewerbungs_pipeline/web/app.py`
- Test: `tests/test_api_applications.py`

**Interfaces:**
- Consumes: `bewerbung_erzeugen`, `exportieren_lauf`, `slot_erzeugen` aus
  `web/routes/applications.py` (bestehend, unverändert);
  `applications.get`, `applications.set_slot`, `applications.ApplicationError`,
  `db.get_job` (bestehend); `ApplicationOut`, `ApplicationDetail`, `SlotOut`,
  `SlotValue`, `ApplicationCreate`, `TaskRef` (Task 2); `get_conn`
  (bestehend).
- Produces: `router` (Modulattribut `api_applications.router`) — von
  `web/app.py` konsumiert. `/applications/{id}/preview` bleibt unverändert
  in `web/routes/applications.py` — kein API-Äquivalent nötig (siehe Spec).

- [ ] **Step 1: Fehlschlagende Tests schreiben**

`tests/test_api_applications.py`:

```python
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from bewerbungs_pipeline import applications, db
from bewerbungs_pipeline import tasks as tasks_modul
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


def _warte_auf_task(task_id: str, timeout: float = 60.0):
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks_modul.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.02)
    raise AssertionError(f"Vorgang {task_id} wurde nicht fertig")


def test_erzeugen_liefert_task_id_und_legt_datensatz_an(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import applications as app_routen

    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    monkeypatch.setattr(app_routen, "make_client", lambda *a, **k: FakeClient(GOOD))
    client = TestClient(create_app(cfg))
    antwort = client.post("/api/applications", json={"job_id": job_id})
    assert antwort.status_code == 200
    task = _warte_auf_task(antwort.json()["task_id"])
    assert task.status == "fertig"
    conn = db.connect(cfg.db_path)
    assert applications.get_by_job(conn, job_id) is not None


def test_detail_liefert_bewerbung_und_stelle(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/applications/{app_id}")
    assert antwort.status_code == 200
    body = antwort.json()
    assert body["stelle"]["company"] == "Beispiel AG"
    assert (
        body["application"]["slots"]["motivation"]["value"]
        == "Wartung und Service sind mein Feld."
    )


def test_detail_unbekannte_bewerbung_gibt_404(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/applications/999")
    assert antwort.status_code == 404


def test_slot_lesen(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/applications/{app_id}/slots/motivation")
    assert antwort.status_code == 200
    assert antwort.json()["value"] == "Wartung und Service sind mein Feld."


def test_slot_lesen_unbekannt_gibt_404(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/applications/{app_id}/slots/gibtsnicht")
    assert antwort.status_code == 404


def test_slot_speichern(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(
        f"/api/applications/{app_id}/slots/motivation",
        json={"value": "Neu von Hand."},
    )
    assert antwort.status_code == 200
    assert antwort.json()["source"] == "manuell"
    conn = db.connect(cfg.db_path)
    assert (
        applications.get(conn, app_id)["slots"]["motivation"]["value"]
        == "Neu von Hand."
    )


def test_slot_speichern_unbekannt_gibt_400(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(
        f"/api/applications/{app_id}/slots/gibtsnicht", json={"value": "x"}
    )
    assert antwort.status_code == 400


def test_slot_neu_erzeugen_liefert_task_id(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import applications as app_routen

    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    monkeypatch.setattr(
        app_routen, "make_client", lambda *a, **k: FakeClient({"motivation": "Neu."})
    )
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/api/applications/{app_id}/slots/motivation/regenerate")
    assert antwort.status_code == 200
    task = _warte_auf_task(antwort.json()["task_id"])
    assert task.status == "fertig"


def test_export_liefert_task_id(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/api/applications/{app_id}/export")
    assert antwort.status_code == 200
    task = _warte_auf_task(antwort.json()["task_id"])
    assert task.status == "fertig", task.meldung
    assert (cfg.out_dir / "beispiel-ag" / "index.html").exists()
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `uv run pytest tests/test_api_applications.py -v`
Expected: FAIL — `ModuleNotFoundError` bzw. 404 auf alle `/api/applications*`-Pfade

- [ ] **Step 3: Implementieren**

`src/bewerbungs_pipeline/web/routes/api_applications.py`:

```python
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ... import applications, db, tasks
from ...applications import ApplicationError
from ..app import get_conn
from ..schemas import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationOut,
    SlotOut,
    SlotValue,
    TaskRef,
    job_out,
)
from .applications import bewerbung_erzeugen, exportieren_lauf, slot_erzeugen

router = APIRouter(prefix="/api")


@router.post("/applications")
def erzeugen(body: ApplicationCreate, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    task_id = tasks.start(
        "Bewerbung wird geschrieben", bewerbung_erzeugen, cfg, body.job_id
    )
    return TaskRef(task_id=task_id)


@router.get("/applications/{app_id}")
def seite(
    app_id: int, conn: sqlite3.Connection = Depends(get_conn)
) -> ApplicationDetail:
    bewerbung = applications.get(conn, app_id)
    if bewerbung is None:
        raise HTTPException(404, "Bewerbung nicht gefunden.")
    stelle = db.get_job(conn, bewerbung["job_id"])
    return ApplicationDetail(
        application=ApplicationOut.model_validate(bewerbung), stelle=job_out(stelle)
    )


@router.get("/applications/{app_id}/slots/{slot}")
def slot_fragment(
    app_id: int, slot: str, conn: sqlite3.Connection = Depends(get_conn)
) -> SlotOut:
    bewerbung = applications.get(conn, app_id)
    if bewerbung is None:
        raise HTTPException(404, "Bewerbung nicht gefunden.")
    daten = bewerbung["slots"].get(slot)
    if daten is None:
        raise HTTPException(404, f"Unbekannter Slot: {slot}")
    return SlotOut.model_validate(daten)


@router.put("/applications/{app_id}/slots/{slot}")
def slot_speichern(
    app_id: int,
    slot: str,
    body: SlotValue,
    conn: sqlite3.Connection = Depends(get_conn),
) -> SlotOut:
    try:
        applications.set_slot(conn, app_id, slot, body.value)
    except ApplicationError as exc:
        raise HTTPException(400, str(exc)) from exc
    daten = applications.get(conn, app_id)["slots"][slot]
    return SlotOut.model_validate(daten)


@router.post("/applications/{app_id}/slots/{slot}/regenerate")
def slot_neu(app_id: int, slot: str, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    task_id = tasks.start(
        f"Block „{slot}“ wird neu geschrieben", slot_erzeugen, cfg, app_id, slot
    )
    return TaskRef(task_id=task_id)


@router.post("/applications/{app_id}/export")
def exportieren(app_id: int, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    task_id = tasks.start("Bewerbung wird exportiert", exportieren_lauf, cfg, app_id)
    return TaskRef(task_id=task_id)
```

In `src/bewerbungs_pipeline/web/app.py` den lokalen Import-Block ein
letztes Mal erweitern:

```python
    from .routes import api_applications as api_applications_routen
    from .routes import api_jobs as api_jobs_routen
    from .routes import api_tasks as api_tasks_routen
    from .routes import applications as bewerbungs_routen
    from .routes import jobs as jobs_routen
    from .routes import tasks as tasks_routen

    app.include_router(jobs_routen.router)
    app.include_router(tasks_routen.router)
    app.include_router(bewerbungs_routen.router)
    app.include_router(api_jobs_routen.router)
    app.include_router(api_tasks_routen.router)
    app.include_router(api_applications_routen.router)
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `uv run pytest tests/test_api_applications.py -v`
Expected: PASS

- [ ] **Step 5: Gesamte Suite laufen lassen**

Run: `uv run pytest`
Expected: PASS — alle bestehenden Tests (inkl. `test_web_*.py`, die die
unveränderte HTML-Oberfläche prüfen) und alle neuen `test_api_*.py`/
`test_web_schemas.py`/erweiterten `test_db.py`-Tests sind grün.

- [ ] **Step 6: Commit**

```bash
git add src/bewerbungs_pipeline/web/routes/api_applications.py \
        src/bewerbungs_pipeline/web/app.py tests/test_api_applications.py
git commit -m "feat(web): JSON-API für Bewerbungen (Erzeugen, Slots, Export)"
```

---

## Phase-1-Abschlusskriterium

Nach Task 6: `uv run jobs serve` startet unverändert, `/` zeigt weiterhin
die bestehende HTMX-Oberfläche, und sämtliche 14 Operationen sind zusätzlich
unter `/api/*` als JSON erreichbar und getestet. Damit ist die Grundlage für
Phase 2 (React-Frontend gegen diese API) gelegt — deren Plan folgt separat,
sobald die hier entstandenen JSON-Formen als stabil gelten.

## Selbstreview (durchgeführt)

- **Spec-Abdeckung:** Alle 14 in der Spec-Tabelle „API-Schnitt" gelisteten
  Endpunkte sind auf Tasks 3/4/5/6 verteilt; `sort`/`order`-Whitelist
  (Task 1), Bulk-Status (Task 3) und die ersatzlose Streichung von
  `ziel`/`ziel_element`/`ziel_swap` (Task 5) sind mit abgedeckt.
- **Platzhalter-Scan:** keine TBD/TODO; jeder Schritt enthält lauffähigen
  Code statt Beschreibung.
- **Typkonsistenz geprüft:** `job_out(row, application_id=None)` (Task 2)
  wird in Task 3 und Task 6 mit identischer Signatur aufgerufen;
  `bewerbung_erzeugen`/`exportieren_lauf`/`slot_erzeugen` werden mit exakt
  den Parametern aufgerufen, die ihre bestehenden Definitionen in
  `web/routes/applications.py` erwarten; `TaskRef.task_id` wird überall
  gleich benannt (nicht z. B. `id` in einer Antwort und `task_id` in einer
  anderen).
