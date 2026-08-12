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


def test_static_files_are_served(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.get("/static/tokens.css")
    assert antwort.status_code == 200
    assert "--accent" in antwort.text


def test_index_renders(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "Bewerbungen" in antwort.text
