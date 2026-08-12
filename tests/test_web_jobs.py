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
