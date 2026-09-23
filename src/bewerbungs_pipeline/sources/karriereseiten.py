"""Stellen direkt aus den öffentlichen Feeds von Bewerbermanagement-Systemen.

Viele Firmen verwalten ihre Stellen in einem Bewerbermanagement-System
(Personio, Greenhouse, Lever, Recruitee, SmartRecruiters). Deren Stellenfeeds
sind bewusst öffentlich und ohne Schlüssel abrufbar — sie existieren, damit
Karriereseiten, Portale und Suchmaschinen die Anzeigen übernehmen. Das ist
kein Abgreifen eines Portals, sondern der vorgesehene Weg.

Welche Firma welches System nutzt, verrät die Anzeigen-URL: Die
Arbeitsagentur verlinkt bei vielen Treffern auf die Karriereseite der Firma
(`externeURL`). `erkenne()` zieht daraus System und Kennung, der Feed liefert
dann alle offenen Stellen der Firma — auch die, die nie an die Arbeitsagentur
gemeldet wurden.
"""

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from ..models import JobItem
from . import html_text, normalisierung

TIMEOUT = 30.0
USER_AGENT = "Jobschleuse/0.1 (+https://github.com/darkjive/Jobschleuse)"
HEADERS = {"User-Agent": USER_AGENT}
# SmartRecruiters blättert in Hunderterschritten; große Konzerne haben
# tausende Stellen, die meisten davon woanders. Zehn Seiten reichen.
SMARTRECRUITERS_SEITEN = 10

SYSTEME = ("personio", "greenhouse", "lever", "recruitee", "smartrecruiters")

# Kennungen landen in URLs — nur harmlose Zeichen zulassen.
_KENNUNG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_PERSONIO_HOST = re.compile(r"^[a-z0-9-]+\.jobs\.personio\.(de|com)$")
_RECRUITEE_HOST = re.compile(r"^([a-z0-9-]+)\.recruitee\.com$")
_GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
_LEVER_HOSTS = {"jobs.lever.co"}
_SMARTRECRUITERS_HOSTS = {"jobs.smartrecruiters.com", "careers.smartrecruiters.com"}


@dataclass(frozen=True)
class Karriereseite:
    system: str
    kennung: str

    @property
    def praefix(self) -> str:
        """Gemeinsamer Anfang der `source_ref` aller Stellen dieser Seite."""
        return f"{self.system}:{self.kennung}:"


def _pruefe(system: str, kennung: str | None) -> Karriereseite | None:
    if not kennung or not _KENNUNG.match(kennung):
        return None
    return Karriereseite(system, kennung)


def erkenne(url: str | None) -> Karriereseite | None:
    """System und Kennung aus einer Anzeigen- oder Karriereseiten-URL.

    ``None``, wenn die URL zu keinem bekannten System gehört.
    """
    if not url:
        return None
    try:
        teile = urlparse(url.strip())
    except ValueError:
        return None
    host = (teile.hostname or "").lower()
    pfad = [stueck for stueck in teile.path.split("/") if stueck]

    if _PERSONIO_HOST.match(host):
        return Karriereseite("personio", host)
    if treffer := _RECRUITEE_HOST.match(host):
        return _pruefe("recruitee", treffer.group(1))
    if host in _GREENHOUSE_HOSTS:
        # Eingebettete Formulare: boards.greenhouse.io/embed/job_app?for=firma
        if pfad and pfad[0] == "embed":
            return _pruefe("greenhouse", (parse_qs(teile.query).get("for") or [None])[0])
        return _pruefe("greenhouse", pfad[0] if pfad else None)
    if host in _LEVER_HOSTS:
        return _pruefe("lever", pfad[0] if pfad else None)
    if host in _SMARTRECRUITERS_HOSTS:
        return _pruefe("smartrecruiters", pfad[0] if pfad else None)
    return None


# --- Hilfen ----------------------------------------------------------------


def _datum(wert) -> date | None:
    if wert in (None, ""):
        return None
    if isinstance(wert, (int, float)):
        # Lever liefert Millisekunden seit 1970.
        return datetime.fromtimestamp(wert / 1000, tz=UTC).date()
    try:
        return date.fromisoformat(str(wert).strip()[:10])
    except ValueError:
        return None


def _text(element: ET.Element | None, pfad: str) -> str:
    if element is None:
        return ""
    return (element.findtext(pfad) or "").strip()


def _item(seite: Karriereseite, firma: str, stellen_id, **felder) -> JobItem:
    return JobItem(
        company=firma,
        source=seite.system,
        source_ref=f"{seite.praefix}{stellen_id}",
        scraped_at=datetime.now(UTC),
        external_host=normalisierung.host(felder.get("url")),
        **felder,
    )


