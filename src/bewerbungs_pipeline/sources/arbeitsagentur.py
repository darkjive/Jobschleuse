import base64
from datetime import UTC, date, datetime

import httpx

from ..models import JobItem
from . import normalisierung

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
HEADERS = {"X-API-KEY": "jobboerse-jobsuche"}
DETAIL_PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
TIMEOUT = 30.0


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


def _search_page(client: httpx.Client, was: str, wo: str, umkreis: int, page: int) -> dict:
    response = client.get(
        f"{BASE_URL}/pc/v6/jobs",
        params={"was": was, "wo": wo, "umkreis": umkreis, "size": 100, "page": page},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def fetch_jobs(was: str, wo: str, umkreis: int = 25, max_pages: int = 5) -> list[JobItem]:
    items: list[JobItem] = []
    with httpx.Client() as client:
        for page in range(1, max_pages + 1):
            batch = parse_jobs(_search_page(client, was, wo, umkreis, page))
            if not batch:
                break
            items.extend(batch)
    return items


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
