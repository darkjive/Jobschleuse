import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from bewerbungs_pipeline.models import JobItem
from bewerbungs_pipeline.sources import arbeitsagentur

FIXTURE = Path(__file__).parent / "fixtures" / "aa_search_response.json"
DETAIL_FIXTURE = Path(__file__).parent / "fixtures" / "aa_detail_response.json"


def load_payload() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parse_jobs_maps_fields():
    items = arbeitsagentur.parse_jobs(load_payload())
    assert len(items) == 2
    first = items[0]
    assert first.title == "Mechatroniker (m/w/d)"
    assert first.company == "AC Motoren GmbH"
    assert first.location == "Eppertshausen"
    assert first.source == "arbeitsagentur"
    assert first.source_ref == "10001-1000012345-S"
    assert first.posted_at.isoformat() == "2026-07-01"
    assert first.url == (
        "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1000012345-S"
    )


def test_parse_jobs_prefers_externe_url():
    items = arbeitsagentur.parse_jobs(load_payload())
    assert items[1].url == "https://karriere.beispiel.de/job/42"


def test_parse_jobs_empty_payload():
    assert arbeitsagentur.parse_jobs({}) == []
    assert arbeitsagentur.parse_jobs({"ergebnisliste": []}) == []


def test_parse_jobs_skips_entry_without_refnr_and_url():
    payload = {"ergebnisliste": [{"stellenangebotsTitel": "Kaputt", "firma": "X"}]}
    assert arbeitsagentur.parse_jobs(payload) == []


def test_parse_jobs_handles_malformed_date():
    """Malformed date should not crash parsing; entry should still be returned with posted_at=None."""
    payload = {
        "ergebnisliste": [
            {
                "stellenangebotsTitel": "Test Job",
                "firma": "Test Company",
                "referenznummer": "123-456-S",
                "datumErsteVeroeffentlichung": "kaputt",
            }
        ]
    }
    items = arbeitsagentur.parse_jobs(payload)
    assert len(items) == 1
    assert items[0].title == "Test Job"
    assert items[0].company == "Test Company"
    assert items[0].posted_at is None


def test_parse_jobs_liest_faktenfelder():
    first = arbeitsagentur.parse_jobs(load_payload())[0]
    assert first.job_kind == "ARBEIT"
    assert first.salary == "19,78–26,00 €/h"
    assert first.worktime == "Vollzeit"
    assert first.contract == "unbefristet"
    assert first.distance_km == 42
    assert first.start_date.isoformat() == "2026-09-01"
    assert first.changed_at.isoformat().startswith("2026-08-10T18:05:28")
    assert first.homeoffice is None
    assert first.plz


def test_parse_jobs_setzt_external_host():
    second = arbeitsagentur.parse_jobs(load_payload())[1]
    assert second.external_host == "karriere.beispiel.de"


def test_parse_jobs_ohne_faktenfelder():
    """Eine duenn belegte Anzeige laeuft durch und laesst die Felder leer."""
    payload = {
        "ergebnisliste": [
            {"stellenangebotsTitel": "Duenn", "firma": "X", "referenznummer": "1-2-S"}
        ]
    }
    item = arbeitsagentur.parse_jobs(payload)[0]
    assert item.salary is None
    assert item.worktime is None
    assert item.contract is None
    assert item.distance_km is None
    assert item.external_host is None


def _client_mit(handler, monkeypatch):
    """Ersetzt httpx.Client durch einen Transport, der handler befragt."""
    transport = httpx.MockTransport(handler)
    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **kw: original(*a, transport=transport, **kw)
    )


def test_fetch_details_liefert_payload(monkeypatch):
    nutzlast = json.loads(DETAIL_FIXTURE.read_text())
    _client_mit(lambda request: httpx.Response(200, json=nutzlast), monkeypatch)

    payload = arbeitsagentur.fetch_details("10001-1000012345-S")
    assert payload["allianzpartnerName"] == "XING GmbH & Co. KG"
    assert payload["stellenangebotsBeschreibung"].startswith("Wir suchen")


def test_fetch_details_gibt_none_bei_404(monkeypatch):
    _client_mit(lambda request: httpx.Response(404), monkeypatch)
    assert arbeitsagentur.fetch_details("weg-1-S") is None