# --- Personio --------------------------------------------------------------

_PERSONIO_ARBEITSZEIT = {
    "full-time": "Vollzeit",
    "part-time": "Teilzeit",
    "full-or-part-time": "Vollzeit/Teilzeit",
}
_PERSONIO_VERTRAG = {"permanent": "unbefristet", "temporary": "befristet"}


def parse_personio(xml: str, seite: Karriereseite, firma: str) -> list[JobItem]:
    wurzel = ET.fromstring(xml)
    items: list[JobItem] = []
    for position in wurzel.iter("position"):
        stellen_id = _text(position, "id")
        titel = _text(position, "name")
        if not stellen_id or not titel:
            continue
        abschnitte = []
        for block in position.iter("jobDescription"):
            kopf = _text(block, "name")
            inhalt = html_text.zu_text(block.findtext("value"))
            if inhalt:
                abschnitte.append(f"{kopf}\n\n{inhalt}" if kopf else inhalt)
        items.append(
            _item(
                seite,
                _text(position, "subcompany") or firma,
                stellen_id,
                title=titel,
                location=_text(position, "office"),
                url=f"https://{seite.kennung}/job/{stellen_id}?language=de",
                description_md="\n\n".join(abschnitte),
                posted_at=_datum(_text(position, "createdAt")),
                worktime=_PERSONIO_ARBEITSZEIT.get(_text(position, "schedule")),
                contract=_PERSONIO_VERTRAG.get(_text(position, "employmentType")),
            )
        )
    return items


# --- Greenhouse ------------------------------------------------------------


def parse_greenhouse(payload: dict, seite: Karriereseite, firma: str) -> list[JobItem]:
    items: list[JobItem] = []
    for job in payload.get("jobs") or []:
        stellen_id = job.get("id")
        url = job.get("absolute_url")
        if stellen_id is None or not url:
            continue
        # `content` ist doppelt kodiert: HTML, dessen Zeichen nochmals als
        # Entitäten stehen (&lt;p&gt;).
        beschreibung = html_text.zu_text(html.unescape(job.get("content") or ""))
        items.append(
            _item(
                seite,
                job.get("company_name") or firma,
                stellen_id,
                title=(job.get("title") or "").strip() or "(ohne Titel)",
                location=((job.get("location") or {}).get("name") or "").strip(),
                url=url,
                description_md=beschreibung,
                posted_at=_datum(job.get("first_published") or job.get("updated_at")),
            )
        )
    return items


# --- Lever -----------------------------------------------------------------

_LEVER_INTERVALLE = {
    "per-year-salary": "Jahr",
    "per-month-salary": "Monat",
    "per-hour-wage": "Std.",
}


def _lever_gehalt(spanne: dict | None) -> str | None:
    if not spanne or not spanne.get("min"):
        return None
    betrag = normalisierung.formatiere_ganzzahl_betrag
    waehrung = spanne.get("currency") or "EUR"
    einheit = _LEVER_INTERVALLE.get(spanne.get("interval"))
    zeitraum = f"/{einheit}" if einheit else ""
    minimum, maximum = spanne["min"], spanne.get("max")
    if maximum and maximum != minimum:
        return f"{betrag(minimum)}–{betrag(maximum)} {waehrung}{zeitraum}"
    return f"{betrag(minimum)} {waehrung}{zeitraum}"


def parse_lever(payload: list, seite: Karriereseite, firma: str) -> list[JobItem]:
    items: list[JobItem] = []
    for job in payload or []:
        stellen_id = job.get("id")
        url = job.get("hostedUrl")
        if not stellen_id or not url:
            continue
        abschnitte = [job.get("descriptionPlain") or ""]
        for liste in job.get("lists") or []:
            inhalt = html_text.zu_text(liste.get("content"))
            if inhalt:
                abschnitte.append(f"{liste.get('text') or ''}\n\n{inhalt}".strip())
        abschnitte.append(job.get("additionalPlain") or "")
        kategorien = job.get("categories") or {}
        arbeitsort = job.get("workplaceType")
        items.append(
            _item(
                seite,
                firma,
                stellen_id,
                title=(job.get("text") or "").strip() or "(ohne Titel)",
                location=(kategorien.get("location") or "").strip(),
                url=url,
                description_md="\n\n".join(a.strip() for a in abschnitte if a.strip()),
                posted_at=_datum(job.get("createdAt")),
                homeoffice=arbeitsort if arbeitsort in ("remote", "hybrid") else None,
                salary=_lever_gehalt(job.get("salaryRange")),
                worktime={"Full-time": "Vollzeit", "Part-time": "Teilzeit"}.get(
                    kategorien.get("commitment")
                ),
            )
        )
    return items


# --- Recruitee -------------------------------------------------------------


