from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from bewerbungs_pipeline import db, pipeline
from bewerbungs_pipeline.models import JobItem
from bewerbungs_pipeline.sources import html_text, karriereseiten
from bewerbungs_pipeline.sources.karriereseiten import Karriereseite, erkenne

PERSONIO_XML = (Path(__file__).parent / "fixtures" / "personio.xml").read_text()
PERSONIO = Karriereseite("personio", "beispiel.jobs.personio.de")


# --- Erkennung -------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "erwartet"),
    [
        (
            "https://beispiel.jobs.personio.de/job/123?language=de&display=de",
            ("personio", "beispiel.jobs.personio.de"),
        ),
        ("https://acme.jobs.personio.com/", ("personio", "acme.jobs.personio.com")),
        ("https://boards.greenhouse.io/n26/jobs/42", ("greenhouse", "n26")),
        ("https://job-boards.greenhouse.io/acme/jobs/1", ("greenhouse", "acme")),
        (
            "https://boards.greenhouse.io/embed/job_app?for=acme&token=1",
            ("greenhouse", "acme"),
        ),
        ("https://jobs.lever.co/acme/0b1c-uuid", ("lever", "acme")),
        ("https://acme.recruitee.com/o/lagerhelfer", ("recruitee", "acme")),
        ("https://jobs.smartrecruiters.com/BoschGroup/7439", ("smartrecruiters", "BoschGroup")),
        ("https://careers.smartrecruiters.com/Acme", ("smartrecruiters", "Acme")),
    ],
)
def test_erkenne_bekannte_systeme(url, erwartet):
    seite = erkenne(url)
    assert (seite.system, seite.kennung) == erwartet


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "https://www.arbeitsagentur.de/jobsuche/jobdetail/1",
        "https://karriere.beispiel.de/job/42",
        "https://boards.greenhouse.io/",
        "https://jobs.lever.co/%2e%2e",
        "https://jobs.personio.de/",
        "mailto:bewerbung@beispiel.de",
    ],
)
def test_erkenne_ignoriert_fremdes(url):
    assert erkenne(url) is None


# --- Feeds -----------------------------------------------------------------


def test_parse_personio():
    items = karriereseiten.parse_personio(PERSONIO_XML, PERSONIO, "Fallback AG")
    assert len(items) == 2
    lager, buchhalter = items
    assert lager.title == "Lagerhelfer (m/w/d)"
    assert lager.company == "Beispiel Logistik GmbH"
    assert lager.location == "Kassel"
    assert lager.source == "personio"
    assert lager.source_ref == "personio:beispiel.jobs.personio.de:1234567"
    assert lager.url == "https://beispiel.jobs.personio.de/job/1234567?language=de"
    assert lager.external_host == "beispiel.jobs.personio.de"
    assert lager.worktime == "Vollzeit/Teilzeit"
    assert lager.contract == "unbefristet"
    assert lager.posted_at.isoformat() == "2026-09-01"
    assert "Deine Aufgaben" in lager.description_md
    assert "- Kommissionieren" in lager.description_md
    assert "Kein Abschluss nötig." in lager.description_md
    # Ohne subcompany greift der eingetragene Firmenname.
    assert buchhalter.company == "Fallback AG"
    assert buchhalter.contract == "befristet"
    assert buchhalter.worktime == "Teilzeit"
    assert buchhalter.description_md == ""


def test_parse_greenhouse_entpackt_doppelt_kodiertes_html():
    payload = {
        "jobs": [
            {
                "id": 42,
                "title": "Support Agent",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
                "location": {"name": "Berlin"},
                "content": "&lt;p&gt;Hilf Kunden &amp;amp; Kolleginnen.&lt;/p&gt;",
                "updated_at": "2026-09-02T10:00:00-04:00",
                "company_name": "Acme",
            },
            {"id": 43, "title": "ohne URL"},
        ]
    }
    seite = Karriereseite("greenhouse", "acme")
    (item,) = karriereseiten.parse_greenhouse(payload, seite, "x")
    assert item.description_md == "Hilf Kunden & Kolleginnen."
    assert item.company == "Acme"
    assert item.location == "Berlin"
    assert item.source_ref == "greenhouse:acme:42"
    assert item.posted_at.isoformat() == "2026-09-02"


def test_parse_lever():
    payload = [
        {
            "id": "abc-123",
            "text": "Fahrer (m/w/d)",
            "hostedUrl": "https://jobs.lever.co/acme/abc-123",
            "categories": {"location": "Hamburg", "commitment": "Full-time"},
            "descriptionPlain": "Wir liefern aus.",
            "lists": [{"text": "Das bringst du mit", "content": "<li>Führerschein B</li>"}],
            "additionalPlain": "Bewirb dich ohne Anschreiben.",
            "createdAt": 1756800000000,
            "workplaceType": "onsite",
            "salaryRange": {
                "min": 30000,
                "max": 36000,
                "currency": "EUR",
                "interval": "per-year-salary",
            },
        }
    ]
    (item,) = karriereseiten.parse_lever(payload, Karriereseite("lever", "acme"), "Acme")
    assert item.title == "Fahrer (m/w/d)"
    assert item.location == "Hamburg"
    assert item.worktime == "Vollzeit"
    assert item.homeoffice is None
    assert item.salary == "30.000–36.000 EUR/Jahr"
    assert item.posted_at.isoformat() == "2025-09-02"
    assert item.description_md.startswith("Wir liefern aus.")
    assert "Das bringst du mit\n\n- Führerschein B" in item.description_md
    assert item.description_md.endswith("Bewirb dich ohne Anschreiben.")


