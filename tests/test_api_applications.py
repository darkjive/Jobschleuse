import json
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from bewerbungs_pipeline import applications, db
from bewerbungs_pipeline import tasks as tasks_modul
from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.models import JobItem
from bewerbungs_pipeline.web.app import create_app

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"

GOOD = {
    "titel": "Bewerbung — Beispiel AG",
    "firma": "Beispiel AG",
    "einstieg": "Ihre Anzeige hat mich überzeugt.",
    "motivation": "Wartung und Service sind mein Feld.",
}


class FakeClient:
    def __init__(self, payload: dict):
        message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: response)
        )


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


def seed(cfg) -> int:
    conn = db.connect(cfg.db_path)
    db.insert_job(
        conn,
        JobItem(
            title="Servicetechniker (m/w/d)",
            company="Beispiel AG",
            location="Frankfurt am Main",
            url="https://example.org/job/1",
            source="arbeitsagentur",
            description_md="Wir suchen Verstärkung im Service.",
            scraped_at=datetime.now(UTC),
        ),
    )
    job_id = db.list_jobs(conn)[0]["id"]
    db.set_status(conn, job_id, "selected")
    conn.close()
    return job_id


def bewerbung_anlegen(cfg, job_id) -> int:
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    conn.close()
    return app_id


def _warte_auf_task(task_id: str, timeout: float = 60.0):
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks_modul.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.02)
    raise AssertionError(f"Vorgang {task_id} wurde nicht fertig")


def test_erzeugen_liefert_task_id_und_legt_datensatz_an(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import api_applications as app_routen

    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    monkeypatch.setattr(app_routen, "make_client", lambda *a, **k: FakeClient(GOOD))
    client = TestClient(create_app(cfg))
    antwort = client.post("/api/applications", json={"job_id": job_id})
    assert antwort.status_code == 200
    task = _warte_auf_task(antwort.json()["task_id"])
    assert task.status == "fertig"
    conn = db.connect(cfg.db_path)
    assert applications.get_by_job(conn, job_id) is not None


def test_detail_liefert_bewerbung_und_stelle(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/applications/{app_id}")
    assert antwort.status_code == 200
    body = antwort.json()
    assert body["stelle"]["company"] == "Beispiel AG"
    assert (
        body["application"]["slots"]["motivation"]["value"]
        == "Wartung und Service sind mein Feld."
    )


def test_detail_unbekannte_bewerbung_gibt_404(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/applications/999")
    assert antwort.status_code == 404


def test_slot_lesen(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/applications/{app_id}/slots/motivation")
    assert antwort.status_code == 200
    assert antwort.json()["value"] == "Wartung und Service sind mein Feld."


def test_slot_lesen_unbekannt_gibt_404(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/applications/{app_id}/slots/gibtsnicht")
    assert antwort.status_code == 404


def test_slot_speichern(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(
        f"/api/applications/{app_id}/slots/motivation",
        json={"value": "Neu von Hand."},
    )
    assert antwort.status_code == 200
    assert antwort.json()["source"] == "manuell"
    conn = db.connect(cfg.db_path)
    assert (
        applications.get(conn, app_id)["slots"]["motivation"]["value"]
        == "Neu von Hand."
    )


def test_slot_speichern_unbekannt_gibt_400(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(
        f"/api/applications/{app_id}/slots/gibtsnicht", json={"value": "x"}
    )
    assert antwort.status_code == 400


def test_slot_neu_erzeugen_liefert_task_id(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import api_applications as app_routen

    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    monkeypatch.setattr(
        app_routen, "make_client", lambda *a, **k: FakeClient({"motivation": "Neu."})
    )
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/api/applications/{app_id}/slots/motivation/regenerate")
    assert antwort.status_code == 200
    task = _warte_auf_task(antwort.json()["task_id"])
    assert task.status == "fertig"


def test_export_liefert_task_id(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/api/applications/{app_id}/export")
    assert antwort.status_code == 200
    task = _warte_auf_task(antwort.json()["task_id"])
    assert task.status == "fertig", task.meldung
    assert (cfg.out_dir / "beispiel-ag" / "index.html").exists()
