from datetime import date

from bewerbungs_pipeline.sources import indeed


def _row(**overrides):
    row = {
        "id": "in-abc123",
        "job_url": "https://de.indeed.com/viewjob?jk=abc123",
        "job_url_direct": None,
        "title": "Frontend Entwickler (m/w/d)",
        "company": "Beispiel GmbH",
        "location": "Darmstadt, HE, DE",
        "date_posted": date(2026, 8, 20),
        "job_type": "fulltime",
        "min_amount": None,
        "max_amount": None,
        "currency": None,
        "interval": None,
        "is_remote": False,
        "description": "Stellenbeschreibung",
        "company_url": None,
    }
    row.update(overrides)
    return row


def test_parse_jobs_maps_fields():
    items = indeed.parse_jobs([_row()])
    assert len(items) == 1
    item = items[0]
    assert item.title == "Frontend Entwickler (m/w/d)"
    assert item.company == "Beispiel GmbH"
    assert item.location == "Darmstadt, HE, DE"
    assert item.url == "https://de.indeed.com/viewjob?jk=abc123"
    assert item.source == "indeed"
    assert item.source_ref == "in-abc123"
    assert item.posted_at == date(2026, 8, 20)
    assert item.worktime == "Vollzeit"
    assert item.description_md == "Stellenbeschreibung"


def test_parse_jobs_keeps_unique_job_url_and_sets_external_host():
    items = indeed.parse_jobs(
        [_row(job_url_direct="https://karriere.beispiel.de/job/42")]
    )
    assert items[0].url == "https://de.indeed.com/viewjob?jk=abc123"
    assert items[0].external_host == "karriere.beispiel.de"


def test_parse_jobs_skips_row_without_url():
    assert indeed.parse_jobs([_row(job_url=None)]) == []


def test_parse_jobs_treats_nan_like_missing():
    nan = float("nan")
    items = indeed.parse_jobs([_row(company=nan, min_amount=nan)])
    assert items[0].company == "(unbekannt)"
    assert items[0].salary is None


def test_parse_jobs_empty():
    assert indeed.parse_jobs([]) == []


def test_gehalt_range():
    row = _row(min_amount=40000, max_amount=50000, currency="EUR", interval="yearly")
    assert indeed.gehalt(row) == "40.000–50.000 EUR/Jahr"


def test_gehalt_ab_wert_ohne_intervall():
    row = _row(min_amount=20, max_amount=None, currency="EUR", interval=None)
    assert indeed.gehalt(row) == "ab 20 EUR"


def test_gehalt_bis_wert_wenn_nur_maximum_bekannt():
    row = _row(min_amount=None, max_amount=50000, currency="EUR", interval="yearly")
    assert indeed.gehalt(row) == "bis 50.000 EUR/Jahr"


def test_gehalt_none_wenn_keine_angabe():
    assert indeed.gehalt(_row()) is None


def test_homeoffice_moeglich_bei_remote():
    assert indeed.parse_jobs([_row(is_remote=True)])[0].homeoffice == "moeglich"


def test_homeoffice_none_ohne_remote():
    assert indeed.parse_jobs([_row(is_remote=False)])[0].homeoffice is None


class _FakeDataFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self._rows


def test_fetch_jobs_reicht_suchparameter_durch(monkeypatch):
    aufruf = {}

    def falscher_scrape(**kwargs):
        aufruf.update(kwargs)
        return _FakeDataFrame([_row()])

    monkeypatch.setattr(indeed, "scrape_jobs", falscher_scrape)
    items = indeed.fetch_jobs(
        was="Frontend Entwickler", wo="Darmstadt", umkreis=50, seit_stunden=168
    )
    assert len(items) == 1
    assert aufruf["site_name"] == "indeed"
    assert aufruf["search_term"] == "Frontend Entwickler"
    assert aufruf["location"] == "Darmstadt"
    assert aufruf["distance"] == 50
    assert aufruf["country_indeed"] == "germany"
    assert aufruf["hours_old"] == 168