def parse_recruitee(payload: dict, seite: Karriereseite, firma: str) -> list[JobItem]:
    items: list[JobItem] = []
    for angebot in payload.get("offers") or []:
        stellen_id = angebot.get("id")
        url = angebot.get("careers_url")
        if stellen_id is None or not url:
            continue
        teile = [
            html_text.zu_text(angebot.get("description")),
            html_text.zu_text(angebot.get("requirements")),
        ]
        items.append(
            _item(
                seite,
                angebot.get("company_name") or firma,
                stellen_id,
                title=(angebot.get("title") or "").strip() or "(ohne Titel)",
                location=(angebot.get("city") or angebot.get("location") or "").strip(),
                url=url,
                description_md="\n\n".join(t for t in teile if t),
                posted_at=_datum(angebot.get("published_at")),
                homeoffice="remote" if angebot.get("remote") else None,
            )
        )
    return items


# --- SmartRecruiters -------------------------------------------------------


def parse_smartrecruiters(
    payload: dict, seite: Karriereseite, firma: str
) -> list[JobItem]:
    """Die Liste enthält keinen Anzeigentext; der wird bei Bedarf über die
    strukturierten Daten der Anzeigenseite nachgeladen (siehe jsonld.py)."""
    items: list[JobItem] = []
    for posting in payload.get("content") or []:
        stellen_id = posting.get("id")
        if not stellen_id:
            continue
        ort = posting.get("location") or {}
        homeoffice = "remote" if ort.get("remote") else "hybrid" if ort.get("hybrid") else None
        items.append(
            _item(
                seite,
                (posting.get("company") or {}).get("name") or firma,
                stellen_id,
                title=(posting.get("name") or "").strip() or "(ohne Titel)",
                location=(ort.get("city") or "").strip(),
                url=f"https://jobs.smartrecruiters.com/{seite.kennung}/{stellen_id}",
                posted_at=_datum(posting.get("releasedDate")),
                homeoffice=homeoffice,
            )
        )
    return items


# --- Abruf -----------------------------------------------------------------


def _get(client: httpx.Client, url: str, **params) -> httpx.Response:
    antwort = client.get(
        url, params=params or None, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
    )
    antwort.raise_for_status()
    return antwort


def fetch_seite(
    seite: Karriereseite, firma: str, client: httpx.Client | None = None
) -> list[JobItem]:
    """Alle offenen Stellen einer Karriereseite.

    Fehler (Netz, HTTP, kaputtes Format) werden geworfen: Der Aufrufer darf
    einen gescheiterten Abruf nicht mit „keine Stellen mehr" verwechseln.
    """
    if client is None:
        with httpx.Client() as eigener:
            return fetch_seite(seite, firma, eigener)
    k = seite.kennung
    match seite.system:
        case "personio":
            antwort = _get(client, f"https://{k}/xml", language="de")
            return parse_personio(antwort.text, seite, firma)
        case "greenhouse":
            antwort = _get(
                client, f"https://boards-api.greenhouse.io/v1/boards/{k}/jobs", content="true"
            )
            return parse_greenhouse(antwort.json(), seite, firma)
        case "lever":
            antwort = _get(client, f"https://api.lever.co/v0/postings/{k}", mode="json")
            return parse_lever(antwort.json(), seite, firma)
        case "recruitee":
            antwort = _get(client, f"https://{k}.recruitee.com/api/offers/")
            return parse_recruitee(antwort.json(), seite, firma)
        case "smartrecruiters":
            items: list[JobItem] = []
            for seite_nr in range(SMARTRECRUITERS_SEITEN):
                payload = _get(
                    client,
                    f"https://api.smartrecruiters.com/v1/companies/{k}/postings",
                    limit=100,
                    offset=seite_nr * 100,
                ).json()
                stapel = parse_smartrecruiters(payload, seite, firma)
                items.extend(stapel)
                if len(items) >= (payload.get("totalFound") or 0) or not stapel:
                    break
            return items
    raise ValueError(f"Unbekanntes System: {seite.system}")


def passt(item: JobItem, was: str | None, wo: str | None) -> bool:
    """Grobe Vorauswahl, weil Feeds alle Stellen einer Firma liefern.

    `was`: jedes Wort muss in Titel oder Beschreibung vorkommen. `wo`: muss
    im Ort vorkommen — Stellen mit Homeoffice-Angabe gelten als überall.
    Ein Umkreis ist nicht möglich, die Feeds liefern keine Koordinaten.
    """
    if was:
        heuhaufen = f"{item.title}\n{item.description_md}".lower()
        if not all(wort in heuhaufen for wort in was.lower().split()):
            return False
    if wo and wo.lower() not in item.location.lower():
        return item.homeoffice in ("remote", "hybrid")
    return True