def test_parse_recruitee():
    payload = {
        "offers": [
            {
                "id": 9,
                "title": "Reinigungskraft",
                "careers_url": "https://acme.recruitee.com/o/reinigungskraft",
                "city": "Leipzig",
                "description": "<p>Minijob möglich.</p>",
                "requirements": "<p>Zuverlässigkeit</p>",
                "published_at": "2026-09-03 07:00:00 UTC",
                "remote": False,
            }
        ]
    }
    (item,) = karriereseiten.parse_recruitee(
        payload, Karriereseite("recruitee", "acme"), "Acme"
    )
    assert item.location == "Leipzig"
    assert item.description_md == "Minijob möglich.\n\nZuverlässigkeit"
    assert item.posted_at.isoformat() == "2026-09-03"
    assert item.homeoffice is None


def test_parse_smartrecruiters():
    payload = {
        "totalFound": 1,
        "content": [
            {
                "id": "744000",
                "name": "Produktionshelfer",
                "location": {"city": "Stuttgart", "remote": False, "hybrid": True},
                "releasedDate": "2026-09-04T09:00:00.000Z",
                "company": {"name": "Bosch"},
            }
        ],
    }
    (item,) = karriereseiten.parse_smartrecruiters(
        payload, Karriereseite("smartrecruiters", "BoschGroup"), "x"
    )
    assert item.company == "Bosch"
    assert item.url == "https://jobs.smartrecruiters.com/BoschGroup/744000"
    assert item.homeoffice == "hybrid"
    assert item.description_md == ""


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_seite_personio_ruft_xml_feed():
    anfragen = []

    def handler(request):
        anfragen.append(request)
        return httpx.Response(200, text=PERSONIO_XML)

    with _client(handler) as client:
        items = karriereseiten.fetch_seite(PERSONIO, "Beispiel", client)
    assert len(items) == 2
    assert str(anfragen[0].url) == "https://beispiel.jobs.personio.de/xml?language=de"
    assert anfragen[0].headers["user-agent"].startswith("Jobschleuse/")


def test_fetch_seite_wirft_bei_http_fehler():
    with _client(lambda r: httpx.Response(503)) as client, pytest.raises(
        httpx.HTTPStatusError
    ):
        karriereseiten.fetch_seite(Karriereseite("lever", "acme"), "Acme", client)


def test_fetch_seite_smartrecruiters_blaettert():
    def handler(request):
        offset = int(request.url.params["offset"])
        stapel = [{"id": str(offset + i), "name": f"Stelle {offset + i}"} for i in range(100)]
        return httpx.Response(200, json={"totalFound": 150, "content": stapel[: 150 - offset]})

    with _client(handler) as client:
        items = karriereseiten.fetch_seite(
            Karriereseite("smartrecruiters", "Acme"), "Acme", client
        )
    assert len(items) == 150


# --- Vorauswahl ------------------------------------------------------------


def _item(**felder) -> JobItem:
    basis = {
        "title": "Lagerhelfer",
        "company": "Acme",
        "location": "Kassel",
        "url": "https://acme.recruitee.com/o/1",
        "source": "recruitee",
        "scraped_at": datetime.now(UTC),
    }
    basis.update(felder)
    return JobItem(**basis)


def test_passt_filtert_nach_wort_und_ort():
    assert karriereseiten.passt(_item(), "lager", "kassel")
    assert karriereseiten.passt(_item(), None, None)
    assert not karriereseiten.passt(_item(), "lager fahrer", None)
    assert karriereseiten.passt(_item(description_md="auch Fahrer"), "lager fahrer", None)
    assert not karriereseiten.passt(_item(), None, "Berlin")
    assert karriereseiten.passt(_item(homeoffice="remote"), None, "Berlin")


def test_html_zu_text():
    assert html_text.zu_text(None) == ""
    assert (
        html_text.zu_text("<h2>Wir bieten</h2><ul><li>Obst</li><li>30&nbsp;Tage</li></ul>")
        == "Wir bieten\n\n- Obst\n- 30 Tage"
    )
    assert html_text.zu_text("<p>a<br>b</p><script>x()</script>") == "a\nb"


# --- Pipeline --------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "jobs.db")


def _aa_stelle(url: str, company: str = "Beispiel Logistik GmbH") -> JobItem:
    return JobItem(
        title="Lagerhelfer (m/w/d)",
        company=company,
        location="Kassel",
        url=url,
        source="arbeitsagentur",
        source_ref="10001-1",
        scraped_at=datetime.now(UTC),
    )


