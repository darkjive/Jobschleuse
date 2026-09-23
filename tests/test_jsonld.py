import json
import sqlite3
from datetime import UTC, datetime

import httpx
import pytest

from bewerbungs_pipeline import applications, db
from bewerbungs_pipeline.models import JobItem
from bewerbungs_pipeline.sources import jsonld

# Beim Laden gebunden, also vor dem Netz-Schutz aus conftest.py.
from bewerbungs_pipeline.sources.jsonld import abrufen as echtes_abrufen

POSTING = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Lagerhelfer (m/w/d)",
    "description": "<p>Wir suchen <b>dich</b>.</p><ul><li>Staplerschein</li></ul>",
    "datePosted": "2026-09-05",
    "employmentType": ["FULL_TIME", "PART_TIME"],
    "hiringOrganization": {"@type": "Organization", "name": "Acme", "sameAs": "https://acme.de"},
    "baseSalary": {
        "@type": "MonetaryAmount",
        "currency": "EUR",
        "value": {"@type": "QuantitativeValue", "minValue": 2800, "maxValue": 3200, "unitText": "MONTH"},
    },
}


def _seite(*bloecke: str) -> str:
    skripte = "".join(
        f'<script type="application/ld+json">{block}</script>' for block in bloecke
    )
    return f"<html><head>{skripte}</head><body>Anzeige</body></html>"


def test_finde_jobposting_direkt():
    assert jsonld.finde_jobposting(_seite(json.dumps(POSTING)))["title"] == "Lagerhelfer (m/w/d)"


def test_finde_jobposting_in_graph_und_nach_kaputtem_block():
    graph = {"@graph": [{"@type": "WebPage"}, {**POSTING, "@type": ["JobPosting"]}]}
    html = _seite("{kaputt", json.dumps({"@type": "Organization"}), json.dumps(graph))
    assert jsonld.finde_jobposting(html)["datePosted"] == "2026-09-05"


def test_finde_jobposting_ohne_treffer():
    assert jsonld.finde_jobposting("<html>nichts</html>") is None
    assert jsonld.finde_jobposting(_seite(json.dumps({"@type": "Article"}))) is None


def test_felder_uebersetzt_angaben():
    felder = jsonld.felder(POSTING)
    assert felder["description_md"] == "Wir suchen dich.\n\n- Staplerschein"
    assert felder["salary"] == "2.800–3.200 EUR/Monat"
    assert felder["worktime"] == "Vollzeit/Teilzeit"
    assert felder["company_website"] == "https://acme.de"
    assert felder["posted_at"].isoformat() == "2026-09-05"
    assert "homeoffice" not in felder


@pytest.mark.parametrize(
    ("basis", "erwartet"),
    [
        ({"currency": "EUR", "value": {"value": 14.5, "unitText": "HOUR"}}, "14,50 EUR/Std."),
        ({"currency": "EUR", "value": 42000, "unitText": "YEAR"}, "42.000 EUR/Jahr"),
        ({"currency": "EUR", "value": {"minValue": "x"}}, None),
        ("Verhandlungssache", None),
    ],
)
def test_gehalt_varianten(basis, erwartet):
    assert jsonld.gehalt({"baseSalary": basis}) == erwartet


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_abrufen_liest_seite(monkeypatch):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, text=_seite(json.dumps(POSTING)), headers={"content-type": "text/html"}
        )

    with _client(handler) as client:
        felder = echtes_abrufen("https://karriere.acme.de/job/1", client)
    assert felder["salary"] == "2.800–3.200 EUR/Monat"


def test_abrufen_respektiert_robots_txt():
    abrufe = []

    def handler(request):
        abrufe.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /job/\n")
        return httpx.Response(200, text=_seite(json.dumps(POSTING)))

    with _client(handler) as client:
        assert echtes_abrufen("https://karriere.acme.de/job/1", client) is None
    assert abrufe == ["/robots.txt"]


def test_abrufen_ohne_erreichbare_robots_txt_verzichtet():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(503)
        raise AssertionError("ohne robots.txt kein Seitenabruf")

    with _client(handler) as client:
        assert echtes_abrufen("https://karriere.acme.de/job/1", client) is None


def test_abrufen_ignoriert_nicht_html():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    with _client(handler) as client:
        assert echtes_abrufen("https://karriere.acme.de/job.pdf", client) is None


def test_abrufen_wirft_bei_http_fehler():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(500)

    with _client(handler) as client, pytest.raises(httpx.HTTPStatusError):
        echtes_abrufen("https://karriere.acme.de/job/1", client)


# --- Anbindung an ensure_description ----------------------------------------


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    return db.connect(tmp_path / "jobs.db")


def _stelle(conn, **felder) -> sqlite3.Row:
    basis = {
        "title": "Lagerhelfer",
        "company": "Acme",
        "location": "Kassel",
        "url": "https://karriere.acme.de/job/1",
        "source": "personio",
        "description_md": "kurz",
        "salary": "13 €/h",
        "scraped_at": datetime.now(UTC),
    }
    basis.update(felder)
    db.insert_job(conn, JobItem(**basis))
    return db.list_jobs(conn)[-1]


def test_ensure_description_holt_volltext_von_firmenseite(conn, monkeypatch):
    aufrufe = []

    def fake(url, client=None):
        aufrufe.append(url)
        return {**jsonld.felder(POSTING), "description_md": "Volltext " * 40}

    monkeypatch.setattr(jsonld, "abrufen", fake)
    zeile = applications.ensure_description(conn, _stelle(conn))
    assert aufrufe == ["https://karriere.acme.de/job/1"]
    assert zeile["description_md"].startswith("Volltext")
    assert zeile["salary"] == "13 €/h"  # vorhandene Angabe bleibt
    assert zeile["worktime"] == "Vollzeit/Teilzeit"  # fehlende wird ergänzt
    assert zeile["company_website"] == "https://acme.de"


def test_ensure_description_nicht_bei_arbeitsagentur_url(conn, monkeypatch):
    def darf_nicht(url, client=None):
        raise AssertionError("kein Abruf erwartet")

    monkeypatch.setattr(jsonld, "abrufen", darf_nicht)
    zeile = _stelle(conn, url="https://www.arbeitsagentur.de/jobsuche/jobdetail/1")
    assert applications.ensure_description(conn, zeile)["description_md"] == "kurz"


def test_ensure_description_bei_netzfehler_weiter(conn, monkeypatch, capsys):
    def kaputt(url, client=None):
        raise httpx.ConnectError("kein Netz")

    monkeypatch.setattr(jsonld, "abrufen", kaputt)
    assert applications.ensure_description(conn, _stelle(conn))["description_md"] == "kurz"
    assert "Firmenseite nicht abrufbar" in capsys.readouterr().err
