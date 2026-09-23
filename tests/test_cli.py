import json
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
    monkeypatch.setattr(cli.arbeitsagentur, "check_alive", lambda refnrs: set())
    rc = cli.main(["fetch", "--what", "Elektroniker", "--where", "Frankfurt"])
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


def test_check_markiert_verschwundene(env, monkeypatch, capsys):
    conn = db.connect(env / "jobs.db")
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at) VALUES ('http://a', 'h1', 'ref-weg', 'Titel', 'Firma',"
        " 'Ort', 'arbeitsagentur', '2026-07-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(cli.arbeitsagentur, "check_alive", lambda refnrs: {"ref-weg"})
    assert cli.main(["check"]) == 0
    assert (
        "1 Stellen sind bei der Quelle nicht mehr vorhanden." in capsys.readouterr().out
    )


def test_fetch_reicht_neue_optionen_durch(env, monkeypatch, capsys):
    gesehen = {}

    def falsches_holen(**kw):
        gesehen.update(kw)
        return []

    monkeypatch.setattr(cli.arbeitsagentur, "fetch_jobs", falsches_holen)
    monkeypatch.setattr(cli.arbeitsagentur, "check_alive", lambda refnrs: set())
    cli.main(
        [
            "fetch",
            "--what",
            "Frontend",
            "--where",
            "Darmstadt",
            "--radius",
            "30",
            "--since",
            "7",
            "--no-temp-agency",
            "--jobs-only",
        ]
    )
    assert gesehen["umkreis"] == 30
    assert gesehen["veroeffentlicht_seit"] == 7
    assert gesehen["ohne_zeitarbeit"] is True
    assert gesehen["nur_arbeit"] is True


def test_fetch_json(env, monkeypatch, capsys):
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
    monkeypatch.setattr(cli.arbeitsagentur, "check_alive", lambda refnrs: set())
    rc = cli.main(["fetch", "--what", "X", "--where", "Y", "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"fetched": 1, "new": 1, "gone": 0}


def test_fetch_alte_deutsche_optionen_sind_weg(env):
    with pytest.raises(SystemExit) as fehler:
        cli.main(["fetch", "--was", "X", "--wo", "Y"])
    assert fehler.value.code == 2


def test_fetch_indeed_optionen_und_json(env, monkeypatch, capsys):
    from bewerbungs_pipeline.sources import indeed

    gesehen = {}

    def falsches_holen(**kw):
        gesehen.update(kw)
        return []

    monkeypatch.setattr(indeed, "fetch_jobs", falsches_holen)
    rc = cli.main(
        ["fetch-indeed", "--what", "Dev", "--where", "Darmstadt", "--since", "2",
         "--limit", "10", "--json"]
    )
    assert rc == 0
    assert gesehen["ergebnisse"] == 10
    assert gesehen["seit_stunden"] == 48
    assert json.loads(capsys.readouterr().out) == {"fetched": 0, "new": 0}


def test_check_json(env, monkeypatch, capsys):
    conn = db.connect(env / "jobs.db")
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at) VALUES ('http://a', 'h1', 'ref-weg', 'Titel', 'Firma',"
        " 'Ort', 'arbeitsagentur', '2026-07-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(cli.arbeitsagentur, "check_alive", lambda refnrs: {"ref-weg"})
    assert cli.main(["check", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"checked": 1, "gone": 1}
