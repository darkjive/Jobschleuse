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
    monkeypatch.setattr(jobs_routen.arbeitsagentur, "fetch_jobs", lambda **kw: [])
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
