from pathlib import Path

from fastapi.testclient import TestClient

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


def test_wurzel_liefert_react_app(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert '<div id="root">' in antwort.text


def test_unbekannter_pfad_liefert_ebenfalls_die_react_app(tmp_path):
    """React Router übernimmt clientseitig — der Server liefert für jeden
    unbekannten Pfad dieselbe index.html aus."""
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.get("/bewerbung/42")
    assert antwort.status_code == 200
    assert '<div id="root">' in antwort.text


def test_api_pfade_gehen_nicht_an_die_spa(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.get("/api/jobs")
    assert antwort.status_code == 200
    assert antwort.headers["content-type"].startswith("application/json")
