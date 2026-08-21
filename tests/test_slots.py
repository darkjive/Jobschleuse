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
        {
            "firma": "Beispiel AG",
            "einstieg": "Neuer Einstieg.",
            "titel": "Bewerbung — Beispiel AG",
            "motivation": "Neue Motivation.",
        },
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


def test_fill_preserves_static_bytes_exactly():
    html = (
        "<!DOCTYPE html>\n<html lang='de'>\n<head>\n"
        '  <meta charset="utf-8">\n'
        "  <style>.x  {color:red}</style>\n</head>\n<body>\n"
        '  <p data-slot="gruss">Alt</p>\n'
        "  <br>\n  <img src='x.png'>\n"
        '  <svg viewBox="0 0 1 1"><path d="M0 0"/></svg>\n'
        "  <pre>  exakt   so  </pre>\n</body>\n</html>\n"
    )
    result = fill_slots(html, {"gruss": "Neu & <gut>"})
    expected = html.replace(">Alt<", ">Neu &amp; &lt;gut&gt;<")
    assert result == expected


def test_fill_without_values_returns_input_unchanged():
    html = '<p data-slot="a">x</p><meta charset="utf-8">'
    assert fill_slots(html, {}) == html


def test_nested_markup_inside_slot_is_replaced_whole():
    html = '<div data-slot="m"><p>alt <strong>fett</strong></p></div><div>bleibt</div>'
    result = fill_slots(html, {"m": "neu"})
    assert result == '<div data-slot="m">neu</div><div>bleibt</div>'


def test_slot_on_void_element_raises():
    with pytest.raises(ValueError, match="leerem Element"):
        extract_slots('<img data-slot="bild" src="x.png">')


def test_nested_slots_raise():
    html = '<div data-slot="outer">AAA<p data-slot="inner">x</p>BBB</div>'
    with pytest.raises(ValueError, match="Verschachtelte Slots"):
        extract_slots(html)
    with pytest.raises(ValueError, match="Verschachtelte Slots"):
        fill_slots(html, {"outer": "O"})


def test_nested_same_tag_slots_raise():
    html = '<div data-slot="a">x<div data-slot="b">y</div>z</div>'
    with pytest.raises(ValueError, match="Verschachtelte Slots"):
        extract_slots(html)


def test_unclosed_slot_raises():
    with pytest.raises(ValueError, match="nicht geschlossen"):
        extract_slots('<div data-slot="offen">Text ohne Ende')
