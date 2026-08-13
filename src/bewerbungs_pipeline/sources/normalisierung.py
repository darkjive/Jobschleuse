"""Wandelt Rohwerte der Arbeitsagentur-Schnittstelle in Anzeigewerte um.

Ausschliesslich reine Funktionen: rein geht das Wörterbuch eines Eintrags,
raus geht eine fertige Zeichenkette oder ``None``. ``None`` heisst immer
„die Quelle sagt dazu nichts" — die Oberfläche zeigt dann kein Kennzeichen,
statt „unbekannt" zu behaupten.
"""

from urllib.parse import urlparse

TEILZEIT_MERKMALE = (
    "arbeitszeitTeilzeitFlexibel",
    "arbeitszeitTeilzeitVormittag",
    "arbeitszeitTeilzeitNachmittag",
    "arbeitszeitTeilzeitAbend",
    "arbeitszeitSchichtNachtWochenende",
)


def _betrag(wert: float) -> str:
    """1234.5 → '1.234,50' — deutsche Schreibweise."""
    return f"{wert:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def gehalt(entry: dict) -> str | None:
    festgehalt = entry.get("festgehalt")
    if festgehalt:
        ganz = f"{int(festgehalt):,}".replace(",", ".")
        return f"{ganz} €/Jahr"

    von = entry.get("gehaltsspanneVon")
    bis = entry.get("gehaltsspanneBis")
    if not von:
        return None
    einheit = "€/h" if entry.get("verguetungsangabe") == "STUNDENLOHN" else "€"
    if bis:
        return f"{_betrag(von)}–{_betrag(bis)} {einheit}"
    return f"ab {_betrag(von)} {einheit}"


def arbeitszeit(entry: dict) -> str | None:
    vollzeit = bool(entry.get("arbeitszeitVollzeit"))
    teilzeit = any(entry.get(merkmal) for merkmal in TEILZEIT_MERKMALE)
    if vollzeit and teilzeit:
        return "Vollzeit/Teilzeit"
    if vollzeit:
        return "Vollzeit"
    if teilzeit:
        return "Teilzeit"
    return None


def vertrag(entry: dict) -> str | None:
    dauer = entry.get("vertragsdauer")
    if dauer == "UNBEFRISTET":
        return "unbefristet"
    if dauer == "BEFRISTET":
        monate = entry.get("befristungInMonaten")
        return f"befristet, {monate} Monate" if monate else "befristet"
    return None


def herkunftsart(entry: dict) -> str | None:
    """'zeitarbeit' | 'vermittler' | 'arbeitgeber' | None.

    ``None``, sobald eines der beiden Merkmale fehlt — bei rund 40 % der
    Anzeigen ist das der Fall, und eine Anzeige ohne Angabe darf nicht als
    „Arbeitgeber" ausgegeben werden.
    """
    ueberlassung = entry.get("istArbeitnehmerUeberlassung")
    vermittlung = entry.get("istPrivateArbeitsvermittlung")
    if ueberlassung:
        return "zeitarbeit"
    if vermittlung:
        return "vermittler"
    if ueberlassung is False and vermittlung is False:
        return "arbeitgeber"
    return None


def host(url: str | None) -> str | None:
    if not url:
        return None
    netloc = urlparse(url).netloc
    if not netloc:
        return None
    return netloc.removeprefix("www.")