def test_entdecken_aus_gespeicherten_links(conn):
    db.insert_job(conn, _aa_stelle("https://beispiel.jobs.personio.de/job/1"))
    db.insert_job(
        conn, _aa_stelle("https://karriere.andere.de/1", company="Andere GmbH")
    )
    assert pipeline.karriereseiten_entdecken(conn) == 1
    assert pipeline.karriereseiten_entdecken(conn) == 0  # schon bekannt
    (zeile,) = db.karriereseiten(conn)
    assert (zeile["system"], zeile["kennung"], zeile["company"]) == (
        "personio",
        "beispiel.jobs.personio.de",
        "Beispiel Logistik GmbH",
    )


def test_hinzufuegen_von_hand(conn):
    assert pipeline.karriereseite_hinzufuegen(conn, "https://example.org") is None
    seite = pipeline.karriereseite_hinzufuegen(conn, "https://jobs.lever.co/acme", "Acme")
    assert seite == Karriereseite("lever", "acme")
    assert db.karriereseiten(conn)[0]["company"] == "Acme"


def _feed_patchen(monkeypatch, antworten: dict):
    """antworten: Kennung → Liste von JobItems oder Exception."""

    def fake(seite, firma, client=None):
        ergebnis = antworten[seite.kennung]
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return ergebnis

    monkeypatch.setattr(karriereseiten, "fetch_seite", fake)


def test_fetch_karriereseiten_speichert_filtert_und_markiert_weg(conn, monkeypatch):
    db.karriereseite_merken(conn, "personio", PERSONIO.kennung, "Beispiel")
    items = karriereseiten.parse_personio(PERSONIO_XML, PERSONIO, "Beispiel")
    _feed_patchen(monkeypatch, {PERSONIO.kennung: items})

    ergebnis = pipeline.fetch_karriereseiten(conn, wo="Kassel")
    assert ergebnis == (1, 1, 0, 0)
    assert [r["title"] for r in db.list_jobs(conn)] == ["Lagerhelfer (m/w/d)"]
    assert db.karriereseiten(conn)[0]["fetched_at"] is not None

    # Stelle verschwindet aus dem Feed → wird markiert, nicht gelöscht.
    _feed_patchen(monkeypatch, {PERSONIO.kennung: items[1:]})
    assert pipeline.fetch_karriereseiten(conn, wo="Kassel").weg == 1
    assert db.list_jobs(conn)[0]["gone_at"] is not None


def test_fetch_karriereseiten_fehler_laesst_bestand_in_ruhe(conn, monkeypatch):
    db.karriereseite_merken(conn, "personio", PERSONIO.kennung, "Beispiel")
    db.karriereseite_merken(conn, "lever", "acme", "Acme")
    items = karriereseiten.parse_personio(PERSONIO_XML, PERSONIO, "Beispiel")
    _feed_patchen(monkeypatch, {PERSONIO.kennung: items, "acme": []})
    pipeline.fetch_karriereseiten(conn)
    assert len(db.list_jobs(conn)) == 2

    _feed_patchen(
        monkeypatch,
        {PERSONIO.kennung: httpx.ConnectError("kein Netz"), "acme": []},
    )
    ergebnis = pipeline.fetch_karriereseiten(conn)
    assert ergebnis.fehler == 1
    assert ergebnis.weg == 0
    assert all(r["gone_at"] is None for r in db.list_jobs(conn))
    fehler = {z["kennung"]: z["fehler"] for z in db.karriereseiten(conn)}
    assert fehler[PERSONIO.kennung].startswith("ConnectError")
    assert fehler["acme"] is None


def test_weg_markieren_trifft_nur_eigene_seite(conn):
    """Präfixe mit gleichem Anfang (acme / acme-two) dürfen sich nicht stören."""
    for kennung in ("acme", "acme-two"):
        db.insert_job(
            conn,
            _item(
                url=f"https://jobs.lever.co/{kennung}/1",
                company=kennung,
                source="lever",
                source_ref=f"lever:{kennung}:1",
            ),
        )
    assert db.mark_gone_ausser(conn, "lever:acme:", set()) == 1
    lebend = [r["company"] for r in db.list_jobs(conn) if r["gone_at"] is None]
    assert lebend == ["acme-two"]


def test_fetch_arbeitsagentur_entdeckt_karriereseiten(conn, monkeypatch):
    from bewerbungs_pipeline.sources import arbeitsagentur

    monkeypatch.setattr(
        arbeitsagentur,
        "fetch_jobs",
        lambda **kw: [_aa_stelle("https://jobs.lever.co/acme/1")],
    )
    monkeypatch.setattr(arbeitsagentur, "check_alive", lambda refs: set())
    pipeline.fetch_arbeitsagentur(conn, was="Lager", wo="Kassel")
    assert [z["kennung"] for z in db.karriereseiten(conn)] == ["acme"]
