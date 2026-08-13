# Stellen-Anreicherung — Implementierungsplan

> **Für agentische Bearbeiter:** ERFORDERLICHE UNTER-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Aufgabe für Aufgabe umzusetzen. Die Schritte nutzen Checkbox-Syntax (`- [ ]`) zur Nachverfolgung.

**Ziel:** Jede Stelle in der Liste ist nachweislich verfügbar und zeigt ohne Klick Herkunft, Vermittlerart, Homeoffice, Gehalt, Entfernung und Alter.

**Architektur:** Die Trefferliste der Arbeitsagentur wird beim Holen um einen parallelen Detail-Abruf je Stelle ergänzt (16 Threads, ~0,4 s für 60 Stellen). HTTP 404 bedeutet „Anzeige weg" — betroffene Treffer werden gar nicht erst gespeichert, und derselbe Prüfweg markiert bei jedem Suchlauf verschwundene Bestandsstellen mit `gone_at`. Die gewonnenen Felder landen als eigene Spalten in `jobs` und erscheinen als Kennzeichen in der Listenzeile.

**Tech-Stack:** Python 3.12+, `uv`, httpx, pydantic, SQLite, FastAPI, Jinja2, HTMX, pytest.

**Spec:** `docs/specs/2026-08-13-stellen-anreicherung-design.md` — bei Widersprüchen gilt die Spec.

## Globale Randbedingungen

- **Sprache:** Bezeichner in `db.py`, `models.py`, `sources/` bleiben englisch (bestehende Konvention); Bezeichner in `web/` und `cli.py` bleiben deutsch (bestehende Konvention). Kommentare, Docstrings und Oberflächentexte auf Deutsch, mit korrekten Umlauten. Commit-Betreffzeilen ohne Umlaute (bestehende Konvention, siehe `git log`).
- **Kein Netzzugriff in Tests.** Jeder Test gegen die API arbeitet mit `monkeypatch` oder aufgezeichneten Antworten unter `tests/fixtures/`.
- **`filterwarnings = error`** ist aktiv (siehe `pyproject.toml`). Jede selbst geöffnete `sqlite3.Connection` im Test muss über die `conn`-Fixture laufen oder geschlossen werden.
- **Nur HTTP 404 setzt `gone_at`.** Verbindungsfehler, Zeitüberschreitungen und alle anderen HTTP-Fehler dürfen niemals als „verschwunden" gewertet werden.
- **Migrationen sind spaltenweise und idempotent.** Nie `DROP`, nie `CREATE TABLE ... AS SELECT` — die Bestandsdatenbank mit 529 Stellen und daran hängenden Bewerbungen muss unverändert überleben.
- **Testlauf:** `uv run pytest`. Ein Linter ist im Projekt nicht eingerichtet — keinen hinzufügen, sondern sich am Stil der umliegenden Dateien orientieren (Zeilenlänge ~90, doppelte Anführungszeichen, Typannotationen an öffentlichen Funktionen).
- **Python ≥ 3.13**, `requires-python` in `pyproject.toml`. Keine neuen Abhängigkeiten — `concurrent.futures` ist Teil der Standardbibliothek.
- **Commit nach jeder Aufgabe**, nicht erst am Ende.

## Dateiübersicht

| Datei | Zuständigkeit | Änderung |
|---|---|---|
| `src/bewerbungs_pipeline/sources/normalisierung.py` | Reine Umwandlung von API-Rohwerten in Anzeigewerte (Gehalt, Arbeitszeit, Vertrag, Herkunftsart, Host) | **neu** |
| `src/bewerbungs_pipeline/sources/arbeitsagentur.py` | HTTP-Zugriff auf die Arbeitsagentur, Parsen, Anreichern, Verfügbarkeitsprüfung | erweitert |
| `src/bewerbungs_pipeline/models.py` | `JobItem` | erweitert |
| `src/bewerbungs_pipeline/db.py` | Schema, Migration, Lese-/Schreibzugriffe | erweitert |
| `src/bewerbungs_pipeline/applications.py` | Aufrufer von `fetch_details` | angepasst |
| `src/bewerbungs_pipeline/web/routes/jobs.py` | Suchlauf, Frischeprüfung, Listenfilter | erweitert |
| `src/bewerbungs_pipeline/web/app.py` | Jinja-Filter `alter` | erweitert |
| `src/bewerbungs_pipeline/web/templates/_stellenliste.html` | Kennzeichen-Reihe | erweitert |
| `src/bewerbungs_pipeline/web/templates/_stellendetail.html` | Faktenliste, Verschwunden-Hinweis | erweitert |
| `src/bewerbungs_pipeline/web/templates/stellen.html` | Suchformular, Filterhäkchen | erweitert |
| `src/bewerbungs_pipeline/web/static/app.css` | Stil der Kennzeichen | erweitert |
| `src/bewerbungs_pipeline/cli.py` | `fetch`-Optionen, neuer Befehl `check` | erweitert |
| `tests/test_normalisierung.py` | Tests der reinen Umwandlung | **neu** |
| `tests/fixtures/aa_detail_response.json` | aufgezeichnete Detail-Antwort | **neu** |

Warum ein eigenes Modul `normalisierung.py`: Die Umwandlungsregeln (Gehaltsformate, Arbeitszeitkombinationen, Herkunftsart-Ableitung) sind der fehleranfälligste Teil und rein funktional. Getrennt sind sie ohne HTTP-Attrappen testbar, und `arbeitsagentur.py` bleibt beim Netzzugriff.

---

### Aufgabe 1: Modul `normalisierung.py` — reine Umwandlungsfunktionen

**Dateien:**
- Anlegen: `src/bewerbungs_pipeline/sources/normalisierung.py`
- Test: `tests/test_normalisierung.py`

**Schnittstellen:**
- Nutzt: nichts aus vorherigen Aufgaben.
- Liefert: `gehalt(entry) -> str | None`, `arbeitszeit(entry) -> str | None`, `vertrag(entry) -> str | None`, `herkunftsart(entry) -> str | None`, `host(url) -> str | None`. Alle nehmen das rohe API-Wörterbuch eines Eintrags entgegen (bzw. eine URL) und werden in Aufgabe 3 und 6 verwendet.

- [ ] **Schritt 1: Fehlschlagenden Test schreiben**

Datei `tests/test_normalisierung.py` anlegen:

```python
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
        ({"arbeitszeitVollzeit": True, "arbeitszeitTeilzeitVormittag": True}, "Vollzeit/Teilzeit"),
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
        ({"vertragsdauer": "BEFRISTET", "befristungInMonaten": 12}, "befristet, 12 Monate"),
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
        ({"istArbeitnehmerUeberlassung": True, "istPrivateArbeitsvermittlung": False}, "zeitarbeit"),
        ({"istArbeitnehmerUeberlassung": True, "istPrivateArbeitsvermittlung": True}, "zeitarbeit"),
        ({"istPrivateArbeitsvermittlung": True}, "vermittler"),
        ({"istArbeitnehmerUeberlassung": False, "istPrivateArbeitsvermittlung": False}, "arbeitgeber"),
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
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_normalisierung.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'bewerbungs_pipeline.sources.normalisierung'`

- [ ] **Schritt 3: Modul umsetzen**

Datei `src/bewerbungs_pipeline/sources/normalisierung.py` anlegen:

```python
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
```

- [ ] **Schritt 4: Test laufen lassen und Erfolg bestätigen**

Ausführen: `uv run pytest tests/test_normalisierung.py -v`
Erwartet: alle Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add src/bewerbungs_pipeline/sources/normalisierung.py tests/test_normalisierung.py
git commit -m "feat(sources): Rohwerte der Arbeitsagentur in Anzeigewerte umwandeln"
```

---

### Aufgabe 2: `JobItem` um die neuen Felder erweitern

**Dateien:**
- Ändern: `src/bewerbungs_pipeline/models.py:6-18`
- Test: `tests/test_db.py` (neuer Test am Dateiende)

**Schnittstellen:**
- Nutzt: nichts.
- Liefert: `JobItem` mit 16 zusätzlichen optionalen Feldern, genutzt von Aufgabe 3 bis 6.

- [ ] **Schritt 1: Fehlschlagenden Test schreiben**

An `tests/test_db.py` anhängen:

```python
def test_jobitem_neue_felder_sind_optional():
    """Bestehende Aufrufe ohne die neuen Felder bleiben gueltig."""
    item = make_item()
    assert item.job_kind is None
    assert item.employer_kind is None
    assert item.source_partner is None
    assert item.gone_at is None


