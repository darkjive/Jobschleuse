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
