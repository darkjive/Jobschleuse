import io
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


def seed_many(db_path, titel: list[str], company: str = "AC Motoren GmbH") -> list[int]:
    conn = db.connect(db_path)
    for i, t in enumerate(titel):
        db.insert_job(
            conn,
            JobItem(
                title=t,
                company=company,
                location="Darmstadt",
                url=f"https://example.org/job/{i}",
                source="arbeitsagentur",
                scraped_at=datetime.now(UTC),
            ),
        )
    ids = [r["id"] for r in db.list_jobs(conn)]
    conn.close()
    return ids


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


LIST_FELDER = {
    "id", "title", "company", "location", "source", "url", "posted_at", "status",
    "homeoffice", "salary", "distance_km", "score", "tags",
}


def test_list_json_kompakte_felder(env, capsys):
    seed(env / "jobs.db")
    assert cli.main(["list", "--json"]) == 0
    daten = json.loads(capsys.readouterr().out)
    assert len(daten) == 1
    assert set(daten[0]) == LIST_FELDER
    assert daten[0]["tags"] == []
    assert daten[0]["score"] is None


def test_list_json_leer(env, capsys):
    seed(env / "jobs.db")
    assert cli.main(["list", "--json", "--status", "selected"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_list_json_umlaute_roh(env, capsys):
    seed_many(env / "jobs.db", ["Dev"], company="Müller GmbH")
    cli.main(["list", "--json"])
    out = capsys.readouterr().out
    assert "Müller" in out
    assert json.loads(out)[0]["company"] == "Müller GmbH"


def test_list_blendet_verschwundene_standardmaessig_aus(env, capsys):
    job_id = seed(env / "jobs.db")
    conn = db.connect(env / "jobs.db")
    conn.execute(
        "UPDATE jobs SET gone_at = '2026-09-01T00:00:00+00:00' WHERE id = ?", (job_id,)
    )
    conn.commit()
    conn.close()
    cli.main(["list", "--json"])
    assert json.loads(capsys.readouterr().out) == []
    cli.main(["list", "--json", "--include-gone"])
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_list_filter_und_score_sortierung(env, capsys):
    a, b, c = seed_many(env / "jobs.db", ["Python Dev", "React Dev", "Koch"])
    conn = db.connect(env / "jobs.db")
    db.set_rating(conn, a, 60, "ok", ["python"])
    db.set_rating(conn, b, 90, "super", ["react"])
    conn.close()

    cli.main(["list", "--json", "--sort", "score"])
    assert [j["id"] for j in json.loads(capsys.readouterr().out)] == [b, a, c]

    cli.main(["list", "--json", "--min-score", "70"])
    daten = json.loads(capsys.readouterr().out)
    assert [j["id"] for j in daten] == [b]
    assert daten[0]["tags"] == ["react"]

    cli.main(["list", "--json", "--unrated"])
    assert [j["id"] for j in json.loads(capsys.readouterr().out)] == [c]

    cli.main(["list", "--json", "--query", "dev", "--limit", "1"])
    assert [j["id"] for j in json.loads(capsys.readouterr().out)] == [a]


def test_list_negatives_limit_ist_aufruffehler(env, capsys):
    seed(env / "jobs.db")
    assert cli.main(["list", "--limit", "-1"]) == 2
    assert capsys.readouterr().out == ""


def test_list_zeigt_score_spalte(env, capsys):
    job_id = seed(env / "jobs.db")
    conn = db.connect(env / "jobs.db")
    db.set_rating(conn, job_id, 77, "", [])
    conn.close()
    cli.main(["list"])
    out = capsys.readouterr().out
    assert "Score" in out
    assert "77" in out


def test_show_json_in_reihenfolge_der_ids(env, capsys):
    a, b = seed_many(env / "jobs.db", ["Erste", "Zweite"])
    assert cli.main(["show", str(b), str(a), "--json"]) == 0
    daten = json.loads(capsys.readouterr().out)
    assert [j["id"] for j in daten] == [b, a]
    assert "description_md" in daten[0]
    assert "score_reason" in daten[0]
    assert daten[0]["tags"] == []


def test_show_unbekannte_id(env, capsys):
    a = seed(env / "jobs.db")
    assert cli.main(["show", str(a), "999", "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "999" in captured.err


def test_show_menschlich(env, capsys):
    job_id = seed(env / "jobs.db")
    conn = db.connect(env / "jobs.db")
    db.update_description(conn, job_id, "Wir suchen Verstärkung.")
    conn.close()
    assert cli.main(["show", str(job_id)]) == 0
    out = capsys.readouterr().out
    assert "Mechatroniker (m/w/d)" in out
    assert "Wir suchen Verstärkung." in out


def _bewertung(env, job_id):
    conn = db.connect(env / "jobs.db")
    row = db.get_job(conn, job_id)
    conn.close()
    return row["score"], row["score_reason"], json.loads(row["tags"] or "[]")


def test_rate_einzeln(env, capsys):
    job_id = seed(env / "jobs.db")
    rc = cli.main(
        ["rate", str(job_id), "--score", "85", "--reason", "passt", "--tags", "Python, react,,"]
    )
    assert rc == 0
    assert _bewertung(env, job_id) == (85, "passt", ["python", "react"])
    assert "1 Stellen bewertet." in capsys.readouterr().out


def test_rate_einzeln_ungueltiger_score(env, capsys):
    job_id = seed(env / "jobs.db")
    assert cli.main(["rate", str(job_id), "--score", "101", "--reason", "x"]) == 1
    assert _bewertung(env, job_id)[0] is None


def test_rate_einzeln_unbekannte_id(env, capsys):
    seed(env / "jobs.db")
    assert cli.main(["rate", "999", "--score", "50", "--reason", "x"]) == 1
    assert "999" in capsys.readouterr().err


def test_rate_stdin(env, monkeypatch, capsys):
    a, b = seed_many(env / "jobs.db", ["A", "B"])
    eingabe = (
        json.dumps({"id": a, "score": 70, "reason": "gut", "tags": ["python"]}) + "\r\n"
        + "\n"
        + json.dumps({"id": b, "score": 20, "reason": "nein"}) + "\n"
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(eingabe))
    assert cli.main(["rate", "--stdin", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"rated": 2}
    assert _bewertung(env, a) == (70, "gut", ["python"])
    assert _bewertung(env, b) == (20, "nein", [])


def test_rate_stdin_doppelte_id_letzte_gewinnt(env, monkeypatch, capsys):
    a = seed(env / "jobs.db")
    eingabe = (
        json.dumps({"id": a, "score": 10, "reason": "erst"}) + "\n"
        + json.dumps({"id": a, "score": 90, "reason": "dann"}) + "\n"
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(eingabe))
    assert cli.main(["rate", "--stdin", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"rated": 2}
    assert _bewertung(env, a)[:2] == (90, "dann")


@pytest.mark.parametrize(
    "zweite_zeile",
    [
        "kein json",
        '{"id": 999, "score": 50, "reason": "x"}',
        '{"id": 1, "score": true, "reason": "x"}',
        '{"id": 1, "score": 50.5, "reason": "x"}',
        '{"id": 1, "score": 50}',
        '{"id": 1, "score": 50, "reason": "x", "tags": "python"}',
        "[1, 2]",
    ],
)
def test_rate_stdin_alles_oder_nichts(env, monkeypatch, capsys, zweite_zeile):
    a = seed(env / "jobs.db")
    eingabe = json.dumps({"id": a, "score": 70, "reason": "gut"}) + "\n" + zweite_zeile + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(eingabe))
    assert cli.main(["rate", "--stdin"]) == 1
    captured = capsys.readouterr()
    assert "Zeile 2" in captured.err
    assert captured.out == ""
    assert _bewertung(env, a)[0] is None


def test_rate_braucht_genau_eine_form(env, capsys):
    job_id = seed(env / "jobs.db")
    assert cli.main(["rate"]) == 2
    assert cli.main(["rate", "--stdin", str(job_id)]) == 2
    assert cli.main(["rate", str(job_id), "--score", "50"]) == 2