def test_jobitem_nimmt_neue_felder_an():
    item = make_item(
        job_kind="ARBEIT",
        employer_kind="vermittler",
        source_partner="XING GmbH & Co. KG",
        external_host="persy.jobs",
        homeoffice="NACH_VEREINBARUNG",
        salary="19,78–26,00 €/h",
        contract="unbefristet",
        worktime="Vollzeit",
        distance_km=42,
        start_date=date(2026, 9, 1),
        changed_at=datetime(2026, 8, 10, 18, 5, tzinfo=UTC),
        street="Lyoner Str. 12",
        plz="60528",
        education="MITTLERE_REIFE_MITTLERER_BILDUNGSABSCHLUSS",
        employer_hash="fJsK89VjMAftJUvCwcatHyz",
    )
    assert item.distance_km == 42
    assert item.start_date.isoformat() == "2026-09-01"
```

Dazu die Importzeile oben in `tests/test_db.py` erweitern:

```python
from datetime import UTC, date, datetime
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_db.py::test_jobitem_neue_felder_sind_optional -v`
Erwartet: FAIL mit `AttributeError: 'JobItem' object has no attribute 'job_kind'`

- [ ] **Schritt 3: `models.py` erweitern**

In `src/bewerbungs_pipeline/models.py` innerhalb von `class JobItem` nach `description_md: str = ""` einfügen (die bestehenden Felder bleiben unverändert):

```python
    # Angaben aus der Trefferliste und dem Detail-Abruf der Quelle.
    # Alle optional: was die Quelle nicht liefert, bleibt None und wird in
    # der Oberflaeche weggelassen statt als „unbekannt" behauptet.
    job_kind: str | None = None
    employer_kind: str | None = None
    source_partner: str | None = None
    external_host: str | None = None
    homeoffice: str | None = None
    salary: str | None = None
    contract: str | None = None
    worktime: str | None = None
    distance_km: int | None = None
    start_date: date | None = None
    changed_at: datetime | None = None
    street: str | None = None
    plz: str | None = None
    education: str | None = None
    employer_hash: str | None = None
    gone_at: datetime | None = None
```

- [ ] **Schritt 4: Test laufen lassen und Erfolg bestätigen**

Ausführen: `uv run pytest tests/test_db.py -v`
Erwartet: alle Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add src/bewerbungs_pipeline/models.py tests/test_db.py
git commit -m "feat(models): JobItem um Herkunfts- und Faktenfelder erweitert"
```

---

### Aufgabe 3: Datenbankschema, Migration und Zugriffsfunktionen

**Dateien:**
- Ändern: `src/bewerbungs_pipeline/db.py:10-30` (Schema), `:55-62` (`_migrate`), `:86-110` (`insert_job`), `:137-160` (`suche_jobs`), `:163-177` (`row_to_item`)
- Test: `tests/test_db.py`

**Schnittstellen:**
- Nutzt: `JobItem` mit den Feldern aus Aufgabe 2.
- Liefert:
  - `db.insert_job(conn, item)` schreibt die neuen Spalten mit.
  - `db.suche_jobs(conn, status=None, q=None, ort=None, mit_verschwundenen=False)` — neuer letzter Parameter.
  - `db.offene_referenzen(conn) -> list[str]` — Referenznummern aller Stellen mit `source_ref IS NOT NULL AND gone_at IS NULL`.
  - `db.mark_gone(conn, refnrs: set[str]) -> int` — setzt `gone_at` auf jetzt, gibt die Anzahl geänderter Zeilen zurück.
  - `db.row_to_item(row)` liest die neuen Spalten.

- [ ] **Schritt 1: Fehlschlagenden Test schreiben**

An `tests/test_db.py` anhängen:

```python
def test_migration_erhaelt_bestandsdaten(tmp_path):
    """Eine Datenbank im alten Schema bekommt die neuen Spalten, ohne Zeilen zu verlieren."""
    pfad = tmp_path / "alt.db"
    alt = sqlite3.connect(pfad)
    alt.execute(
        """CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE, dedupe_hash TEXT NOT NULL UNIQUE,
            source_ref TEXT, title TEXT NOT NULL, company TEXT NOT NULL,
            company_website TEXT, location TEXT NOT NULL, source TEXT NOT NULL,
            posted_at TEXT, contact_name TEXT, contact_email TEXT,
            description_md TEXT NOT NULL DEFAULT '', scraped_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new')"""
    )
    alt.execute(
        "INSERT INTO jobs (url, dedupe_hash, title, company, location, source, scraped_at)"
        " VALUES ('http://a', 'hash1', 'Alt', 'Firma', 'Ort', 'arbeitsagentur', '2026-07-01T00:00:00+00:00')"
    )
    alt.commit()
    alt.close()

    conn = db.connect(pfad)
    zeilen = conn.execute("SELECT * FROM jobs").fetchall()
    assert len(zeilen) == 1
    assert zeilen[0]["title"] == "Alt"
    assert zeilen[0]["gone_at"] is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()


def test_migration_ist_wiederholbar(tmp_path):
    """Zweimal verbinden darf nicht an bereits vorhandenen Spalten scheitern."""
    pfad = tmp_path / "zweimal.db"
    db.connect(pfad).close()
    conn = db.connect(pfad)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()


def test_insert_job_schreibt_neue_spalten(conn):
    db.insert_job(conn, make_item(source_partner="XING GmbH & Co. KG", employer_kind="vermittler", distance_km=42))
    zeile = conn.execute("SELECT * FROM jobs").fetchone()
    assert zeile["source_partner"] == "XING GmbH & Co. KG"
    assert zeile["employer_kind"] == "vermittler"
    assert zeile["distance_km"] == 42


def test_row_to_item_liest_neue_spalten(conn):
    db.insert_job(conn, make_item(source_partner="XING GmbH & Co. KG", salary="ab 19,78 €/h"))
    item = db.row_to_item(conn.execute("SELECT * FROM jobs").fetchone())
    assert item.source_partner == "XING GmbH & Co. KG"
    assert item.salary == "ab 19,78 €/h"


def test_offene_referenzen_und_mark_gone(conn):
    db.insert_job(conn, make_item(url="http://a", source_ref="ref-a"))
    db.insert_job(conn, make_item(url="http://b", source_ref="ref-b", title="Zweiter"))
    db.insert_job(conn, make_item(url="http://c", source_ref=None, title="Dritter"))

    assert sorted(db.offene_referenzen(conn)) == ["ref-a", "ref-b"]

    assert db.mark_gone(conn, {"ref-a"}) == 1
    assert db.offene_referenzen(conn) == ["ref-b"]
    zeile = conn.execute("SELECT gone_at FROM jobs WHERE source_ref = 'ref-a'").fetchone()
    assert zeile["gone_at"] is not None


def test_mark_gone_ohne_referenzen(conn):
    db.insert_job(conn, make_item(source_ref="ref-a"))
    assert db.mark_gone(conn, set()) == 0


def test_suche_jobs_blendet_verschwundene_aus(conn):
    db.insert_job(conn, make_item(url="http://a", source_ref="ref-a"))
    db.insert_job(conn, make_item(url="http://b", source_ref="ref-b", title="Zweiter"))
    db.mark_gone(conn, {"ref-a"})

    assert len(db.suche_jobs(conn)) == 1
    assert len(db.suche_jobs(conn, mit_verschwundenen=True)) == 2
```

