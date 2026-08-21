import re
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from bewerbungs_pipeline import db
from bewerbungs_pipeline import tasks as tasks_modul
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


def _warte_auf_task(task_id: str, timeout: float = 5.0) -> tasks_modul.Task:
    """Wartet, bis der Hintergrundlauf durch ist.

    Notwendig, weil monkeypatch den Fake am Testende zurücknimmt: liefe der
    Thread erst danach, ginge ein echter Netzaufruf an die Arbeitsagentur
    raus — und Tests dürfen nicht ins Netz.
    """
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks_modul.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.01)
    raise AssertionError(f"Vorgang {task_id} wurde nicht fertig")


def test_suche_ausfuehren_schreibt_stellen(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import jobs as jobs_routen

    cfg = make_cfg(tmp_path)
    db.connect(cfg.db_path).close()

    def fake_fetch(**kwargs):
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
    monkeypatch.setattr(jobs_routen.arbeitsagentur, "check_alive", lambda refnrs: set())
    meldung = jobs_routen.suche_ausfuehren(cfg, "Entwickler", "Mainz", 25, None, False, False)

    assert "1" in meldung
    conn = db.connect(cfg.db_path)
    assert any(r["title"] == "Neue Stelle (m/w/d)" for r in db.list_jobs(conn))


def test_fetch_liefert_fortschritt_mit_task_id(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import jobs as jobs_routen

    cfg = make_cfg(tmp_path)
    monkeypatch.setattr(jobs_routen.arbeitsagentur, "fetch_jobs", lambda **kw: [])
    monkeypatch.setattr(jobs_routen.arbeitsagentur, "check_alive", lambda refnrs: set())
    client = TestClient(create_app(cfg))
    antwort = client.post(
        "/jobs/fetch", data={"was": "Entwickler", "wo": "Mainz", "umkreis": "25"}
    )
    assert antwort.status_code == 200
    assert "/tasks/" in antwort.text

    task_id = re.search(r"/tasks/(\w+)", antwort.text).group(1)
    assert _warte_auf_task(task_id).status == "fertig"


def test_task_status_unbekannt_meldet_deutsch(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/tasks/gibtsnicht")
    assert antwort.status_code == 404
    assert "nicht gefunden" in antwort.text


def test_task_status_verwirft_fremdes_ziel(tmp_path):
    cfg = make_cfg(tmp_path)
    task_id = tasks_modul.start("Testlauf", lambda: "fertig")
    _warte_auf_task(task_id)
    client = TestClient(create_app(cfg))
    antwort = client.get(
        f"/tasks/{task_id}",
        params={"ziel": "https://boese.example/x", "ziel_element": "body"},
    )
    assert antwort.status_code == 200
    assert "boese.example" not in antwort.text
    assert "hx-get" not in antwort.text


def test_task_status_verwirft_fremden_swap(tmp_path):
    cfg = make_cfg(tmp_path)
    task_id = tasks_modul.start("Testlauf", lambda: "fertig")
    _warte_auf_task(task_id)
    client = TestClient(create_app(cfg))
    antwort = client.get(
        f"/tasks/{task_id}",
        params={"ziel": "/jobs", "ziel_element": "#stellenliste", "ziel_swap": "delete"},
    )
    assert 'hx-swap="innerHTML"' in antwort.text
    assert "delete" not in antwort.text


def test_suche_markiert_verschwundene(tmp_path, monkeypatch):
    from bewerbungs_pipeline.sources import arbeitsagentur
    from bewerbungs_pipeline.web.routes import jobs as jobs_routen

    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at) VALUES ('http://alt', 'h1', 'ref-weg', 'Alte Stelle',"
        " 'Firma', 'Ort', 'arbeitsagentur', '2026-07-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(arbeitsagentur, "fetch_jobs", lambda **kw: [])
    monkeypatch.setattr(arbeitsagentur, "check_alive", lambda refnrs: {"ref-weg"})

    meldung = jobs_routen.suche_ausfuehren(cfg, "Frontend", "Darmstadt", 50, None, False, False)
    assert "1 nicht mehr verfügbar" in meldung

    conn = db.connect(cfg.db_path)
    zeile = conn.execute("SELECT gone_at FROM jobs WHERE source_ref = 'ref-weg'").fetchone()
    assert zeile["gone_at"] is not None
    conn.close()


def test_liste_blendet_verschwundene_aus(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    conn = db.connect(cfg.db_path)
    conn.execute("UPDATE jobs SET gone_at = '2026-08-13T00:00:00+00:00' WHERE id = ?",
                 (list(ids.values())[0],))
    conn.commit()
    conn.close()

    client = TestClient(create_app(cfg))
    ohne = client.get("/jobs").text
    mit = client.get("/jobs?verschwunden=1").text
    assert ohne.count("stelle__titel") == 1
    assert mit.count("stelle__titel") == 2


def test_task_status_reicht_outerhtml_durch(tmp_path):
    cfg = make_cfg(tmp_path)
    task_id = tasks_modul.start("Testlauf", lambda: "fertig")
    _warte_auf_task(task_id)
    client = TestClient(create_app(cfg))
    antwort = client.get(
        f"/tasks/{task_id}",
        params={"ziel": "/x", "ziel_element": "#slot-titel", "ziel_swap": "outerHTML"},
    )
    assert 'hx-swap="outerHTML"' in antwort.text


def test_liste_zeigt_kennzeichen(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at, source_partner, employer_kind, homeoffice, salary,"
        " contract, distance_km) VALUES ('http://a', 'h1', 'ref-a', 'Titel', 'Firma',"
        " 'Ort', 'arbeitsagentur', '2026-08-13T00:00:00+00:00', 'XING GmbH & Co. KG',"
        " 'vermittler', 'NACH_VEREINBARUNG', 'ab 19,78 €/h', 'unbefristet', 42)"
    )
    conn.commit()
    conn.close()

    text = TestClient(create_app(cfg)).get("/jobs").text
    assert "XING GmbH &amp; Co. KG" in text
    assert "Vermittler" in text
    assert "Homeoffice" in text
    assert "ab 19,78" in text
    assert "42 km" in text


def test_liste_zeigt_leere_felder_nicht(tmp_path):
    """Eine duenn belegte Stelle bekommt keine Kennzeichen mit 'None' darin."""
    cfg = make_cfg(tmp_path)
    seed(cfg)
    text = TestClient(create_app(cfg)).get("/jobs").text
    assert "None" not in text
    assert "Vermittler" not in text


def test_liste_markiert_verschwundene(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    conn = db.connect(cfg.db_path)
    conn.execute("UPDATE jobs SET gone_at = '2026-08-13T00:00:00+00:00' WHERE id = ?",
                 (list(ids.values())[0],))
    conn.commit()
    conn.close()

    text = TestClient(create_app(cfg)).get("/jobs?verschwunden=1").text
    assert "nicht mehr verfügbar" in text
    assert "stelle--weg" in text


def test_detail_zeigt_faktenliste(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at, street, plz, start_date, education, worktime,"
        " source_partner) VALUES ('http://a', 'h1', 'ref-a', 'Titel', 'Firma', 'Ort',"
        " 'arbeitsagentur', '2026-08-13T00:00:00+00:00', 'Lyoner Str. 12', '60528',"
        " '2026-09-01', 'MITTLERE_REIFE_MITTLERER_BILDUNGSABSCHLUSS', 'Vollzeit',"
        " 'XING GmbH & Co. KG')"
    )
    conn.commit()
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    conn.close()

    text = TestClient(create_app(cfg)).get(f"/jobs/{job_id}").text
    assert "Lyoner Str. 12" in text
    assert "60528" in text
    assert "Vollzeit" in text
    assert "XING GmbH &amp; Co. KG" in text


def test_detail_warnt_bei_verschwundener_stelle(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    job_id = list(ids.values())[0]
    conn = db.connect(cfg.db_path)
    conn.execute("UPDATE jobs SET gone_at = '2026-08-13T00:00:00+00:00' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    text = TestClient(create_app(cfg)).get(f"/jobs/{job_id}").text
    assert "nicht mehr verfügbar" in text


def test_suchformular_hat_neue_felder(tmp_path):
    text = TestClient(create_app(make_cfg(tmp_path))).get("/").text
    assert 'name="seit"' in text
    assert 'name="ohne_zeitarbeit"' in text
    assert 'name="nur_arbeit"' in text
    assert 'name="verschwunden"' in text
