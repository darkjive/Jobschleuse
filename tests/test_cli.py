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