def test_fetch_details_wirft_bei_serverfehler(monkeypatch):
    _client_mit(lambda request: httpx.Response(500), monkeypatch)
    with pytest.raises(httpx.HTTPStatusError):
        arbeitsagentur.fetch_details("kaputt-1-S")


def make_item(**overrides):
    basis = dict(
        title="Mechatroniker (m/w/d)",
        company="AC Motoren GmbH",
        location="Eppertshausen",
        url="https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1",
        source="arbeitsagentur",
        source_ref="10001-1",
        scraped_at=datetime.now(UTC),
    )
    basis.update(overrides)
    return JobItem(**basis)


def test_enrich_uebernimmt_detailfelder(monkeypatch):
    nutzlast = json.loads(DETAIL_FIXTURE.read_text())
    monkeypatch.setattr(arbeitsagentur, "fetch_details", lambda refnr: nutzlast)

    item = arbeitsagentur.enrich([make_item()])[0]
    assert item.source_partner == "XING GmbH & Co. KG"
    assert item.employer_kind == "vermittler"
    assert item.education == "MITTLERE_REIFE_MITTLERER_BILDUNGSABSCHLUSS"
    assert item.employer_hash == "fJsK89VjMAftJUvCwcatHyz"
    assert item.street == "Lyoner Str. 12"
    assert item.description_md.startswith("Wir suchen")


def test_enrich_verwirft_verschwundene(monkeypatch):
    monkeypatch.setattr(arbeitsagentur, "fetch_details", lambda refnr: None)
    assert arbeitsagentur.enrich([make_item()]) == []


def test_enrich_behaelt_stelle_bei_netzfehler(monkeypatch):
    def kaputt(refnr):
        raise httpx.ConnectError("kein Netz")

    monkeypatch.setattr(arbeitsagentur, "fetch_details", kaputt)
    ergebnis = arbeitsagentur.enrich([make_item()])
    assert len(ergebnis) == 1
    assert ergebnis[0].source_partner is None
    assert ergebnis[0].gone_at is None


def test_enrich_ohne_referenznummer(monkeypatch):
    def darf_nicht_aufgerufen_werden(refnr):
        raise AssertionError("ohne source_ref darf kein Abruf laufen")

    monkeypatch.setattr(arbeitsagentur, "fetch_details", darf_nicht_aufgerufen_werden)
    assert len(arbeitsagentur.enrich([make_item(source_ref=None)])) == 1


def test_check_alive_meldet_nur_404(monkeypatch):
    def antwort(refnr):
        if refnr == "weg-1":
            return None
        if refnr == "kaputt-1":
            raise httpx.ConnectError("kein Netz")
        return {"stellenangebotsBeschreibung": "da"}

    monkeypatch.setattr(arbeitsagentur, "fetch_details", antwort)
    assert arbeitsagentur.check_alive(["lebt-1", "weg-1", "kaputt-1"]) == {"weg-1"}


def test_fetch_jobs_reicht_suchparameter_durch(monkeypatch):
    gesehen = {}

    def falsche_seite(client, was, wo, umkreis, page, extra):
        gesehen.update(extra)
        return {"ergebnisliste": []}

    monkeypatch.setattr(arbeitsagentur, "_search_page", falsche_seite)
    monkeypatch.setattr(arbeitsagentur, "enrich", lambda items: items)

    arbeitsagentur.fetch_jobs(
        was="Frontend", wo="Darmstadt", veroeffentlicht_seit=7,
        ohne_zeitarbeit=True, nur_arbeit=True,
    )
    assert gesehen == {"veroeffentlichtseit": 7, "zeitarbeit": "false", "angebotsart": 1}


def test_fetch_jobs_ohne_zusatzparameter(monkeypatch):
    gesehen = {}

    def falsche_seite(client, was, wo, umkreis, page, extra):
        gesehen["extra"] = extra
        return {"ergebnisliste": []}

    monkeypatch.setattr(arbeitsagentur, "_search_page", falsche_seite)
    monkeypatch.setattr(arbeitsagentur, "enrich", lambda items: items)

    arbeitsagentur.fetch_jobs(was="Frontend", wo="Darmstadt")
    assert gesehen["extra"] == {}
