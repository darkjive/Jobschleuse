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