Die Importzeile oben in `tests/test_db.py` um `import sqlite3` erweitern.

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_db.py -v`
Erwartet: FAIL — `sqlite3.OperationalError: no such column: gone_at` bzw. `AttributeError: module 'bewerbungs_pipeline.db' has no attribute 'offene_referenzen'`

- [ ] **Schritt 3: `db.py` umsetzen**

`SCHEMA_VERSION` auf `2` setzen und im `SCHEMA`-String die neuen Spalten vor der schliessenden Klammer ergänzen:

```python
SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    dedupe_hash TEXT NOT NULL UNIQUE,
    source_ref TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    company_website TEXT,
    location TEXT NOT NULL,
    source TEXT NOT NULL,
    posted_at TEXT,
    contact_name TEXT,
    contact_email TEXT,
    description_md TEXT NOT NULL DEFAULT '',
    scraped_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    job_kind TEXT,
    employer_kind TEXT,
    source_partner TEXT,
    external_host TEXT,
    homeoffice TEXT,
    salary TEXT,
    contract TEXT,
    worktime TEXT,
    distance_km INTEGER,
    start_date TEXT,
    changed_at TEXT,
    street TEXT,
    plz TEXT,
    education TEXT,
    employer_hash TEXT,
    gone_at TEXT
)
"""

# Spalten, die Bestandsdatenbanken aus Schema-Version 1 nachgeruestet bekommen.
NEUE_SPALTEN_V2 = (
    ("job_kind", "TEXT"),
    ("employer_kind", "TEXT"),
    ("source_partner", "TEXT"),
    ("external_host", "TEXT"),
    ("homeoffice", "TEXT"),
    ("salary", "TEXT"),
    ("contract", "TEXT"),
    ("worktime", "TEXT"),
    ("distance_km", "INTEGER"),
    ("start_date", "TEXT"),
    ("changed_at", "TEXT"),
    ("street", "TEXT"),
    ("plz", "TEXT"),
    ("education", "TEXT"),
    ("employer_hash", "TEXT"),
    ("gone_at", "TEXT"),
)
```

`_migrate` ersetzen:

```python
def _migrate(conn: sqlite3.Connection) -> None:
    """Führt Schemaschritte aus, die über CREATE TABLE hinausgehen."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        conn.execute("UPDATE jobs SET status = 'selected' WHERE status = 'generated'")
    if version < 2:
        # Spaltenweise statt Tabellenneubau: die Bestandsdatenbank haengt an
        # Bewerbungen, die einen Fremdschluessel auf jobs.id halten.
        vorhanden = {
            zeile["name"] for zeile in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        for name, typ in NEUE_SPALTEN_V2:
            if name not in vorhanden:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")
    if version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
```

`insert_job` ersetzen:

```python
def insert_job(conn: sqlite3.Connection, item: JobItem) -> bool:
    cur = conn.execute(
        """INSERT OR IGNORE INTO jobs
           (url, dedupe_hash, source_ref, title, company, company_website,
            location, source, posted_at, contact_name, contact_email,
            description_md, scraped_at, job_kind, employer_kind, source_partner,
            external_host, homeoffice, salary, contract, worktime, distance_km,
            start_date, changed_at, street, plz, education, employer_hash, gone_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item.url,
            dedupe_hash(item),
            item.source_ref,
            item.title,
            item.company,
            item.company_website,
            item.location,
            item.source,
            item.posted_at.isoformat() if item.posted_at else None,
            item.contact_name,
            item.contact_email,
            item.description_md,
            item.scraped_at.isoformat(),
            item.job_kind,
            item.employer_kind,
            item.source_partner,
            item.external_host,
            item.homeoffice,
            item.salary,
            item.contract,
            item.worktime,
            item.distance_km,
            item.start_date.isoformat() if item.start_date else None,
            item.changed_at.isoformat() if item.changed_at else None,
            item.street,
            item.plz,
            item.education,
            item.employer_hash,
            item.gone_at.isoformat() if item.gone_at else None,
        ),
    )
    conn.commit()
    return cur.rowcount == 1
```

`suche_jobs` um den Parameter erweitern — die bestehende Signatur und die drei vorhandenen Filter bleiben unverändert, nur der neue Parameter und der neue Block kommen dazu:

```python
def suche_jobs(
    conn: sqlite3.Connection,
    status: str | None = None,
    q: str | None = None,
    ort: str | None = None,
    mit_verschwundenen: bool = False,
) -> list[sqlite3.Row]:
    """Stellenliste mit optionalen Filtern.

    `q` sucht in Titel und Firma, `ort` im Ort — beides ohne
    Beachtung der Groß-/Kleinschreibung. Stellen, deren Anzeige bei der
    Quelle verschwunden ist, bleiben aussen vor, solange
    `mit_verschwundenen` nicht gesetzt ist.
    """
    sql = "SELECT * FROM jobs WHERE 1=1"
    werte: list[str] = []
    if not mit_verschwundenen:
        sql += " AND gone_at IS NULL"
    if status:
        sql += " AND status = ?"
        werte.append(status)
    if q:
        sql += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"
        werte.extend([f"%{q.lower()}%"] * 2)
    if ort:
        sql += " AND LOWER(location) LIKE ?"
        werte.append(f"%{ort.lower()}%")
    sql += " ORDER BY id DESC"
    return conn.execute(sql, werte).fetchall()
```

Zwei neue Funktionen hinter `suche_jobs` einfügen:

```python
def offene_referenzen(conn: sqlite3.Connection) -> list[str]:
    """Referenznummern aller Stellen, die noch als verfügbar gelten."""
    zeilen = conn.execute(
        "SELECT source_ref FROM jobs"
        " WHERE source_ref IS NOT NULL AND gone_at IS NULL ORDER BY id"
    ).fetchall()
    return [zeile["source_ref"] for zeile in zeilen]


def mark_gone(conn: sqlite3.Connection, refnrs: set[str]) -> int:
    """Markiert die genannten Stellen als bei der Quelle verschwunden."""
    if not refnrs:
        return 0
    jetzt = datetime.now(UTC).isoformat()
    platzhalter = ",".join("?" * len(refnrs))
    cur = conn.execute(
        f"UPDATE jobs SET gone_at = ?"
        f" WHERE gone_at IS NULL AND source_ref IN ({platzhalter})",
        (jetzt, *sorted(refnrs)),
    )
    conn.commit()
    return cur.rowcount
```

Dafür die Importzeile oben in `db.py` ersetzen:

```python
from datetime import UTC, date, datetime
```

`row_to_item` um die neuen Felder ergänzen (bestehende Zuweisungen bleiben):

```python
def row_to_item(row: sqlite3.Row) -> JobItem:
    return JobItem(
        title=row["title"],
        company=row["company"],
        location=row["location"],
        url=row["url"],
        source=row["source"],
        source_ref=row["source_ref"],
        company_website=row["company_website"],
        posted_at=date.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
        contact_name=row["contact_name"],
        contact_email=row["contact_email"],
        description_md=row["description_md"],
        scraped_at=datetime.fromisoformat(row["scraped_at"]),
        job_kind=row["job_kind"],
        employer_kind=row["employer_kind"],
        source_partner=row["source_partner"],
        external_host=row["external_host"],
        homeoffice=row["homeoffice"],
        salary=row["salary"],
        contract=row["contract"],
        worktime=row["worktime"],
        distance_km=row["distance_km"],
        start_date=date.fromisoformat(row["start_date"]) if row["start_date"] else None,
        changed_at=datetime.fromisoformat(row["changed_at"]) if row["changed_at"] else None,
        street=row["street"],
        plz=row["plz"],
        education=row["education"],
        employer_hash=row["employer_hash"],
        gone_at=datetime.fromisoformat(row["gone_at"]) if row["gone_at"] else None,
    )
```

- [ ] **Schritt 4: Test laufen lassen und Erfolg bestätigen**

Ausführen: `uv run pytest tests/test_db.py -v`
Erwartet: alle Tests PASS

Dann die gesamte Suite: `uv run pytest`
Erwartet: alle Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add src/bewerbungs_pipeline/db.py tests/test_db.py
git commit -m "feat(db): Faktenspalten und Verschwunden-Markierung im Schema"
```

---

### Aufgabe 4: `parse_jobs` liest die Trefferlisten-Felder mit

**Dateien:**
- Ändern: `src/bewerbungs_pipeline/sources/arbeitsagentur.py:24-46`
- Ändern: `tests/fixtures/aa_search_response.json`
- Test: `tests/test_arbeitsagentur.py`

**Schnittstellen:**
- Nutzt: `normalisierung` (Aufgabe 1), `JobItem` (Aufgabe 2).
- Liefert: `parse_jobs(payload) -> list[JobItem]` mit gefüllten Feldern `job_kind`, `external_host`, `salary`, `worktime`, `contract`, `distance_km`, `start_date`, `changed_at`, `plz`, `homeoffice`.

- [ ] **Schritt 1: Vorlage erweitern**

`tests/fixtures/aa_search_response.json` öffnen und den **ersten** Eintrag in `ergebnisliste` um diese Schlüssel ergänzen (bestehende Schlüssel unverändert lassen):

```json
      "stellenangebotsart": "ARBEIT",
      "arbeitszeitVollzeit": true,
      "verguetungsangabe": "STUNDENLOHN",
      "artDerVerguetung": "GEHALTSSPANNE",
      "gehaltsspanneVon": 19.78,
      "gehaltsspanneBis": 26.0,
      "vertragsdauer": "UNBEFRISTET",
      "homeofficemoeglich": false,
      "entfernung": 42,
      "eintrittszeitraum": { "von": "2026-09-01" },
      "aenderungsdatum": "2026-08-10T18:05:28.461"
```

Beim zweiten Eintrag (der mit `externeURL`) nichts ergänzen — er dient als Nachweis, dass dünn belegte Anzeigen ohne Absturz durchlaufen.

- [ ] **Schritt 2: Fehlschlagenden Test schreiben**

An `tests/test_arbeitsagentur.py` anhängen:

```python
def test_parse_jobs_liest_faktenfelder():
    first = arbeitsagentur.parse_jobs(load_payload())[0]
    assert first.job_kind == "ARBEIT"
    assert first.salary == "19,78–26,00 €/h"
    assert first.worktime == "Vollzeit"
    assert first.contract == "unbefristet"
    assert first.distance_km == 42
    assert first.start_date.isoformat() == "2026-09-01"
    assert first.changed_at.isoformat().startswith("2026-08-10T18:05:28")
    assert first.homeoffice is None
    assert first.plz


def test_parse_jobs_setzt_external_host():
    second = arbeitsagentur.parse_jobs(load_payload())[1]
    assert second.external_host == "karriere.beispiel.de"


def test_parse_jobs_ohne_faktenfelder():
    """Eine duenn belegte Anzeige laeuft durch und laesst die Felder leer."""
    payload = {
        "ergebnisliste": [
            {"stellenangebotsTitel": "Duenn", "firma": "X", "referenznummer": "1-2-S"}
        ]
    }
    item = arbeitsagentur.parse_jobs(payload)[0]
    assert item.salary is None
    assert item.worktime is None
    assert item.contract is None
    assert item.distance_km is None
    assert item.external_host is None
```

- [ ] **Schritt 3: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_arbeitsagentur.py -v`
Erwartet: FAIL mit `AssertionError: assert None == 'ARBEIT'`

- [ ] **Schritt 4: `parse_jobs` umsetzen**

In `src/bewerbungs_pipeline/sources/arbeitsagentur.py` den Import ergänzen:

```python
from . import normalisierung
```

Eine Hilfsfunktion neben `_parse_date` einfügen:

```python
def _parse_datetime(value: str | None) -> datetime | None:
    """Parst den Änderungszeitstempel; die Quelle liefert ihn ohne Zeitzone."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
```

`parse_jobs` ersetzen:

```python
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
```

- [ ] **Schritt 5: Test laufen lassen und Erfolg bestätigen**

Ausführen: `uv run pytest tests/test_arbeitsagentur.py -v`
Erwartet: alle Tests PASS, auch die fünf bestehenden

- [ ] **Schritt 6: Committen**

```bash
git add src/bewerbungs_pipeline/sources/arbeitsagentur.py tests/test_arbeitsagentur.py tests/fixtures/aa_search_response.json
git commit -m "feat(sources): Faktenfelder aus der Trefferliste uebernehmen"
```

---

### Aufgabe 5: `fetch_details` liefert das ganze Payload und `None` bei 404

**Dateien:**
- Ändern: `src/bewerbungs_pipeline/sources/arbeitsagentur.py:71-79`
- Ändern: `src/bewerbungs_pipeline/applications.py:33-45`
- Anlegen: `tests/fixtures/aa_detail_response.json`
- Test: `tests/test_arbeitsagentur.py`, `tests/test_applications.py`

**Schnittstellen:**
- Nutzt: nichts aus vorherigen Aufgaben.
- Liefert: `fetch_details(refnr: str) -> dict | None` — vollständiges Payload, `None` bei HTTP 404. Andere HTTP-Fehler und Netzfehler werden weiterhin geworfen. Genutzt von Aufgabe 6 und von `applications.ensure_description`.

**Achtung — Signaturbruch.** Bisher lieferte die Funktion einen String. Einziger Aufrufer ist `applications.ensure_description`; der wird in dieser Aufgabe mitgezogen. Wer sonst noch `fetch_details` importiert, ist mit `grep -rn "fetch_details" src tests` zu prüfen.

- [ ] **Schritt 1: Vorlage anlegen**

Datei `tests/fixtures/aa_detail_response.json` anlegen:

```json
{
  "stellenangebotsart": "ARBEIT",
  "stellenangebotsTitel": "Mechatroniker (m/w/d)",
  "stellenangebotsBeschreibung": "Wir suchen zum naechstmoeglichen Zeitpunkt eine Mechatronikerin oder einen Mechatroniker fuer unsere Fertigung. Sie montieren, pruefen und warten Antriebseinheiten.",
  "firma": "AC Motoren GmbH",
  "referenznummer": "10001-1000012345-S",
  "istArbeitnehmerUeberlassung": false,
  "istPrivateArbeitsvermittlung": true,
  "istBetreut": true,
  "allianzpartnerName": "XING GmbH & Co. KG",
  "allianzpartnerUrl": "www.xing.com",
  "arbeitgeberKundennummerHash": "fJsK89VjMAftJUvCwcatHyz",
  "geforderterBildungsabschluss": "MITTLERE_REIFE_MITTLERER_BILDUNGSABSCHLUSS",
  "stellenlokationen": [
    {
      "adresse": {
        "strasse": "Lyoner Str.",
        "hausnummer": "12",
        "plz": "60528",
        "ort": "Frankfurt am Main"
      }
    }
  ]
}
```

- [ ] **Schritt 2: Fehlschlagenden Test schreiben**

An `tests/test_arbeitsagentur.py` anhängen (Importe `httpx` und `pytest` oben ergänzen):

```python
DETAIL_FIXTURE = Path(__file__).parent / "fixtures" / "aa_detail_response.json"


def _client_mit(handler, monkeypatch):
    """Ersetzt httpx.Client durch einen Transport, der handler befragt."""
    transport = httpx.MockTransport(handler)
    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **kw: original(*a, transport=transport, **kw)
    )


def test_fetch_details_liefert_payload(monkeypatch):
    nutzlast = json.loads(DETAIL_FIXTURE.read_text())
    _client_mit(lambda request: httpx.Response(200, json=nutzlast), monkeypatch)

    payload = arbeitsagentur.fetch_details("10001-1000012345-S")
    assert payload["allianzpartnerName"] == "XING GmbH & Co. KG"
    assert payload["stellenangebotsBeschreibung"].startswith("Wir suchen")


def test_fetch_details_gibt_none_bei_404(monkeypatch):
    _client_mit(lambda request: httpx.Response(404), monkeypatch)
    assert arbeitsagentur.fetch_details("weg-1-S") is None


def test_fetch_details_wirft_bei_serverfehler(monkeypatch):
    _client_mit(lambda request: httpx.Response(500), monkeypatch)
    with pytest.raises(httpx.HTTPStatusError):
        arbeitsagentur.fetch_details("kaputt-1-S")
```

- [ ] **Schritt 3: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_arbeitsagentur.py -k fetch_details -v`
Erwartet: FAIL — `TypeError: string indices must be integers` bzw. `httpx.HTTPStatusError` beim 404-Test

- [ ] **Schritt 4: `fetch_details` umsetzen**

In `arbeitsagentur.py` ersetzen:

```python
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
```

- [ ] **Schritt 5: Aufrufer anpassen**

In `src/bewerbungs_pipeline/applications.py` den Rumpf von `ensure_description` anpassen — die Zeile `text = fetch_details(row["source_ref"])` und die folgende Auswertung ersetzen:

```python
def ensure_description(conn, row) -> sqlite3.Row:
    """Holt bei zu kurzer Beschreibung den Volltext von der Quelle nach."""
    too_short = len(row["description_md"]) < MIN_DESCRIPTION_CHARS
    if too_short and row["source"] == "arbeitsagentur" and row["source_ref"]:
        try:
            payload = fetch_details(row["source_ref"])
        except Exception as exc:  # Netzfehler: mit Kurzbeschreibung weiterarbeiten
            print(f"Warnung: Details nicht abrufbar ({exc}).", file=sys.stderr)
            return row
        if payload is None:
            # Anzeige ist bei der Quelle verschwunden — vermerken und mit dem
            # arbeiten, was gespeichert ist.
            dbmod.mark_gone(conn, {row["source_ref"]})
            print("Warnung: Anzeige ist bei der Quelle nicht mehr vorhanden.", file=sys.stderr)
            return dbmod.get_job(conn, row["id"])
        text = payload.get("stellenangebotsBeschreibung") or ""
        if text:
            dbmod.update_description(conn, row["id"], text)
            return dbmod.get_job(conn, row["id"])
    return row
```

- [ ] **Schritt 6: Test laufen lassen und Erfolg bestätigen**

Ausführen: `uv run pytest tests/test_arbeitsagentur.py tests/test_applications.py -v`
Erwartet: alle Tests PASS. Schlägt ein bestehender Test in `test_applications.py` fehl, weil er `fetch_details` mit einem String-Rückgabewert nachbildet, ist die Attrappe auf ein Wörterbuch mit dem Schlüssel `stellenangebotsBeschreibung` umzustellen — inhaltlich prüft der Test dasselbe wie vorher.

Dann: `uv run pytest`
Erwartet: alle Tests PASS

- [ ] **Schritt 7: Committen**

```bash
git add src/bewerbungs_pipeline/sources/arbeitsagentur.py src/bewerbungs_pipeline/applications.py tests/test_arbeitsagentur.py tests/test_applications.py tests/fixtures/aa_detail_response.json
git commit -m "refactor(sources): fetch_details liefert Payload und None bei 404"
```

---

### Aufgabe 6: Paralleles Anreichern und Verfügbarkeitsprüfung

**Dateien:**
- Ändern: `src/bewerbungs_pipeline/sources/arbeitsagentur.py` (neue Funktionen ans Dateiende, `fetch_jobs` erweitert)
- Test: `tests/test_arbeitsagentur.py`

**Schnittstellen:**
- Nutzt: `fetch_details` (Aufgabe 5), `normalisierung.herkunftsart` (Aufgabe 1), `JobItem` (Aufgabe 2).
- Liefert:
  - `enrich(items: list[JobItem]) -> list[JobItem]` — reichert an, verwirft 404er.
  - `check_alive(refnrs: list[str]) -> set[str]` — Menge der Referenznummern, die 404 melden.
  - `fetch_jobs(was, wo, umkreis=25, max_pages=5, veroeffentlicht_seit=None, ohne_zeitarbeit=False, nur_arbeit=False)` — neue optionale Parameter, ruft am Ende `enrich`.

- [ ] **Schritt 1: Fehlschlagenden Test schreiben**

An `tests/test_arbeitsagentur.py` anhängen:

Dazu am Dateikopf ergänzen: `from datetime import UTC, datetime` und
`from bewerbungs_pipeline.models import JobItem`.

```python
def make_item(**overrides):
    basis = dict(
        title="Mechatroniker (m/w/d)",
        company="AC Motoren GmbH",
        location="Eppertshausen",
        url="https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1",
        source="arbeitsagentur",
        source_ref="10001-1",
        scraped_at=datetime.now(UTC),
    )
    basis.update(overrides)
    return JobItem(**basis)


def test_enrich_uebernimmt_detailfelder(monkeypatch):
    nutzlast = json.loads(DETAIL_FIXTURE.read_text())
    monkeypatch.setattr(arbeitsagentur, "fetch_details", lambda refnr: nutzlast)

    item = arbeitsagentur.enrich([make_item()])[0]
    assert item.source_partner == "XING GmbH & Co. KG"
    assert item.employer_kind == "vermittler"
    assert item.education == "MITTLERE_REIFE_MITTLERER_BILDUNGSABSCHLUSS"
    assert item.employer_hash == "fJsK89VjMAftJUvCwcatHyz"
    assert item.street == "Lyoner Str. 12"
    assert item.description_md.startswith("Wir suchen")


def test_enrich_verwirft_verschwundene(monkeypatch):
    monkeypatch.setattr(arbeitsagentur, "fetch_details", lambda refnr: None)
    assert arbeitsagentur.enrich([make_item()]) == []


def test_enrich_behaelt_stelle_bei_netzfehler(monkeypatch):
    def kaputt(refnr):
        raise httpx.ConnectError("kein Netz")

    monkeypatch.setattr(arbeitsagentur, "fetch_details", kaputt)
    ergebnis = arbeitsagentur.enrich([make_item()])
    assert len(ergebnis) == 1
    assert ergebnis[0].source_partner is None
    assert ergebnis[0].gone_at is None


def test_enrich_ohne_referenznummer(monkeypatch):
    def darf_nicht_aufgerufen_werden(refnr):
        raise AssertionError("ohne source_ref darf kein Abruf laufen")

    monkeypatch.setattr(arbeitsagentur, "fetch_details", darf_nicht_aufgerufen_werden)
    assert len(arbeitsagentur.enrich([make_item(source_ref=None)])) == 1


def test_check_alive_meldet_nur_404(monkeypatch):
    def antwort(refnr):
        if refnr == "weg-1":
            return None
        if refnr == "kaputt-1":
            raise httpx.ConnectError("kein Netz")
        return {"stellenangebotsBeschreibung": "da"}

    monkeypatch.setattr(arbeitsagentur, "fetch_details", antwort)
    assert arbeitsagentur.check_alive(["lebt-1", "weg-1", "kaputt-1"]) == {"weg-1"}


def test_fetch_jobs_reicht_suchparameter_durch(monkeypatch):
    gesehen = {}

    def falsche_seite(client, was, wo, umkreis, page, extra):
        gesehen.update(extra)
        return {"ergebnisliste": []}

    monkeypatch.setattr(arbeitsagentur, "_search_page", falsche_seite)
    monkeypatch.setattr(arbeitsagentur, "enrich", lambda items: items)

    arbeitsagentur.fetch_jobs(
        was="Frontend", wo="Darmstadt", veroeffentlicht_seit=7,
        ohne_zeitarbeit=True, nur_arbeit=True,
    )
    assert gesehen == {"veroeffentlichtseit": 7, "zeitarbeit": "false", "angebotsart": 1}


def test_fetch_jobs_ohne_zusatzparameter(monkeypatch):
    gesehen = {}

    def falsche_seite(client, was, wo, umkreis, page, extra):
        gesehen["extra"] = extra
        return {"ergebnisliste": []}

    monkeypatch.setattr(arbeitsagentur, "_search_page", falsche_seite)
    monkeypatch.setattr(arbeitsagentur, "enrich", lambda items: items)

    arbeitsagentur.fetch_jobs(was="Frontend", wo="Darmstadt")
    assert gesehen["extra"] == {}
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_arbeitsagentur.py -k "enrich or check_alive or suchparameter" -v`
Erwartet: FAIL mit `AttributeError: module 'bewerbungs_pipeline.sources.arbeitsagentur' has no attribute 'enrich'`

- [ ] **Schritt 3: Umsetzen**

Import ans Dateikopf von `arbeitsagentur.py`:

```python
from concurrent.futures import ThreadPoolExecutor
```

Konstante neben `TIMEOUT` ergänzen:

```python
# Gemessen: 60 Detail-Abrufe mit 16 Arbeitern brauchen 0,4 s, ein
# Mengenlimit war nicht feststellbar.
PARALLEL = 16
```

`_search_page` um den Zusatzparameter erweitern:

```python
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
```

`fetch_jobs` ersetzen:

```python
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
```

Ans Dateiende anfügen:

```python
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
```

- [ ] **Schritt 4: Test laufen lassen und Erfolg bestätigen**

Ausführen: `uv run pytest tests/test_arbeitsagentur.py -v`
Erwartet: alle Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add src/bewerbungs_pipeline/sources/arbeitsagentur.py tests/test_arbeitsagentur.py
git commit -m "feat(sources): Treffer parallel anreichern, verschwundene aussortieren"
```

---

### Aufgabe 7: Frischeprüfung im Suchlauf und neuer Befehl `jobs check`

**Dateien:**
- Ändern: `src/bewerbungs_pipeline/web/routes/jobs.py:29-36` (Liste), `:70-101` (Suchlauf)
- Ändern: `src/bewerbungs_pipeline/cli.py:9-15` (`_cmd_fetch`), `:77-108` (Argumente)
- Test: `tests/test_web_jobs.py`, `tests/test_cli.py`

**Schnittstellen:**
- Nutzt: `arbeitsagentur.fetch_jobs`/`check_alive` (Aufgabe 6), `db.offene_referenzen`/`mark_gone`/`suche_jobs` (Aufgabe 3).
- Liefert: `jobs.suche_ausfuehren(cfg, was, wo, umkreis, veroeffentlicht_seit, ohne_zeitarbeit, nur_arbeit) -> str`; Route `GET /jobs` nimmt zusätzlich `verschwunden: str = ""` entgegen.

- [ ] **Schritt 1: Fehlschlagenden Test schreiben**

An `tests/test_web_jobs.py` anhängen:

```python
def test_suche_markiert_verschwundene(tmp_path, monkeypatch):
    from bewerbungs_pipeline.sources import arbeitsagentur
    from bewerbungs_pipeline.web.routes import jobs as jobs_routen

    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at) VALUES ('http://alt', 'h1', 'ref-weg', 'Alte Stelle',"
        " 'Firma', 'Ort', 'arbeitsagentur', '2026-07-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(arbeitsagentur, "fetch_jobs", lambda **kw: [])
    monkeypatch.setattr(arbeitsagentur, "check_alive", lambda refnrs: {"ref-weg"})

    meldung = jobs_routen.suche_ausfuehren(cfg, "Frontend", "Darmstadt", 50, None, False, False)
    assert "1 nicht mehr verfügbar" in meldung

    conn = db.connect(cfg.db_path)
    zeile = conn.execute("SELECT gone_at FROM jobs WHERE source_ref = 'ref-weg'").fetchone()
    assert zeile["gone_at"] is not None
    conn.close()


def test_liste_blendet_verschwundene_aus(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    conn = db.connect(cfg.db_path)
    conn.execute("UPDATE jobs SET gone_at = '2026-08-13T00:00:00+00:00' WHERE id = ?",
                 (list(ids.values())[0],))
    conn.commit()
    conn.close()

    client = TestClient(create_app(cfg))
    ohne = client.get("/jobs").text
    mit = client.get("/jobs?verschwunden=1").text
    assert ohne.count("stelle__titel") == 1
    assert mit.count("stelle__titel") == 2
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_web_jobs.py -k "verschwunden" -v`
Erwartet: FAIL mit `TypeError: suche_ausfuehren() takes 4 positional arguments but 7 were given`

- [ ] **Schritt 3: `web/routes/jobs.py` umsetzen**

`liste` ersetzen:

```python
@router.get("/jobs", response_class=HTMLResponse)
def liste(
    request: Request,
    status: str = "",
    q: str = "",
    ort: str = "",
    verschwunden: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
):
    stellen = db.suche_jobs(
        conn,
        status=status or None,
        q=q or None,
        ort=ort or None,
        mit_verschwundenen=bool(verschwunden),
    )
    return templates.TemplateResponse(request, "_stellenliste.html", {"stellen": stellen})
```

`suche_ausfuehren` und `fetch` ersetzen:

```python
def suche_ausfuehren(
    cfg: Config,
    was: str,
    wo: str,
    umkreis: int,
    veroeffentlicht_seit: int | None,
    ohne_zeitarbeit: bool,
    nur_arbeit: bool,
) -> str:
    """Läuft im Hintergrund-Thread — öffnet deshalb eine eigene Verbindung."""
    items = arbeitsagentur.fetch_jobs(
        was=was,
        wo=wo,
        umkreis=umkreis,
        veroeffentlicht_seit=veroeffentlicht_seit,
        ohne_zeitarbeit=ohne_zeitarbeit,
        nur_arbeit=nur_arbeit,
    )
    conn = db.connect(cfg.db_path)
    try:
        neu = sum(1 for item in items if db.insert_job(conn, item))
        # Bei der Gelegenheit den Bestand nachziehen: derselbe Abruf, der
        # gerade neue Treffer geprueft hat, taugt auch fuer die alten.
        weg = db.mark_gone(conn, arbeitsagentur.check_alive(db.offene_referenzen(conn)))
    finally:
        conn.close()
    return f"{len(items)} Stellen geholt, {neu} neu, {weg} nicht mehr verfügbar."


@router.post("/jobs/fetch", response_class=HTMLResponse)
def fetch(
    request: Request,
    was: str = Form(...),
    wo: str = Form(...),
    umkreis: int = Form(25),
    seit: str = Form(""),
    ohne_zeitarbeit: str = Form(""),
    nur_arbeit: str = Form(""),
):
    cfg = request.app.state.cfg
    task_id = tasks.start(
        f"Suche „{was}“ in {wo}",
        suche_ausfuehren,
        cfg,
        was,
        wo,
        umkreis,
        int(seit) if seit else None,
        bool(ohne_zeitarbeit),
        bool(nur_arbeit),
    )
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {
            "task": tasks.get(task_id),
            "ziel": "/jobs?status=new",
            "ziel_element": "#stellenliste",
        },
    )
```

- [ ] **Schritt 4: CLI umsetzen**

In `src/bewerbungs_pipeline/cli.py` `_cmd_fetch` ersetzen und `_cmd_check` ergänzen:

```python
def _cmd_fetch(args: argparse.Namespace) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    items = arbeitsagentur.fetch_jobs(
        was=args.was,
        wo=args.wo,
        umkreis=args.umkreis,
        veroeffentlicht_seit=args.seit,
        ohne_zeitarbeit=args.ohne_zeitarbeit,
        nur_arbeit=args.nur_arbeit,
    )
    inserted = sum(1 for item in items if db.insert_job(conn, item))
    weg = db.mark_gone(conn, arbeitsagentur.check_alive(db.offene_referenzen(conn)))
    print(f"{len(items)} Stellen geholt, {inserted} neu, {weg} nicht mehr verfügbar.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    referenzen = db.offene_referenzen(conn)
    print(f"{len(referenzen)} Stellen werden geprüft …")
    weg = db.mark_gone(conn, arbeitsagentur.check_alive(referenzen))
    print(f"{weg} Stellen sind bei der Quelle nicht mehr vorhanden.")
    return 0
```

Im Argumentparser die `fetch`-Optionen ergänzen und den Befehl `check` anmelden:

```python
    p_fetch.add_argument("--seit", type=int, default=None,
                         help="nur Anzeigen der letzten N Tage")
    p_fetch.add_argument("--ohne-zeitarbeit", action="store_true",
                         help="Arbeitnehmerüberlassung ausblenden")
    p_fetch.add_argument("--nur-arbeit", action="store_true",
                         help="nur Arbeitsstellen, keine Ausbildungen")
```

(direkt vor `p_fetch.set_defaults(func=_cmd_fetch)` einfügen)

```python
    p_check = sub.add_parser("check", help="Bestand auf verschwundene Anzeigen prüfen")
    p_check.set_defaults(func=_cmd_check)
```

(nach dem `p_list`-Block einfügen)

- [ ] **Schritt 5: Test für den CLI-Befehl schreiben**

An `tests/test_cli.py` anhängen:

```python
def test_check_markiert_verschwundene(env, monkeypatch, capsys):
    conn = db.connect(env / "jobs.db")
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at) VALUES ('http://a', 'h1', 'ref-weg', 'Titel', 'Firma',"
        " 'Ort', 'arbeitsagentur', '2026-07-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(cli.arbeitsagentur, "check_alive", lambda refnrs: {"ref-weg"})
    assert cli.main(["check"]) == 0
    assert "1 Stellen sind bei der Quelle nicht mehr vorhanden." in capsys.readouterr().out


def test_fetch_reicht_neue_optionen_durch(env, monkeypatch, capsys):
    gesehen = {}

    def falsches_holen(**kw):
        gesehen.update(kw)
        return []

    monkeypatch.setattr(cli.arbeitsagentur, "fetch_jobs", falsches_holen)
    monkeypatch.setattr(cli.arbeitsagentur, "check_alive", lambda refnrs: set())
    cli.main([
        "fetch", "--was", "Frontend", "--wo", "Darmstadt",
        "--seit", "7", "--ohne-zeitarbeit", "--nur-arbeit",
    ])
    assert gesehen["veroeffentlicht_seit"] == 7
    assert gesehen["ohne_zeitarbeit"] is True
    assert gesehen["nur_arbeit"] is True
```

Die Datei nutzt die vorhandene `env`-Fixture, die `DB_PATH` auf `tmp_path` umbiegt — keine zweite Art danebenstellen, `load_config` nicht ersetzen.

- [ ] **Schritt 6: Tests laufen lassen und Erfolg bestätigen**

Ausführen: `uv run pytest`
Erwartet: alle Tests PASS

**Falle:** `_cmd_fetch` und `suche_ausfuehren` rufen jetzt zusätzlich
`check_alive`. Bestehende Tests, die nur `fetch_jobs` durch eine Attrappe
ersetzen (`test_fetch_inserts_jobs` in `tests/test_cli.py`, die Suchlauf-Tests
in `tests/test_web_jobs.py`), würden damit gegen das echte Netz laufen, sobald
die Testdatenbank eine Stelle mit `source_ref` enthält. In jedem dieser Tests
zusätzlich `check_alive` ersetzen:

```python
monkeypatch.setattr(cli.arbeitsagentur, "check_alive", lambda refnrs: set())
```

Vor dem Commit prüfen: `grep -rn "fetch_jobs" tests/` — jede Fundstelle muss
`check_alive` mit abfangen.

- [ ] **Schritt 7: Committen**

```bash
git add src/bewerbungs_pipeline/web/routes/jobs.py src/bewerbungs_pipeline/cli.py tests/test_web_jobs.py tests/test_cli.py
git commit -m "feat(jobs): Frischepruefung bei jeder Suche und als Befehl 'check'"
```

---

### Aufgabe 8: Kennzeichen in der Listenzeile

**Dateien:**
- Ändern: `src/bewerbungs_pipeline/web/app.py:11-12` (Jinja-Filter)
- Ändern: `src/bewerbungs_pipeline/web/templates/_stellenliste.html`
- Ändern: `src/bewerbungs_pipeline/web/static/app.css` (hinter `.stelle__status--selected`, Zeile 113)
- Test: `tests/test_web_jobs.py`

**Schnittstellen:**
- Nutzt: die Spalten aus Aufgabe 3.
- Liefert: Jinja-Filter `alter`, im Template als `{{ wert | alter }}` verwendbar.

- [ ] **Schritt 1: Fehlschlagenden Test schreiben**

An `tests/test_web_jobs.py` anhängen:

```python
def test_liste_zeigt_kennzeichen(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at, source_partner, employer_kind, homeoffice, salary,"
        " contract, distance_km) VALUES ('http://a', 'h1', 'ref-a', 'Titel', 'Firma',"
        " 'Ort', 'arbeitsagentur', '2026-08-13T00:00:00+00:00', 'XING GmbH & Co. KG',"
        " 'vermittler', 'NACH_VEREINBARUNG', 'ab 19,78 €/h', 'unbefristet', 42)"
    )
    conn.commit()
    conn.close()

    text = TestClient(create_app(cfg)).get("/jobs").text
    assert "XING GmbH &amp; Co. KG" in text
    assert "Vermittler" in text
    assert "Homeoffice" in text
    assert "ab 19,78" in text
    assert "42 km" in text


def test_liste_zeigt_leere_felder_nicht(tmp_path):
    """Eine duenn belegte Stelle bekommt keine Kennzeichen mit 'None' darin."""
    cfg = make_cfg(tmp_path)
    seed(cfg)
    text = TestClient(create_app(cfg)).get("/jobs").text
    assert "None" not in text
    assert "Vermittler" not in text


def test_liste_markiert_verschwundene(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    conn = db.connect(cfg.db_path)
    conn.execute("UPDATE jobs SET gone_at = '2026-08-13T00:00:00+00:00' WHERE id = ?",
                 (list(ids.values())[0],))
    conn.commit()
    conn.close()

    text = TestClient(create_app(cfg)).get("/jobs?verschwunden=1").text
    assert "nicht mehr verfügbar" in text
    assert "stelle--weg" in text
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_web_jobs.py -k kennzeichen -v`
Erwartet: FAIL mit `AssertionError: assert 'Vermittler' in ...`

- [ ] **Schritt 3: Jinja-Filter ergänzen**

In `src/bewerbungs_pipeline/web/app.py` unterhalb der `templates`-Zuweisung einfügen:

```python
def _alter(wert: str | None) -> str | None:
    """ISO-Zeitstempel → 'heute' / 'vor 3 Tagen' / 'vor 5 Wochen'."""
    if not wert:
        return None
    try:
        zeitpunkt = datetime.fromisoformat(wert)
    except ValueError:
        return None
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=UTC)
    tage = (datetime.now(UTC) - zeitpunkt).days
    if tage <= 0:
        return "heute"
    if tage == 1:
        return "gestern"
    if tage < 14:
        return f"vor {tage} Tagen"
    return f"vor {tage // 7} Wochen"


templates.env.filters["alter"] = _alter
```

Dazu den Import am Dateikopf ergänzen:

```python
from datetime import UTC, datetime
```

- [ ] **Schritt 4: Template umsetzen**

`src/bewerbungs_pipeline/web/templates/_stellenliste.html` ersetzen:

```jinja
{% if not stellen %}
  <p class="meldung">Keine Stellen gefunden.</p>
{% else %}
  <ul class="stellen">
    {% for stelle in stellen %}
      <li class="stelle {% if stelle.gone_at %}stelle--weg{% endif %}"
          id="stelle-{{ stelle.id }}">
        <button class="stelle__titel" hx-get="/jobs/{{ stelle.id }}"
                hx-target="#stellendetail">
          {{ stelle.title }}
        </button>
        <span class="stelle__meta">{{ stelle.company }} · {{ stelle.location }}</span>

        {# Reihenfolge fest: Herkunft, Warnzeichen, Pluspunkte, Eckdaten.
           Leere Felder erzeugen kein Kennzeichen — eine duenn belegte
           Anzeige bleibt schmal, statt „unbekannt" zu behaupten. #}
        <span class="marken">
          {% if stelle.gone_at %}
            <span class="marke marke--weg">nicht mehr verfügbar</span>
          {% endif %}
          {% set quelle = stelle.source_partner or stelle.external_host %}
          {% if quelle %}<span class="marke marke--quelle">{{ quelle }}</span>{% endif %}
          {% if stelle.employer_kind == "zeitarbeit" %}
            <span class="marke marke--warnung">Zeitarbeit</span>
          {% elif stelle.employer_kind == "vermittler" %}
            <span class="marke marke--warnung">Vermittler</span>
          {% endif %}
          {% if stelle.job_kind and stelle.job_kind != "ARBEIT" %}
            <span class="marke marke--warnung">Ausbildung</span>
          {% endif %}
          {% if stelle.homeoffice %}<span class="marke">Homeoffice</span>{% endif %}
          {% if stelle.salary %}<span class="marke">{{ stelle.salary }}</span>{% endif %}
          {% if stelle.contract %}<span class="marke">{{ stelle.contract }}</span>{% endif %}
          {% if stelle.distance_km is not none %}
            <span class="marke">{{ stelle.distance_km }} km</span>
          {% endif %}
          {% set frische = (stelle.changed_at or stelle.posted_at) | alter %}
          {% if frische %}<span class="marke">{{ frische }}</span>{% endif %}
        </span>

        <span class="stelle__status stelle__status--{{ stelle.status }}">
          {{ stelle.status }}
        </span>
      </li>
    {% endfor %}
  </ul>
{% endif %}
```

- [ ] **Schritt 5: CSS ergänzen**

In `src/bewerbungs_pipeline/web/static/app.css` hinter `.stelle__status--selected { color: var(--accent); }` einfügen:

```css
.marken { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.15rem; }

.marke {
  font-size: 0.7rem;
  line-height: 1.5;
  padding: 0 0.4rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  color: var(--text-dim);
  white-space: nowrap;
}

.marke--quelle { color: var(--text); border-color: var(--text-dim); }
.marke--warnung { color: var(--accent); border-color: var(--accent); }
.marke--weg { color: var(--text); background: var(--bg-hover); }

.stelle--weg { opacity: 0.55; }
.stelle--weg .stelle__titel { text-decoration: line-through; }
```

Alle verwendeten Token sind in `tokens.css` vorhanden (`--radius-sm` Zeile 42, `--bg-hover` Zeile 26, `--text-dim` Zeile 36, `--border` und `--accent` ebenfalls). Keine neuen Token anlegen.

- [ ] **Schritt 6: Tests laufen lassen und Erfolg bestätigen**

Ausführen: `uv run pytest tests/test_web_jobs.py -v`
Erwartet: alle Tests PASS

- [ ] **Schritt 7: Committen**

```bash
git add src/bewerbungs_pipeline/web/app.py src/bewerbungs_pipeline/web/templates/_stellenliste.html src/bewerbungs_pipeline/web/static/app.css tests/test_web_jobs.py
git commit -m "feat(web): Kennzeichen fuer Quelle, Vermittlerart und Eckdaten in der Liste"
```

---

### Aufgabe 9: Detailansicht und Suchformular

**Dateien:**
- Ändern: `src/bewerbungs_pipeline/web/templates/_stellendetail.html`
- Ändern: `src/bewerbungs_pipeline/web/templates/stellen.html`
- Ändern: `src/bewerbungs_pipeline/web/static/app.css`
- Ändern: `README.md`
- Test: `tests/test_web_jobs.py`

**Schnittstellen:**
- Nutzt: die Spalten aus Aufgabe 3, die Formularfelder aus Aufgabe 7 (`seit`, `ohne_zeitarbeit`, `nur_arbeit`), den Parameter `verschwunden` der Route `GET /jobs`.
- Liefert: nichts, worauf spätere Aufgaben aufbauen — dies ist die letzte Aufgabe.

- [ ] **Schritt 1: Fehlschlagenden Test schreiben**

An `tests/test_web_jobs.py` anhängen:

```python
def test_detail_zeigt_faktenliste(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    conn.execute(
        "INSERT INTO jobs (url, dedupe_hash, source_ref, title, company, location,"
        " source, scraped_at, street, plz, start_date, education, worktime,"
        " source_partner) VALUES ('http://a', 'h1', 'ref-a', 'Titel', 'Firma', 'Ort',"
        " 'arbeitsagentur', '2026-08-13T00:00:00+00:00', 'Lyoner Str. 12', '60528',"
        " '2026-09-01', 'MITTLERE_REIFE_MITTLERER_BILDUNGSABSCHLUSS', 'Vollzeit',"
        " 'XING GmbH & Co. KG')"
    )
    conn.commit()
    job_id = conn.execute("SELECT id FROM jobs").fetchone()["id"]
    conn.close()

    text = TestClient(create_app(cfg)).get(f"/jobs/{job_id}").text
    assert "Lyoner Str. 12" in text
    assert "60528" in text
    assert "Vollzeit" in text
    assert "XING GmbH &amp; Co. KG" in text


def test_detail_warnt_bei_verschwundener_stelle(tmp_path):
    cfg = make_cfg(tmp_path)
    ids = seed(cfg)
    job_id = list(ids.values())[0]
    conn = db.connect(cfg.db_path)
    conn.execute("UPDATE jobs SET gone_at = '2026-08-13T00:00:00+00:00' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    text = TestClient(create_app(cfg)).get(f"/jobs/{job_id}").text
    assert "nicht mehr verfügbar" in text


def test_suchformular_hat_neue_felder(tmp_path):
    text = TestClient(create_app(make_cfg(tmp_path))).get("/").text
    assert 'name="seit"' in text
    assert 'name="ohne_zeitarbeit"' in text
    assert 'name="nur_arbeit"' in text
    assert 'name="verschwunden"' in text
```

- [ ] **Schritt 2: Test laufen lassen und Fehlschlag bestätigen**

Ausführen: `uv run pytest tests/test_web_jobs.py -k "faktenliste or warnt or suchformular" -v`
Erwartet: FAIL mit `AssertionError: assert 'Lyoner Str. 12' in ...`

- [ ] **Schritt 3: Detailansicht umsetzen**

In `src/bewerbungs_pipeline/web/templates/_stellendetail.html` nach der Zeile mit `stelle__meta` und vor dem Link einfügen:

```jinja
  {% if stelle.gone_at %}
    <p class="meldung meldung--fehler">
      Diese Anzeige ist bei der Quelle nicht mehr vorhanden.
      Sie wurde am {{ stelle.gone_at[:10] }} als nicht mehr verfügbar erkannt.
    </p>
  {% endif %}

  <dl class="fakten">
    {% set quelle = stelle.source_partner or stelle.external_host %}
    {% if quelle %}<dt>Quelle</dt><dd>{{ quelle }}</dd>{% endif %}
    {% if stelle.employer_kind %}
      <dt>Anbieter</dt>
      <dd>
        {% if stelle.employer_kind == "zeitarbeit" %}Zeitarbeit
        {% elif stelle.employer_kind == "vermittler" %}private Arbeitsvermittlung
        {% else %}Arbeitgeber direkt{% endif %}
      </dd>
    {% endif %}
    {% if stelle.street or stelle.plz %}
      <dt>Adresse</dt>
      <dd>{{ stelle.street or "" }}{% if stelle.street and stelle.plz %}, {% endif %}{{ stelle.plz or "" }} {{ stelle.location }}</dd>
    {% endif %}
    {% if stelle.salary %}<dt>Vergütung</dt><dd>{{ stelle.salary }}</dd>{% endif %}
    {% if stelle.worktime %}<dt>Arbeitszeit</dt><dd>{{ stelle.worktime }}</dd>{% endif %}
    {% if stelle.contract %}<dt>Vertrag</dt><dd>{{ stelle.contract }}</dd>{% endif %}
    {% if stelle.homeoffice %}<dt>Homeoffice</dt><dd>{{ stelle.homeoffice }}</dd>{% endif %}
    {% if stelle.start_date %}<dt>Eintritt</dt><dd>{{ stelle.start_date }}</dd>{% endif %}
    {% if stelle.education %}<dt>Abschluss</dt><dd>{{ stelle.education }}</dd>{% endif %}
    {% if stelle.distance_km is not none %}<dt>Entfernung</dt><dd>{{ stelle.distance_km }} km</dd>{% endif %}
  </dl>
```

- [ ] **Schritt 4: Suchformular und Filter umsetzen**

In `src/bewerbungs_pipeline/web/templates/stellen.html` das Suchformular ersetzen:

```jinja
<form class="suchform" hx-post="/jobs/fetch" hx-target="#fortschritt">
  <input type="search" name="was" placeholder="Was, z. B. Frontend Entwickler"
         aria-label="Wonach suchen" required>
  <input type="search" name="wo" placeholder="Wo, z. B. Darmstadt"
         aria-label="Wo suchen" required>
  <input type="number" name="umkreis" value="50" min="0" max="200" aria-label="Umkreis in km">
  <select name="seit" aria-label="Veröffentlicht seit">
    <option value="">Alter egal</option>
    <option value="7">letzte 7 Tage</option>
    <option value="14">letzte 14 Tage</option>
    <option value="30">letzte 30 Tage</option>
  </select>
  <label class="haken"><input type="checkbox" name="ohne_zeitarbeit" value="1"> ohne Zeitarbeit</label>
  <label class="haken"><input type="checkbox" name="nur_arbeit" value="1"> keine Ausbildung</label>
  <button class="knopf knopf--haupt" type="submit">Stellen suchen</button>
</form>
```

Im Filterbereich hinter dem Ort-Feld ergänzen:

```jinja
      <label class="haken">
        <input type="checkbox" name="verschwunden" value="1">
        auch verschwundene zeigen
      </label>
```

- [ ] **Schritt 5: CSS ergänzen**

In `app.css` ans Dateiende anfügen:

```css
.fakten {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.2rem 0.8rem;
  margin: 0.8rem 0;
  font-size: 0.85rem;
}

.fakten dt { color: var(--text-dim); }
.fakten dd { margin: 0; }

.haken { display: flex; align-items: center; gap: 0.3rem; font-size: 0.85rem; }
```

- [ ] **Schritt 6: README ergänzen**

Im Abschnitt „Benutzung" die `fetch`-Zeile erweitern und den neuen Befehl ergänzen:

```
    uv run jobs fetch --was "Mechatroniker" --wo "Frankfurt" --umkreis 50 \
        --seit 14 --ohne-zeitarbeit --nur-arbeit
    uv run jobs check             # Bestand auf verschwundene Anzeigen prüfen
```

Unter „Weboberfläche" nach dem bestehenden Absatz ergänzen:

```
Jede Suche prüft nebenbei, ob die bereits gespeicherten Anzeigen bei der
Quelle noch vorhanden sind. Verschwundene werden markiert und ausgeblendet,
bleiben aber über „auch verschwundene zeigen" erreichbar — samt einer
eventuell schon erzeugten Bewerbung.
```

- [ ] **Schritt 7: Gesamte Testsuite laufen lassen**

Ausführen: `uv run pytest`
Erwartet: alle Tests PASS

- [ ] **Schritt 8: Altbestand prüfen**

Ausführen: `uv run jobs check`
Erwartet: Ausgabe in der Größenordnung „248 Stellen sind bei der Quelle nicht mehr vorhanden." (die genaue Zahl liegt höher, wenn seit der Messung vom 13.08.2026 weitere Anzeigen abgelaufen sind).

Danach die Weboberfläche starten (`uv run jobs serve`) und mit eigenen Augen prüfen: Liste zeigt Kennzeichen, verschwundene Stellen sind ausgeblendet, das Häkchen holt sie zurück.

- [ ] **Schritt 9: Committen**

```bash
git add src/bewerbungs_pipeline/web/templates/_stellendetail.html src/bewerbungs_pipeline/web/templates/stellen.html src/bewerbungs_pipeline/web/static/app.css tests/test_web_jobs.py README.md
git commit -m "feat(web): Faktenliste im Detail und Suchfilter an der Quelle"
```

---

## Abnahme

Die Prüfkriterien der Spec, abgehakt gegen die Aufgaben:

| Kriterium der Spec | Abgedeckt durch |
|---|---|
| 1 · Migration erhält Bestand | Aufgabe 3, `test_migration_erhaelt_bestandsdaten` |
| 2 · Anreicherung füllt die Felder | Aufgabe 6, `test_enrich_uebernimmt_detailfelder` |
| 3 · 404 beim Holen landet nicht in der DB | Aufgabe 6, `test_enrich_verwirft_verschwundene` |
| 4 · Netzfehler behält die Stelle, ohne `gone_at` | Aufgabe 6, `test_enrich_behaelt_stelle_bei_netzfehler` |
| 5 · Frischeprüfung markiert und meldet | Aufgabe 7, `test_suche_markiert_verschwundene` |
| 6 · Kein Falschalarm bei lebenden Stellen | Aufgabe 6, `test_check_alive_meldet_nur_404` |
| 7 · `employer_kind` bleibt bei fehlenden Merkmalen leer | Aufgabe 1, `test_herkunftsart`; Aufgabe 8, `test_liste_zeigt_leere_felder_nicht` |
| 8 · Vier Gehaltsformate | Aufgabe 1, `test_gehalt` |
| 9 · Suchparameter werden durchgereicht | Aufgabe 6, `test_fetch_jobs_reicht_suchparameter_durch` |
| 10 · Bestehende Tests bleiben grün | Aufgabe 3, 5, 7 — jeweils Schritt „gesamte Suite" |

Kriterium 9 der Spec verlangt zusätzlich einen Nachweis am echten Dienst („liefert nachweislich weniger Treffer"). Das ist in Schritt 8 der Aufgabe 9 von Hand zu prüfen:

```bash
uv run jobs fetch --was "Frontend Entwickler" --wo "Frankfurt" --umkreis 50
uv run jobs fetch --was "Frontend Entwickler" --wo "Frankfurt" --umkreis 50 --seit 7
```

Der zweite Lauf muss weniger Treffer melden als der erste.
