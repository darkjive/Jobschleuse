import json
from pathlib import Path

from bewerbungs_pipeline.sources import arbeitsagentur

FIXTURE = Path(__file__).parent / "fixtures" / "aa_search_response.json"


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
