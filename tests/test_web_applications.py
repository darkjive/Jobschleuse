import json
import re
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
TEMPLATE_MIT_ASSETS = Path(__file__).parent / "fixtures" / "template_assets.html"

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


def test_bewerbung_erzeugen_legt_datensatz_an(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import applications as app_routen

    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    monkeypatch.setattr(app_routen, "make_client", lambda *a, **k: FakeClient(GOOD))
    app_id = app_routen.bewerbung_erzeugen(cfg, job_id)
    conn = db.connect(cfg.db_path)
    assert applications.get(conn, app_id) is not None


def test_bewerbungsseite_zeigt_slots(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/bewerbung/{app_id}")
    assert antwort.status_code == 200
    assert "motivation" in antwort.text
    assert "Wartung und Service sind mein Feld." in antwort.text


def test_bewerbungsseite_unbekannt_meldet_deutsch(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.get("/bewerbung/999")
    assert antwort.status_code == 404
    assert "nicht gefunden" in antwort.text


def test_slot_speichern(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(
        f"/applications/{app_id}/slots/motivation", data={"value": "Neu von Hand."}
    )
    assert antwort.status_code == 200
    conn = db.connect(cfg.db_path)
    slot = applications.get(conn, app_id)["slots"]["motivation"]
    assert slot["value"] == "Neu von Hand."
    assert slot["source"] == "manuell"


def test_slot_speichern_unbekannt_meldet_deutsch(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(f"/applications/{app_id}/slots/gibtsnicht", data={"value": "x"})
    assert antwort.status_code == 400
    assert "Unbekannter Slot" in antwort.text


def test_vorschau_liefert_gefuelltes_html(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/applications/{app_id}/preview")
    assert antwort.status_code == 200
    assert "Beispiel AG" in antwort.text
    assert "Dieser Text ist statisch und bleibt unverändert." in antwort.text


def test_export_laeuft_im_hintergrund(tmp_path):
    """Der Export dauert Sekunden (PDF-Druck) — er darf die Anfrage nicht blockieren."""
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/applications/{app_id}/export")
    assert antwort.status_code == 200
    assert "/tasks/" in antwort.text

    task_id = re.search(r"/tasks/(\w+)", antwort.text).group(1)
    frist = time.monotonic() + 60.0
    while time.monotonic() < frist and tasks_modul.get(task_id).status == "läuft":
        time.sleep(0.05)
    task = tasks_modul.get(task_id)
    assert task.status == "fertig", task.meldung
    assert (cfg.out_dir / "beispiel-ag" / "index.html").exists()
    assert (cfg.out_dir / "beispiel-ag" / "Bewerbung_Alain Ritter_Beispiel AG.pdf").exists()
    assert "beispiel-ag" in task.ergebnis


def test_slot_erzeugen_setzt_neuen_text(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import applications as app_routen

    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    monkeypatch.setattr(
        app_routen,
        "make_client",
        lambda *a, **k: FakeClient({"motivation": "Frisch erzeugt."}),
    )
    text = app_routen.slot_erzeugen(cfg, app_id, "motivation")
    assert text == "Frisch erzeugt."


def test_pfade_umschreiben_setzt_praefix():
    from bewerbungs_pipeline.web.routes import applications as app_routen

    html = '<link rel="stylesheet" href="styles.css"><img src="assets/foto.png">'
    ergebnis = app_routen.pfade_umschreiben(html)
    assert 'href="/template-assets/styles.css"' in ergebnis
    assert 'src="/template-assets/assets/foto.png"' in ergebnis


def test_pfade_umschreiben_laesst_absolute_pfade_in_ruhe():
    from bewerbungs_pipeline.web.routes import applications as app_routen

    html = '<img src="https://example.org/x.png"><img src="/schon-absolut.png">'
    assert app_routen.pfade_umschreiben(html) == html


def test_vorschau_schreibt_assetpfade_um(tmp_path):
    from dataclasses import replace

    cfg = replace(make_cfg(tmp_path), template_path=TEMPLATE_MIT_ASSETS)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/applications/{app_id}/preview")
    assert "/template-assets/styles.css" in antwort.text


def test_erzeugen_zeigt_keine_rohe_id_und_laedt_stelle_nach(tmp_path, monkeypatch):
    from bewerbungs_pipeline import tasks as tasks_modul
    from bewerbungs_pipeline.web.routes import applications as app_routen

    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    monkeypatch.setattr(app_routen, "make_client", lambda *a, **k: FakeClient(GOOD))
    client = TestClient(create_app(cfg))
    antwort = client.post("/applications", data={"job_id": str(job_id)})
    assert antwort.status_code == 200
    assert f"/jobs/{job_id}" in antwort.text

    task_id = re.search(r"/tasks/(\w+)", antwort.text).group(1)
    frist = time.monotonic() + 5.0
    while time.monotonic() < frist and tasks_modul.get(task_id).status == "läuft":
        time.sleep(0.01)
    assert tasks_modul.get(task_id).status == "fertig"

    fertig = client.get(f"/tasks/{task_id}", params={"ziel": f"/jobs/{job_id}"})
    assert "Fertig." in fertig.text


def test_slot_fragment_einzeln_abrufbar(tmp_path):
    """Nach „Neu erzeugen“ muss der Block nachgeladen werden können —
    sonst zeigt das Textfeld weiter den alten Stand."""
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/applications/{app_id}/slots/motivation")
    assert antwort.status_code == 200
    assert "Wartung und Service sind mein Feld." in antwort.text


def test_slot_fragment_unbekannt_meldet_deutsch(tmp_path):
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.get(f"/applications/{app_id}/slots/gibtsnicht")
    assert antwort.status_code == 404
    assert "Unbekannter Slot" in antwort.text


def test_slot_neu_verweist_auf_das_slot_fragment(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import applications as app_routen

    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    monkeypatch.setattr(
        app_routen, "make_client", lambda *a, **k: FakeClient({"motivation": "Neu."})
    )
    client = TestClient(create_app(cfg))
    antwort = client.post(f"/applications/{app_id}/slots/motivation/regenerate")
    assert antwort.status_code == 200
    assert f"/applications/{app_id}/slots/motivation" in antwort.text
    assert "slot-motivation" in antwort.text


def test_fehlermeldung_maskiert_html(tmp_path):
    """Der Slot-Name stammt aus dem Pfad und darf nicht roh im HTML landen."""
    cfg = make_cfg(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    client = TestClient(create_app(cfg))
    antwort = client.put(
        f"/applications/{app_id}/slots/<b>kaputt", data={"value": "x"}
    )
    assert antwort.status_code == 400
    assert "<b>kaputt" not in antwort.text
    assert "&lt;b&gt;kaputt" in antwort.text
