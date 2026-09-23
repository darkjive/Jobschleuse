"""Schutz der Weboberfläche gegen fremde Webseiten im selben Browser
(CSRF, DNS-Rebinding) und gegen unpassende Uploads."""

from pathlib import Path

from fastapi.testclient import TestClient

from bewerbungs_pipeline.config import Config
from bewerbungs_pipeline.web.app import create_app

TEMPLATE = Path(__file__).parent / "fixtures" / "template_mini.html"

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def make_cfg(tmp_path) -> Config:
    vorlage = tmp_path / "vorlage" / "template.html"
    vorlage.parent.mkdir()
    vorlage.write_text(TEMPLATE.read_text())
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=vorlage,
        profile_path=tmp_path / "profile.yaml",
        llm_base_url="",
        llm_api_key="",
        llm_model="",
    )


def _bulk(client, **headers):
    return client.post(
        "/api/jobs/status", json={"ids": [], "status": "new"}, headers=headers
    )


def test_post_von_fremder_seite_wird_abgelehnt(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    assert _bulk(client, origin="https://boese.example").status_code == 403


def test_post_von_eigener_seite_geht_durch(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    assert _bulk(client, origin="http://testserver").status_code == 200


def test_post_ohne_origin_geht_durch(tmp_path):
    """CLI-Werkzeuge wie curl schicken keinen Origin — Browser bei
    fremden Anfragen immer."""
    client = TestClient(create_app(make_cfg(tmp_path)))
    assert _bulk(client).status_code == 200


def test_get_von_fremder_seite_bleibt_erlaubt(tmp_path):
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.get("/api/jobs", headers={"origin": "https://boese.example"})
    assert antwort.status_code == 200


def test_nur_loopback_lehnt_fremden_host_ab(tmp_path):
    """DNS-Rebinding: die fremde Seite ist dann „same origin“, aber ihr
    Host-Header trägt weiter ihren eigenen Namen."""
    client = TestClient(create_app(make_cfg(tmp_path), nur_loopback=True))
    assert client.get("/api/jobs", headers={"host": "boese.example:8765"}).status_code == 403
    assert client.get("/api/jobs", headers={"host": "127.0.0.1:8765"}).status_code == 200
    assert client.get("/api/jobs", headers={"host": "localhost:8765"}).status_code == 200


def test_upload_nimmt_passendes_bild(tmp_path):
    cfg = make_cfg(tmp_path)
    client = TestClient(create_app(cfg))
    antwort = client.post(
        "/api/profile/signature", files={"datei": ("s.png", PNG, "image/png")}
    )
    assert antwort.status_code == 200
    assert (cfg.template_path.parent / "assets" / "signature.png").read_bytes() == PNG


def test_upload_prueft_inhalt_statt_angabe(tmp_path):
    """Der Content-Type kommt vom Client — entscheidend sind die Bytes."""
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.post(
        "/api/profile/signature", files={"datei": ("s.png", JPEG, "image/png")}
    )
    assert antwort.status_code == 400


def test_upload_begrenzt_groesse(tmp_path, monkeypatch):
    from bewerbungs_pipeline.web.routes import api_profile

    monkeypatch.setattr(api_profile, "MAX_BYTES", 32)
    client = TestClient(create_app(make_cfg(tmp_path)))
    antwort = client.post(
        "/api/profile/portrait",
        files={"datei": ("p.jpg", JPEG + b"\x00" * 64, "image/jpeg")},
    )
    assert antwort.status_code == 413
