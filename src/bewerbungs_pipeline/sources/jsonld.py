"""Stellendaten aus den strukturierten Daten (schema.org/JobPosting) einer Seite.

Firmen betten ihre Anzeigen als JSON-LD ein, damit Suchmaschinen (Google
for Jobs) sie maschinell lesen können. Genau dafür sind die Daten da. Ein
Abruf pro Stelle, bei der Firma selbst, mit ehrlichem User-Agent und nur,
wenn die robots.txt der Seite es erlaubt.
"""

import json
import re
from datetime import date
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from . import html_text, normalisierung
from .karriereseiten import HEADERS, TIMEOUT, USER_AGENT

# Mehr als das ist keine Anzeigenseite mehr, sondern etwas, das wir nicht
# ganz in den Speicher laden wollen.
MAX_BYTES = 3_000_000

_SKRIPT = re.compile(
    r"<script[^>]*type\s*=\s*[\"']?application/ld\+json[\"']?[^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)

_INTERVALLE = {"YEAR": "Jahr", "MONTH": "Monat", "WEEK": "Woche", "DAY": "Tag", "HOUR": "Std."}
_ARBEITSZEIT = {"FULL_TIME": "Vollzeit", "PART_TIME": "Teilzeit"}


def _ist_jobposting(knoten: dict) -> bool:
    typ = knoten.get("@type")
    typen = typ if isinstance(typ, list) else [typ]
    return "JobPosting" in typen


def _durchlaufe(knoten):
    """Alle Wörterbücher im JSON-LD-Baum, inklusive @graph-Verschachtelung."""
    if isinstance(knoten, list):
        for eintrag in knoten:
            yield from _durchlaufe(eintrag)
    elif isinstance(knoten, dict):
        yield knoten
        for wert in knoten.values():
            if isinstance(wert, (list, dict)):
                yield from _durchlaufe(wert)


def finde_jobposting(html: str) -> dict | None:
    """Das erste JobPosting-Objekt der Seite oder ``None``."""
    for roh in _SKRIPT.findall(html):
        try:
            daten = json.loads(roh.strip(), strict=False)
        except ValueError:
            continue  # kaputtes JSON-LD ist verbreitet — nächsten Block versuchen
        for knoten in _durchlaufe(daten):
            if _ist_jobposting(knoten):
                return knoten
    return None


def _zahl(wert) -> float | None:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def _betrag(wert: float) -> str:
    """Ganze Beträge ohne, Stundenlöhne wie 14,50 mit Cent."""
    if wert == int(wert):
        return normalisierung.formatiere_ganzzahl_betrag(wert)
    return normalisierung._betrag(wert)


def gehalt(posting: dict) -> str | None:
    basis = posting.get("baseSalary")
    if isinstance(basis, list):
        basis = basis[0] if basis else None
    if not isinstance(basis, dict):
        return None
    wert = basis.get("value")
    waehrung = basis.get("currency") or "EUR"
    if isinstance(wert, dict):
        minimum = _zahl(wert.get("minValue"))
        maximum = _zahl(wert.get("maxValue"))
        einzel = _zahl(wert.get("value"))
        einheit = _INTERVALLE.get(str(wert.get("unitText") or basis.get("unitText")).upper())
    else:
        minimum = maximum = None
        einzel = _zahl(wert)
        einheit = _INTERVALLE.get(str(basis.get("unitText")).upper())
    zeitraum = f"/{einheit}" if einheit else ""
    betrag = _betrag
    if minimum and maximum and minimum != maximum:
        return f"{betrag(minimum)}–{betrag(maximum)} {waehrung}{zeitraum}"
    if einzel or minimum or maximum:
        return f"{betrag(einzel or minimum or maximum)} {waehrung}{zeitraum}"
    return None


def _arbeitszeit(posting: dict) -> str | None:
    art = posting.get("employmentType")
    arten = {str(a).upper() for a in (art if isinstance(art, list) else [art]) if a}
    namen = [_ARBEITSZEIT[a] for a in ("FULL_TIME", "PART_TIME") if a in arten]
    return "/".join(namen) or None


def _datum(wert) -> date | None:
    try:
        return date.fromisoformat(str(wert)[:10]) if wert else None
    except ValueError:
        return None


def felder(posting: dict) -> dict:
    """JobPosting → Felder im Sinne von JobItem; fehlende Angaben entfallen."""
    organisation = posting.get("hiringOrganization")
    webseite = organisation.get("sameAs") if isinstance(organisation, dict) else None
    ergebnis = {
        "description_md": html_text.zu_text(posting.get("description")),
        "salary": gehalt(posting),
        "worktime": _arbeitszeit(posting),
        "homeoffice": "remote" if posting.get("jobLocationType") == "TELECOMMUTE" else None,
        "company_website": webseite if isinstance(webseite, str) else None,
        "posted_at": _datum(posting.get("datePosted")),
    }
    return {schluessel: wert for schluessel, wert in ergebnis.items() if wert}


# --- robots.txt ------------------------------------------------------------

_robots_cache: dict[str, RobotFileParser] = {}


def darf_abrufen(url: str, client: httpx.Client) -> bool:
    """Erlaubt die robots.txt der Seite unserem User-Agent diesen Abruf?

    Nach RFC 9309: fehlt die Datei (4xx), ist alles erlaubt; ist sie nicht
    erreichbar (Netzfehler, 5xx), gilt vorsichtshalber alles als verboten.
    """
    teile = urlparse(url)
    wurzel = f"{teile.scheme}://{teile.netloc}"
    regeln = _robots_cache.get(wurzel)
    if regeln is None:
        regeln = RobotFileParser()
        try:
            antwort = client.get(
                f"{wurzel}/robots.txt", headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
            )
        except httpx.HTTPError:
            return False
        if antwort.status_code >= 500:
            return False
        if antwort.status_code >= 400:
            regeln.allow_all = True
        else:
            regeln.parse(antwort.text.splitlines())
        _robots_cache[wurzel] = regeln
    return regeln.can_fetch(USER_AGENT, url)


def abrufen(url: str, client: httpx.Client | None = None) -> dict | None:
    """Stellendaten der Seite hinter `url` oder ``None``, wenn es keine gibt.

    ``None`` auch, wenn robots.txt den Abruf verbietet. Netz- und HTTP-Fehler
    werden geworfen.
    """
    if client is None:
        with httpx.Client() as eigener:
            return abrufen(url, eigener)
    if urlparse(url).scheme not in ("http", "https"):
        return None
    if not darf_abrufen(url, client):
        return None
    with client.stream(
        "GET", url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
    ) as antwort:
        antwort.raise_for_status()
        if "html" not in antwort.headers.get("content-type", "html"):
            return None
        roh = b""
        for stueck in antwort.iter_bytes():
            roh += stueck
            if len(roh) > MAX_BYTES:
                return None
        text = roh.decode(antwort.encoding or "utf-8", errors="replace")
    posting = finde_jobposting(text)
    return felder(posting) if posting else None
