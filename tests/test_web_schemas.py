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
