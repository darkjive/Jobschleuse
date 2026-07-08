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
