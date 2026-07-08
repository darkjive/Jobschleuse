import base64
from datetime import UTC, date, datetime

import httpx

from ..models import JobItem

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


def parse_jobs(payload: dict) -> list[JobItem]:
    items: list[JobItem] = []
    for entry in payload.get("ergebnisliste", []):
        refnr = entry.get("referenznummer")
        url = entry.get("externeURL") or (DETAIL_PAGE.format(refnr=refnr) if refnr else None)
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


def fetch_details(refnr: str) -> str:
    encoded = base64.b64encode(refnr.encode()).decode()
    with httpx.Client() as client:
        response = client.get(
            f"{BASE_URL}/pc/v4/jobdetails/{encoded}", headers=HEADERS, timeout=TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    return payload.get("stellenangebotsBeschreibung") or ""
