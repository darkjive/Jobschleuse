import threading
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


def test_verbindung_darf_thread_wechseln(tmp_path):
    """FastAPI öffnet die Anfrage-Verbindung in einem Arbeits-Thread und
    schließt sie in einem anderen. sqlite3 muss das zulassen, sonst endet
    jede Anfrage im Traceback."""
    conn = db.connect(tmp_path / "jobs.db")
    fehler = []

    def schliessen():
        try:
            conn.close()
        except Exception as exc:
            fehler.append(exc)

    thread = threading.Thread(target=schliessen)
    thread.start()
    thread.join()
    assert fehler == []
