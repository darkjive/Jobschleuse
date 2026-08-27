import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from bewerbungs_pipeline import tasks as tasks_modul
from bewerbungs_pipeline.config import Config
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


def _warte_auf_task(task_id: str, timeout: float = 5.0):
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks_modul.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.01)
    raise AssertionError("Task nicht fertig geworden")


def test_status_liefert_laufenden_task(tmp_path):
    cfg = make_cfg(tmp_path)
    gate = threading.Event()
    task_id = tasks_modul.start("Testlauf", lambda: gate.wait() and "fertig")
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/tasks/{task_id}")
    gate.set()
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "läuft"


def test_status_liefert_fertigen_task(tmp_path):
    cfg = make_cfg(tmp_path)
    task_id = tasks_modul.start("Testlauf", lambda: "fertig")
    _warte_auf_task(task_id)
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/api/tasks/{task_id}")
    assert antwort.status_code == 200
    body = antwort.json()
    assert body["status"] == "fertig"
    assert body["ergebnis"] == "fertig"


def test_status_unbekannter_task_gibt_404(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/api/tasks/gibtsnicht")
    assert antwort.status_code == 404
