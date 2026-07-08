from pathlib import Path

import pytest

from bewerbungs_pipeline.slots import extract_slots, fill_slots

TEMPLATE = (Path(__file__).parent / "fixtures" / "template_mini.html").read_text()


def test_extract_slots():
    slots = extract_slots(TEMPLATE)
    assert set(slots) == {"titel", "firma", "einstieg", "motivation"}
    assert slots["firma"] == "AC Motoren GmbH"
    assert slots["einstieg"].startswith("Mit großem Interesse")


def test_extract_duplicate_slot_raises():
    html = '<p data-slot="x">a</p><p data-slot="x">b</p>'
    with pytest.raises(ValueError, match="doppelt"):
        extract_slots(html)


def test_fill_slots_replaces_only_slots():
    result = fill_slots(
        TEMPLATE,
        {"firma": "Beispiel AG", "einstieg": "Neuer Einstieg.", "titel": "Bewerbung — Beispiel AG", "motivation": "Neue Motivation."},
    )
    assert "Beispiel AG" in result
    assert "AC Motoren GmbH" not in result
    assert "Dieser Text ist statisch und bleibt unverändert." in result
    assert "robust" not in result  # alter Slot-Inhalt inkl. Markup ersetzt


def test_fill_slots_partial_is_allowed():
    result = fill_slots(TEMPLATE, {"firma": "Beispiel AG"})
    assert "Beispiel AG" in result
    assert "Mit großem Interesse" in result  # nicht übergebene Slots bleiben


def test_fill_unknown_slot_raises():
    with pytest.raises(ValueError, match="nicht in Vorlage"):
        fill_slots(TEMPLATE, {"gibtsnicht": "x"})
