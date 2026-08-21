import pytest

from bewerbungs_pipeline.sources import normalisierung as n


@pytest.mark.parametrize(
    "entry, erwartet",
    [
        (
            {
                "verguetungsangabe": "STUNDENLOHN",
                "artDerVerguetung": "GEHALTSSPANNE",
                "gehaltsspanneVon": 19.78,
                "gehaltsspanneBis": 26.0,
            },
            "19,78–26,00 €/h",
        ),
        (
            {"verguetungsangabe": "STUNDENLOHN", "gehaltsspanneVon": 19.78},
            "ab 19,78 €/h",
        ),
        ({"festgehalt": 50000.0}, "50.000 €/Jahr"),
        ({"verguetungsangabe": "KEINE_ANGABEN"}, None),
        ({}, None),
    ],
)
def test_gehalt(entry, erwartet):
    assert n.gehalt(entry) == erwartet


def test_gehalt_festgehalt_schlaegt_spanne():
    """Ist beides angegeben, gewinnt das Festgehalt — es ist die konkretere Angabe."""
    entry = {"festgehalt": 50000.0, "gehaltsspanneVon": 19.78, "gehaltsspanneBis": 26.0}
    assert n.gehalt(entry) == "50.000 €/Jahr"


@pytest.mark.parametrize(
    "entry, erwartet",
    [
        ({"arbeitszeitVollzeit": True}, "Vollzeit"),
        ({"arbeitszeitTeilzeitFlexibel": True}, "Teilzeit"),
        (
            {"arbeitszeitVollzeit": True, "arbeitszeitTeilzeitVormittag": True},
            "Vollzeit/Teilzeit",
        ),
        ({"arbeitszeitVollzeit": False, "arbeitszeitTeilzeitAbend": False}, None),
        ({}, None),
    ],
)
def test_arbeitszeit(entry, erwartet):
    assert n.arbeitszeit(entry) == erwartet


@pytest.mark.parametrize(
    "entry, erwartet",
    [
        ({"vertragsdauer": "UNBEFRISTET"}, "unbefristet"),
        (
            {"vertragsdauer": "BEFRISTET", "befristungInMonaten": 12},
            "befristet, 12 Monate",
        ),
        ({"vertragsdauer": "BEFRISTET"}, "befristet"),
        ({"vertragsdauer": "KEINE_ANGABE"}, None),
        ({}, None),
    ],
)
def test_vertrag(entry, erwartet):
    assert n.vertrag(entry) == erwartet


@pytest.mark.parametrize(
    "entry, erwartet",
    [
        (
            {
                "istArbeitnehmerUeberlassung": True,
                "istPrivateArbeitsvermittlung": False,
            },
            "zeitarbeit",
        ),
        (
            {"istArbeitnehmerUeberlassung": True, "istPrivateArbeitsvermittlung": True},
            "zeitarbeit",
        ),
        ({"istPrivateArbeitsvermittlung": True}, "vermittler"),
        (
            {
                "istArbeitnehmerUeberlassung": False,
                "istPrivateArbeitsvermittlung": False,
            },
            "arbeitgeber",
        ),
        ({}, None),
    ],
)
def test_herkunftsart(entry, erwartet):
    assert n.herkunftsart(entry) == erwartet


def test_herkunftsart_nur_ueberlassung_false():
    """Fehlt die Vermittlungsangabe, reicht ein einzelnes False nicht fuer 'arbeitgeber'."""
    assert n.herkunftsart({"istArbeitnehmerUeberlassung": False}) is None


@pytest.mark.parametrize(
    "url, erwartet",
    [
        ("https://www.persy.jobs/persy/l/job-jd2d2-b", "persy.jobs"),
        ("https://karriere.beispiel.de/job/42", "karriere.beispiel.de"),
        ("kaputt", None),
        (None, None),
    ],
)
def test_host(url, erwartet):
    assert n.host(url) == erwartet
