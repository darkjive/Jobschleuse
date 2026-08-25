"""Indeed-Suche über die Bibliothek ``python-jobspy``.

Liefert im Gegensatz zur Arbeitsagentur-Anzeigenliste bereits angereicherte
Felder (Gehalt, Homeoffice, Firmenlink) in einem einzigen Abruf — ein
gesonderter Detail-Abruf wie bei ``arbeitsagentur.py`` ist hier nicht nötig.
"""

from datetime import UTC, date, datetime

from jobspy import scrape_jobs

from ..models import JobItem
from . import normalisierung

INTERVALLE = {
    "yearly": "Jahr",
    "monthly": "Monat",
    "weekly": "Woche",
    "daily": "Tag",
    "hourly": "Std.",
}
ARBEITSZEITEN = {
    "fulltime": "Vollzeit",
    "parttime": "Teilzeit",
}


def _clean(value):
    """None bleibt None, NaN/NaT (pandas) wird ebenfalls zu None."""
    if value is None:
        return None
    if value != value:  # NaN- und NaT-Erkennung ohne pandas-Import
        return None
    return value


def _parse_date(value) -> date | None:
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _betrag(wert: float) -> str:
    return f"{int(wert):,}".replace(",", ".")


def gehalt(row: dict) -> str | None:
    minimum = _clean(row.get("min_amount"))
    maximum = _clean(row.get("max_amount"))
    if minimum is None and maximum is None:
        return None
    waehrung = _clean(row.get("currency")) or "EUR"
    einheit = INTERVALLE.get(_clean(row.get("interval")))
    zeitraum = f"/{einheit}" if einheit else ""
    if minimum is not None and maximum is not None and minimum != maximum:
        return f"{_betrag(minimum)}–{_betrag(maximum)} {waehrung}{zeitraum}"
    if maximum is not None and minimum is None:
        return f"bis {_betrag(maximum)} {waehrung}{zeitraum}"
    betrag = minimum if minimum is not None else maximum
    return f"ab {_betrag(betrag)} {waehrung}{zeitraum}"


def parse_jobs(rows: list[dict]) -> list[JobItem]:
    items: list[JobItem] = []
    for row in rows:
        url = _clean(row.get("job_url"))
        if not url:
            continue
        direkt = _clean(row.get("job_url_direct"))
        items.append(
            JobItem(
                title=_clean(row.get("title")) or "(ohne Titel)",
                company=_clean(row.get("company")) or "(unbekannt)",
                location=_clean(row.get("location")) or "",
                url=url,
                source="indeed",
                source_ref=_clean(row.get("id")),
                company_website=_clean(row.get("company_url")),
                posted_at=_parse_date(row.get("date_posted")),
                description_md=_clean(row.get("description")) or "",
                scraped_at=datetime.now(UTC),
                external_host=normalisierung.host(direkt),
                homeoffice="moeglich" if _clean(row.get("is_remote")) else None,
                salary=gehalt(row),
                worktime=ARBEITSZEITEN.get(_clean(row.get("job_type"))),
            )
        )
    return items


def fetch_jobs(
    was: str,
    wo: str,
    umkreis: int = 25,
    seit_stunden: int | None = None,
    ergebnisse: int = 25,
) -> list[JobItem]:
    df = scrape_jobs(
        site_name="indeed",
        search_term=was,
        location=wo,
        distance=umkreis,
        country_indeed="germany",
        results_wanted=ergebnisse,
        hours_old=seit_stunden,
    )
    return parse_jobs(df.to_dict(orient="records"))
