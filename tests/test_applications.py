import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bewerbungs_pipeline import applications, db
from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.models import JobItem

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"

GOOD = {
    "titel": "Bewerbung — Beispiel AG",
    "firma": "Beispiel AG",
    "einstieg": "Ihre Anzeige als Servicetechniker bei der Beispiel AG hat mich überzeugt.",
    "motivation": "Wartung und Service sind genau mein Feld.",
}


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


def seed(cfg, status="selected") -> int:
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
    db.set_status(conn, job_id, status)
    conn.close()
    return job_id


def test_create_stores_slots(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    application = applications.get(conn, app_id)
    assert application["job_id"] == job_id
    assert set(application["slots"]) == set(GOOD)
    assert application["slots"]["firma"]["value"] == "Beispiel AG"
    assert application["slots"]["firma"]["source"] == "llm"


def test_create_twice_replaces_existing(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    first = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    second = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    assert first == second
    rows = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    assert rows == 1


def test_create_requires_selected_status(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg, status="new")
    conn = db.connect(cfg.db_path)
    with pytest.raises(applications.ApplicationError, match="auswählen"):
        applications.create(conn, job_id, cfg, FakeClient(GOOD))


def test_create_reports_malformed_template(tmp_path):
    cfg = make_cfg(tmp_path)
    broken = tmp_path / "broken.html"
    broken.write_text('<p data-slot="x">kaputt')
    cfg = replace(cfg, template_path=broken)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    with pytest.raises(applications.ApplicationError, match="Vorlage fehlerhaft"):
        applications.create(conn, job_id, cfg, FakeClient(GOOD))


def test_set_slot_marks_source_manuell(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.set_slot(conn, app_id, "motivation", "Von Hand geschrieben.")
    slot = applications.get(conn, app_id)["slots"]["motivation"]
    assert slot["value"] == "Von Hand geschrieben."
    assert slot["source"] == "manuell"


def test_set_slot_rejects_unknown_slot(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    with pytest.raises(applications.ApplicationError, match="Unbekannter Slot"):
        applications.set_slot(conn, app_id, "gibtsnicht", "x")


def test_render_uses_current_slot_values(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.set_slot(conn, app_id, "motivation", "Neuer Text von Hand.")
    html = applications.render(conn, app_id, cfg)
    assert "Neuer Text von Hand." in html
    assert "Dieser Text ist statisch und bleibt unverändert." in html


def test_get_by_job_returns_none_without_application(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    assert applications.get_by_job(conn, job_id) is None


def test_slugify():
    assert applications.slugify("AC Motoren GmbH & Co. KG") == "ac-motoren-gmbh-co-kg"
    assert applications.slugify("Müllerößä") != ""


def test_export_writes_html_and_stelle(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    out_dir = applications.export(conn, app_id, cfg)
    assert "Beispiel AG" in (out_dir / "index.html").read_text()
    assert "Servicetechniker" in (out_dir / "stelle.md").read_text()


def test_export_copies_to_cbks_inbox(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    cfg = make_cfg(tmp_path, cbks_inbox=inbox)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.export(conn, app_id, cfg)
    names = {p.name for p in inbox.iterdir()}
    assert names == {"bewerbung-beispiel-ag.html", "stelle-beispiel-ag.md"}


def test_export_missing_inbox_warns_but_succeeds(tmp_path, capsys):
    cfg = make_cfg(tmp_path, cbks_inbox=tmp_path / "gibtsnicht")
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.export(conn, app_id, cfg)
    assert "CBKS-Inbox" in capsys.readouterr().err


def test_regenerate_slot_replaces_value_and_marks_llm(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    applications.set_slot(conn, app_id, "motivation", "Von Hand.")
    neu = applications.regenerate_slot(
        conn, app_id, "motivation", cfg, FakeClient({"motivation": "Neu vom Modell."})
    )
    slot = applications.get(conn, app_id)["slots"]["motivation"]
    assert neu == "Neu vom Modell."
    assert slot["value"] == "Neu vom Modell."
    assert slot["source"] == "llm"


def test_regenerate_slot_rejects_unknown_slot(tmp_path):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    with pytest.raises(applications.ApplicationError, match="Unbekannter Slot"):
        applications.regenerate_slot(conn, app_id, "gibtsnicht", cfg, FakeClient({}))
