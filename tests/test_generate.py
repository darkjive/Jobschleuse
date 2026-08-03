import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bewerbungs_pipeline import db, generate
from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.models import JobItem

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"


class FakeClient:
    def __init__(self, payload: dict):
        message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: response)
        )


def make_cfg(tmp_path, cbks_inbox=None) -> Config:
    profile = tmp_path / "profile.yaml"
    profile.write_text("name: Alain Ritter\nemail: cosmwave@gmail.com\n")
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=TEMPLATE,
        profile_path=profile,
        cbks_inbox=cbks_inbox,
        llm_base_url="http://localhost",
        llm_api_key="test",
        llm_model="test-model",
    )


def seed(cfg, status="selected", description="Wir suchen Verstärkung im Service.") -> int:
    conn = db.connect(cfg.db_path)
    db.insert_job(
        conn,
        JobItem(
            title="Servicetechniker (m/w/d)",
            company="Beispiel AG",
            location="Frankfurt am Main",
            url="https://example.org/job/1",
            source="arbeitsagentur",
            description_md=description,
            scraped_at=datetime.now(UTC),
        ),
    )
    job_id = db.list_jobs(conn)[0]["id"]
    db.set_status(conn, job_id, status)
    conn.close()
    return job_id


GOOD = {
    "titel": "Bewerbung — Beispiel AG",
    "firma": "Beispiel AG",
    "einstieg": "Ihre Anzeige als Servicetechniker bei der Beispiel AG hat mich überzeugt.",
    "motivation": "Wartung und Service sind genau mein Feld.",
}


def test_generate_writes_output_and_sets_status(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    out_dir = generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))
    html = (out_dir / "index.html").read_text()
    assert "Beispiel AG" in html
    assert "Dieser Text ist statisch und bleibt unverändert." in html
    stelle = (out_dir / "stelle.md").read_text()
    assert "Servicetechniker" in stelle
    assert db.get_job(conn, job_id)["status"] == "selected"


def test_generate_copies_to_cbks_inbox(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    cfg = make_cfg(tmp_path, cbks_inbox=inbox)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))
    names = {p.name for p in inbox.iterdir()}
    assert names == {"bewerbung-beispiel-ag.html", "stelle-beispiel-ag.md"}


def test_generate_missing_inbox_warns_but_succeeds(tmp_path, capsys):
    cfg = make_cfg(tmp_path, cbks_inbox=tmp_path / "gibtsnicht")
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))
    assert "CBKS-Inbox" in capsys.readouterr().err
    assert db.get_job(conn, job_id)["status"] == "selected"


def test_generate_requires_selected_status(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg, status="new")
    conn = db.connect(cfg.db_path)
    with pytest.raises(SystemExit):
        generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))


def test_generate_reports_malformed_template_as_system_exit(tmp_path):
    cfg = make_cfg(tmp_path)
    broken_template = tmp_path / "broken.html"
    broken_template.write_text('<p data-slot="x">kaputt')
    cfg = replace(cfg, template_path=broken_template)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    with pytest.raises(SystemExit, match="Vorlage fehlerhaft"):
        generate.generate_application(conn, job_id, cfg, FakeClient(GOOD))


def test_slugify():
    assert generate.slugify("AC Motoren GmbH & Co. KG") == "ac-motoren-gmbh-co-kg"
    assert generate.slugify("Müllerößä") != ""
