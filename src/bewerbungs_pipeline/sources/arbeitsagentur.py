import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

import httpx

from ..models import JobItem
from . import normalisierung

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-KEY": "jobboerse-jobsuche"}
DETAIL_PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
TIMEOUT = 30.0
# Gemessen: 60 Detail-Abrufe mit 16 Arbeitern brauchen 0,4 s, ein
# Mengenlimit war nicht feststellbar.
PARALLEL = 16


def _parse_date(value: str | None) -> date | None:
    """Parse ISO date string, returning None if missing or malformed."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    """Parst den Änderungszeitstempel; die Quelle liefert ihn ohne Zeitzone."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_jobs(payload: dict) -> list[JobItem]:
    items: list[JobItem] = []
    for entry in payload.get("ergebnisliste", []):
        refnr = entry.get("referenznummer")
        externe_url = entry.get("externeURL")
        url = externe_url or (DETAIL_PAGE.format(refnr=refnr) if refnr else None)
        if not url:
            continue
        posted = entry.get("datumErsteVeroeffentlichung")
        lokationen = entry.get("stellenlokationen") or []
        adresse = (lokationen[0].get("adresse") or {}) if lokationen else {}
        items.append(
            JobItem(
                title=(entry.get("stellenangebotsTitel") or "").strip() or "(ohne Titel)",
                company=(entry.get("firma") or "").strip() or "(unbekannt)",
                location=(adresse.get("ort") or "").strip(),
                url=url,
                source="arbeitsagentur",
                source_ref=refnr,
                posted_at=_parse_date(posted),
                scraped_at=datetime.now(UTC),
                job_kind=entry.get("stellenangebotsart"),
                external_host=normalisierung.host(externe_url),
                homeoffice=entry.get("homeofficetyp")
                or ("moeglich" if entry.get("homeofficemoeglich") else None),
                salary=normalisierung.gehalt(entry),
                contract=normalisierung.vertrag(entry),
                worktime=normalisierung.arbeitszeit(entry),
                distance_km=entry.get("entfernung"),
                start_date=_parse_date((entry.get("eintrittszeitraum") or {}).get("von")),
                changed_at=_parse_datetime(entry.get("aenderungsdatum")),
                plz=(adresse.get("plz") or "").strip() or None,
            )
        )
    return items


def _search_page(
    client: httpx.Client, was: str, wo: str, umkreis: int, page: int, extra: dict
) -> dict:
    params = {"was": was, "wo": wo, "umkreis": umkreis, "size": 100, "page": page}
    params.update(extra)
    response = client.get(
        f"{BASE_URL}/pc/v6/jobs",
        params=params,
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def fetch_jobs(
    was: str,
    wo: str,
    umkreis: int = 25,
    max_pages: int = 5,
    veroeffentlicht_seit: int | None = None,
    ohne_zeitarbeit: bool = False,
    nur_arbeit: bool = False,
) -> list[JobItem]:
    """Holt Treffer und reichert sie um die Detailangaben an.

    Die drei Zusatzparameter engen bereits bei der Quelle ein, statt
    hinterher zu filtern: `veroeffentlicht_seit` in Tagen, `ohne_zeitarbeit`
    blendet Arbeitnehmerüberlassung aus, `nur_arbeit` schliesst Ausbildungen
    aus.
    """
    extra: dict = {}
    if veroeffentlicht_seit:
        extra["veroeffentlichtseit"] = veroeffentlicht_seit
    if ohne_zeitarbeit:
        extra["zeitarbeit"] = "false"
    if nur_arbeit:
        extra["angebotsart"] = 1

    items: list[JobItem] = []
    with httpx.Client() as client:
        for page in range(1, max_pages + 1):
            batch = parse_jobs(_search_page(client, was, wo, umkreis, page, extra))
            if not batch:
                break
            items.extend(batch)
    return enrich(items)


def fetch_details(refnr: str) -> dict | None:
    """Vollständiges Detail-Payload; ``None``, wenn die Anzeige weg ist.

    HTTP 404 heisst bei dieser Schnittstelle zuverlässig „nicht mehr
    vorhanden". Alle anderen Fehler — Zeitüberschreitung, Serverfehler,
    Verbindungsabbruch — werden geworfen und dürfen nicht als „weg"
    gedeutet werden.
    """
    encoded = base64.b64encode(refnr.encode()).decode()
    with httpx.Client() as client:
        response = client.get(
            f"{BASE_URL}/pc/v4/jobdetails/{encoded}", headers=HEADERS, timeout=TIMEOUT
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


def _adresse_strasse(payload: dict) -> str | None:
    lokationen = payload.get("stellenlokationen") or []
    adresse = (lokationen[0].get("adresse") or {}) if lokationen else {}
    strasse = (adresse.get("strasse") or "").strip()
    if not strasse:
        return None
    hausnummer = (adresse.get("hausnummer") or "").strip()
    return f"{strasse} {hausnummer}".strip()


def _anreichern(item: JobItem) -> JobItem | None:
    """Ein Detail-Abruf. ``None`` heisst: Anzeige ist weg, Treffer verwerfen."""
    if not item.source_ref:
        return item
    try:
        payload = fetch_details(item.source_ref)
    except Exception:
        # Netzfehler: Treffer behalten, nur ohne Zusatzangaben. Ein
        # Verbindungsproblem darf keine Stelle verschwinden lassen.
        return item
    if payload is None:
        return None

    return item.model_copy(
        update={
            "source_partner": payload.get("allianzpartnerName"),
            "employer_kind": normalisierung.herkunftsart(payload),
            "education": payload.get("geforderterBildungsabschluss"),
            "employer_hash": payload.get("arbeitgeberKundennummerHash"),
            "street": _adresse_strasse(payload),
            "description_md": payload.get("stellenangebotsBeschreibung")
            or item.description_md,
        }
    )


def enrich(items: list[JobItem]) -> list[JobItem]:
    """Reichert alle Treffer parallel an und wirft verschwundene weg."""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        ergebnisse = pool.map(_anreichern, items)
    return [item for item in ergebnisse if item is not None]


def check_alive(refnrs: list[str]) -> set[str]:
    """Referenznummern, deren Anzeige bei der Quelle verschwunden ist.

    Nur HTTP 404 zählt. Netzfehler liefern keine Aussage und werden
    stillschweigend übergangen — beim nächsten Lauf wird erneut geprüft.
    """
    if not refnrs:
        return set()

    def pruefen(refnr: str) -> str | None:
        try:
            return refnr if fetch_details(refnr) is None else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        return {refnr for refnr in pool.map(pruefen, refnrs) if refnr}
