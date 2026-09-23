# Mehrere Vorlagen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Statt einer globalen HTML-Vorlage verwaltet die App beliebig viele Vorlagen (Ordner unter `data/vorlagen/<slug>/`), jede Bewerbung merkt sich ihre Vorlage, Vorlagen lassen sich per ZIP hochladen, duplizieren, umbenennen, löschen und wechseln — in CLI und Web.

**Architecture:** Neues Modul `vorlagen.py` (Ablage, Standard, Liste, Migration) plus `vorlagen_zip.py` (ZIP-Import mit Sicherheitsprüfung). `applications.py` lädt die Vorlage pro Bewerbung (`applications.vorlage`), statt `cfg.template_path` zu nutzen. Web liefert Vorlagen-Assets über eine eigene Route mit Pfadprüfung aus, Vorschauen bekommen eine CSP mit Nonce. Frontend bekommt eine Vorlagen-Seite und ein Dropdown in der Bewerbungsansicht.

**Tech Stack:** Python 3.13, uv, SQLite (ohne ORM), FastAPI, PyYAML, `zipfile`/`html.parser` (stdlib), pytest; Frontend Vite + React + TypeScript + shadcn/ui + TanStack Query, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-23-mehrere-vorlagen-design.md`

## Global Constraints

- Paketmanager `uv`; Tests: `uv run pytest`. `filterwarnings = ["error"]` — jede neue Warnung (inkl. ResourceWarning durch offene Dateien/Verbindungen) lässt Tests fehlschlagen.
- Eine Instanz pro User, keine Accounts. In-Memory-Tasks über `tasks.py` bleiben.
- Code, Kommentare, Meldungen auf Deutsch, Stil wie Bestand (deutsche Bezeichner, keine Typ-Overengineering).
- Vorlagen-Ordner: `data/vorlagen/<slug>/` mit `vorlage.yaml` (`name`, `erstellt` ISO-Datum, `herkunft`), `index.html`, optional `styles.css`, `assets/`.
- `herkunft` ∈ `mitgeliefert` | `migriert` | `zip` | `kopie`.
- Slug: `^[a-z0-9][a-z0-9-]*$`, unveränderlich; Kollision → Suffix `-2`, `-3`, …
- Persönliche Dateien: `data/eigen/portrait.jpg`, `data/eigen/signature.png`; Vorlagen verweisen relativ auf `eigen/portrait.jpg` / `eigen/signature.png`.
- Einstellungen: Tabelle `einstellungen (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL)`, Schlüssel `standard_vorlage`.
- ZIP-Grenzen: max. 10 MB komprimiert, 30 MB entpackt, 200 Einträge. Erlaubte Endungen: `.html .htm .css .png .jpg .jpeg .gif .svg .webp .woff .woff2 .ttf .otf`. `__MACOSX/` und `.DS_Store` werden ignoriert. Kein `<script>`, keine `on*`-Attribute, keine `javascript:`-URLs (auch in SVG).
- Vorschauen senden eine `Content-Security-Policy`, die fremde Skripte blockiert.
- `frontend/dist/` wird nach Frontend-Änderungen neu gebaut und committed.
- Git: Arbeit auf Branch `feature/mehrere-vorlagen`, Commits mit Trailer `Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ`.

**Bewusste Abweichungen von der Spec (Umsetzungsdetails, Verhalten unverändert):**
- Vorschau-Pfade werden weiter über das bestehende `pfade_umschreiben` umgeschrieben (jetzt mit Präfix `/vorlagen-assets/<slug>/`) statt über `<base href>` — gleiche Wirkung, bestehende Tests bleiben nutzbar.
- CSP ist `script-src 'nonce-…'` statt `script-src 'none'`, weil die Vorschau ein eigenes Skalierungsskript injiziert; Skripte aus der Vorlage bleiben blockiert.
- `importiere_zip` liegt in `vorlagen_zip.py` (eigene Verantwortung), nicht in `vorlagen.py`.
- Zusätzliche Config `templates_dir` (Env `TEMPLATES_DIR`, Default `templates`) — Quelle für Migration und Beispielvorlage; nötig, damit Tests nie das echte Repo-Verzeichnis anfassen.
- `applications.template_path` ist in Bestands-DBs `NOT NULL`; neue Bewerbungen schreiben dort `''`.
- Schritt 3 der Migration (Bewerbungen ohne Vorlage) läuft nach Schritt 4 (Beispielvorlage), damit es immer eine Vorlage gibt, auf die gesetzt werden kann.

## Review Focus

1. **Tests oder CLI schreiben ins echte `data/`/`templates/`** — Migration läuft bei jedem Start; ohne Isolierung würde die Testsuite echte Daten verändern. Erwartung: jeder Test arbeitet nur in `tmp_path` (autouse-Fixture in Task 5, Config-Felder ohne Default).
2. **Vorlagen-Asset-Route liefert HTML oder Dateien außerhalb des Vorlagenordners aus** (`/vorlagen-assets/x/../../jobs.db`, `/vorlagen-assets/x/index.html`). Erwartung: 404; HTML wird nur über die CSP-geschützte Vorschau ausgeliefert (Test in Task 6).
3. **ZIP mit gelogener `file_size` im Header (Zip-Bombe)** — Erwartung: Abbruch anhand der tatsächlich gelesenen Bytes (Test in Task 3).
4. **Vorlage einer Bewerbung wurde von Hand gelöscht/kaputt gemacht** — Erwartung: Detailseite lädt weiter (alle Slots sichtbar), Vorschau zeigt Meldung statt 500, Wechsel auf andere Vorlage funktioniert (Tests in Task 5 und 7).
5. **Vorlagenwechsel scheitert am LLM** — Erwartung: Bewerbung behält alte Vorlage, keine halbfertigen Slotzeilen (Test in Task 5).

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `src/bewerbungs_pipeline/db.py` (ändern) | Schema v4: `applications.vorlage`, Tabelle `einstellungen`, `einstellung()`/`setze_einstellung()` |
| `src/bewerbungs_pipeline/config.py` (ändern) | `vorlagen_dir`, `eigen_dir`, `templates_dir` statt `template_path` |
| `src/bewerbungs_pipeline/vorlagen.py` (neu) | Ablage, Laden, Liste, Standard, Kopie, Umbenennen, Löschen, Verweisprüfung, Migration |
| `src/bewerbungs_pipeline/vorlagen_zip.py` (neu) | ZIP-Import + HTML-Sicherheitsprüfung |
| `src/bewerbungs_pipeline/applications.py` (ändern) | Vorlage pro Bewerbung, `wechsle_vorlage` |
| `src/bewerbungs_pipeline/generate.py`, `cli.py` (ändern) | `--vorlage`, `vorlagen`-Unterbefehle, `vorlage-wechseln`, Migration beim Start |
| `src/bewerbungs_pipeline/web/app.py` (ändern) | Mount `/template-assets` raus, Migration beim Start, Router `api_vorlagen` |
| `src/bewerbungs_pipeline/web/routes/preview.py` (ändern) | Präfix pro Vorlage, CSP-Nonce, Vorlagen-Vorschau, Asset-Route, `/eigen/` |
| `src/bewerbungs_pipeline/web/routes/api_vorlagen.py` (neu) | JSON-API der Vorlagenverwaltung |
| `src/bewerbungs_pipeline/web/routes/api_applications.py`, `api_jobs.py`, `api_profile.py`, `schemas.py` (ändern) | `cfg` an `get`, Wechsel-Endpunkt, Upload nach `eigen/`, Schemas |
| `templates/beispiel/` (neu) | neutrale mitgelieferte Vorlage |
| `tests/vorlagen_hilfe.py` (neu) | Test-Helfer: Vorlage anlegen, Config bauen |
| `frontend/src/features/vorlagen/*` (neu) | Vorlagen-Seite, Karte, Namensdialog, Löschsperre |
| `frontend/src/features/bewerbung/BewerbungPage.tsx`, `profil/ProfilPage.tsx`, `lib/api.ts`, `types/api.ts`, `App.tsx`, `main.tsx`, `vite.config.ts` (ändern) | Anbindung |

---

### Task 1: DB-Schema v4 — Spalte `vorlage`, Tabelle `einstellungen`

**Files:**
- Modify: `src/bewerbungs_pipeline/db.py:23` (`SCHEMA_VERSION`), `:93-102` (`SCHEMA_APPLICATIONS`), `:127-138` (`_migrate`), `:141-154` (`connect`)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `db.einstellung(conn, schluessel: str) -> str | None`, `db.setze_einstellung(conn, schluessel: str, wert: str) -> None`; Spalte `applications.vorlage TEXT` (nullable).

- [ ] **Step 1: Failing tests schreiben** — ans Ende von `tests/test_db.py`:

```python
def test_einstellung_fehlt_liefert_none(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    assert db.einstellung(conn, "standard_vorlage") is None


def test_setze_einstellung_ueberschreibt(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    db.setze_einstellung(conn, "standard_vorlage", "a")
    db.setze_einstellung(conn, "standard_vorlage", "b")
    assert db.einstellung(conn, "standard_vorlage") == "b"


def test_applications_hat_spalte_vorlage(tmp_path):
    conn = db.connect(tmp_path / "jobs.db")
    spalten = {z["name"] for z in conn.execute("PRAGMA table_info(applications)")}
    assert "vorlage" in spalten


def test_migration_v4_ruestet_vorlage_nach(tmp_path):
    """Bestands-DB ohne Spalte `vorlage` (Schema v3) bekommt sie beim Öffnen."""
    import sqlite3

    pfad = tmp_path / "jobs.db"
    alt = sqlite3.connect(pfad)
    alt.execute(db.SCHEMA)
    alt.execute(
        """CREATE TABLE applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            template_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(job_id))"""
    )
    alt.execute("PRAGMA user_version = 3")
    alt.commit()
    alt.close()

    conn = db.connect(pfad)
    spalten = {z["name"] for z in conn.execute("PRAGMA table_info(applications)")}
    assert "vorlage" in spalten
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_db.py -k "einstellung or vorlage" -v`
Expected: FAIL (`AttributeError: module 'bewerbungs_pipeline.db' has no attribute 'einstellung'` bzw. Spalte fehlt)

- [ ] **Step 3: Implementieren** in `db.py`:

`SCHEMA_VERSION = 3` → `SCHEMA_VERSION = 4`.

`SCHEMA_APPLICATIONS` um die Spalte ergänzen (nach `template_path`):

```python
SCHEMA_APPLICATIONS = """
CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER NOT NULL REFERENCES jobs(id),
    template_path TEXT NOT NULL,
    vorlage       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(job_id)
)
"""

SCHEMA_EINSTELLUNGEN = """
CREATE TABLE IF NOT EXISTS einstellungen (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT NOT NULL
)
"""
```

In `_migrate` nach dem `version < 3`-Block:

```python
    if version < 4:
        # Vorlage pro Bewerbung (Slug unter data/vorlagen/). template_path
        # bleibt als Altspalte stehen — DROP COLUMN lohnt den Umbau nicht.
        spalten = {
            zeile["name"]
            for zeile in conn.execute("PRAGMA table_info(applications)").fetchall()
        }
        if "vorlage" not in spalten:
            conn.execute("ALTER TABLE applications ADD COLUMN vorlage TEXT")
```

In `connect` nach `conn.execute(SCHEMA_APPLICATION_SLOTS)`:

```python
    conn.execute(SCHEMA_EINSTELLUNGEN)
```

Neue Funktionen direkt nach `connect`:

```python
def einstellung(conn: sqlite3.Connection, schluessel: str) -> str | None:
    zeile = conn.execute(
        "SELECT wert FROM einstellungen WHERE schluessel = ?", (schluessel,)
    ).fetchone()
    return zeile["wert"] if zeile else None


def setze_einstellung(conn: sqlite3.Connection, schluessel: str, wert: str) -> None:
    conn.execute(
        """INSERT INTO einstellungen (schluessel, wert) VALUES (?, ?)
           ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert""",
        (schluessel, wert),
    )
    conn.commit()
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (alle, auch Bestand)

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/db.py tests/test_db.py
git commit -m "feat(db): Schema v4 mit Vorlage pro Bewerbung und Einstellungen

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 2: Config-Felder und Kernmodul `vorlagen.py`

**Files:**
- Modify: `src/bewerbungs_pipeline/config.py`
- Create: `src/bewerbungs_pipeline/vorlagen.py`
- Create: `tests/vorlagen_hilfe.py`
- Test: `tests/test_vorlagen.py`

**Interfaces:**
- Consumes: `db.einstellung`, `db.setze_einstellung` (Task 1); `slots.extract_slots`; `applications.slugify` (lazy import, sonst Zirkelimport).
- Produces:
  - `Config.vorlagen_dir: Path`, `Config.eigen_dir: Path`, `Config.templates_dir: Path` (in diesem Task noch mit Defaults, Task 5 macht sie Pflicht)
  - `class VorlagenError(Exception)`, `class VorlageFehlt(VorlagenError)`, `class VorlageInBenutzung(VorlagenError)`
  - `EIGEN_DATEIEN = ("portrait.jpg", "signature.png")`
  - `ordner(cfg, slug) -> Path`, `lade(cfg, slug) -> tuple[str, dict[str, str]]`, `slugs(cfg) -> list[str]`
  - `standard(cfg, conn) -> str`, `setze_standard(cfg, conn, slug) -> None`
  - `liste(cfg, conn) -> list[dict]` (Schlüssel: `slug, name, herkunft, erstellt, slots: list[str], ist_standard: bool, nutzungen: int, fehler: str | None`)
  - `neuer_slug(cfg, name) -> str`, `schreibe_meta(pfad, name, herkunft) -> None`
  - `dupliziere(cfg, slug, name) -> str`, `umbenennen(cfg, slug, name) -> None`, `loesche(cfg, conn, slug) -> None`
  - `fehlende_verweise(html_datei: Path) -> list[str]`
  - Test-Helfer: `vorlage_anlegen(vorlagen_dir, slug="mini", html_datei=FIXTURES/"template_mini.html", name=None) -> Path`

- [ ] **Step 1: Config ergänzen** — in `config.py` nach `web_token`:

```python
    web_token: str = ""
    vorlagen_dir: Path = Path("data/vorlagen")
    eigen_dir: Path = Path("data/eigen")
    templates_dir: Path = Path("templates")
```

und in `load_config()`:

```python
        web_token=os.getenv("JOBS_WEB_TOKEN", ""),
        vorlagen_dir=Path(os.getenv("VORLAGEN_DIR", "data/vorlagen")),
        eigen_dir=Path(os.getenv("EIGEN_DIR", "data/eigen")),
        templates_dir=Path(os.getenv("TEMPLATES_DIR", "templates")),
```

- [ ] **Step 2: Test-Helfer anlegen** — `tests/vorlagen_hilfe.py` (kein `test_`-Präfix, damit pytest ihn nicht sammelt; Import in Tests per `from vorlagen_hilfe import …` klappt, weil pytest das Testverzeichnis in `sys.path` einfügt):

```python
"""Helfer für Tests, die Vorlagen-Ordner brauchen."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def vorlage_anlegen(
    vorlagen_dir: Path,
    slug: str = "mini",
    html_datei: Path = FIXTURES / "template_mini.html",
    name: str | None = None,
) -> Path:
    ordner = vorlagen_dir / slug
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "index.html").write_text(html_datei.read_text())
    (ordner / "vorlage.yaml").write_text(
        f"name: {name or slug}\nherkunft: zip\nerstellt: '2026-09-23'\n"
    )
    return ordner
```

- [ ] **Step 3: Failing tests schreiben** — `tests/test_vorlagen.py`:

```python
from dataclasses import replace
from pathlib import Path

import pytest
from vorlagen_hilfe import vorlage_anlegen

from bewerbungs_pipeline import db, vorlagen
from bewerbungs_pipeline.config import Config


def make_cfg(tmp_path) -> Config:
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=tmp_path / "unbenutzt.html",
        profile_path=tmp_path / "profile.yaml",
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        vorlagen_dir=tmp_path / "vorlagen",
        eigen_dir=tmp_path / "eigen",
        templates_dir=tmp_path / "templates",
    )


def test_lade_liefert_html_und_slots(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir)
    html, slots = vorlagen.lade(cfg, "mini")
    assert "AC Motoren" in html
    assert set(slots) == {"titel", "firma", "einstieg", "motivation"}


def test_lade_fehlende_vorlage(tmp_path):
    with pytest.raises(vorlagen.VorlageFehlt, match="fehlt"):
        vorlagen.lade(make_cfg(tmp_path), "gibtsnicht")


def test_lade_kaputte_vorlage(tmp_path):
    cfg = make_cfg(tmp_path)
    ordner = vorlage_anlegen(cfg.vorlagen_dir)
    (ordner / "index.html").write_text('<p data-slot="x">kaputt')
    with pytest.raises(vorlagen.VorlagenError, match="Vorlage fehlerhaft"):
        vorlagen.lade(cfg, "mini")


def test_lade_ohne_slots(tmp_path):
    cfg = make_cfg(tmp_path)
    ordner = vorlage_anlegen(cfg.vorlagen_dir)
    (ordner / "index.html").write_text("<p>nichts</p>")
    with pytest.raises(vorlagen.VorlagenError, match="keine data-slot"):
        vorlagen.lade(cfg, "mini")


@pytest.mark.parametrize("slug", ["../x", "a/b", "", "Gross", ".tmp-1"])
def test_ordner_weist_ungueltigen_slug_ab(tmp_path, slug):
    with pytest.raises(vorlagen.VorlageFehlt):
        vorlagen.ordner(make_cfg(tmp_path), slug)


def test_standard_ohne_vorlagen(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    with pytest.raises(vorlagen.VorlagenError, match="Keine Vorlage"):
        vorlagen.standard(cfg, conn)


def test_standard_faellt_auf_erste_vorlage_zurueck(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "b")
    vorlage_anlegen(cfg.vorlagen_dir, "a")
    conn = db.connect(cfg.db_path)
    assert vorlagen.standard(cfg, conn) == "a"
    db.setze_einstellung(conn, "standard_vorlage", "weg")
    assert vorlagen.standard(cfg, conn) == "a"


def test_setze_standard(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "a")
    vorlage_anlegen(cfg.vorlagen_dir, "b")
    conn = db.connect(cfg.db_path)
    vorlagen.setze_standard(cfg, conn, "b")
    assert vorlagen.standard(cfg, conn) == "b"
    with pytest.raises(vorlagen.VorlageFehlt):
        vorlagen.setze_standard(cfg, conn, "c")


def test_liste_markiert_kaputte_vorlage_statt_zu_scheitern(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "gut", name="Gute Vorlage")
    kaputt = vorlage_anlegen(cfg.vorlagen_dir, "kaputt")
    (kaputt / "index.html").write_text("<p>ohne slots</p>")
    conn = db.connect(cfg.db_path)
    eintraege = {e["slug"]: e for e in vorlagen.liste(cfg, conn)}
    assert eintraege["gut"]["name"] == "Gute Vorlage"
    assert eintraege["gut"]["fehler"] is None
    assert eintraege["gut"]["ist_standard"] is True
    assert "firma" in eintraege["gut"]["slots"]
    assert eintraege["kaputt"]["fehler"]


def test_liste_zaehlt_nutzungen(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "a")
    conn = db.connect(cfg.db_path)
    conn.execute("INSERT INTO jobs (url, dedupe_hash, title, company, location, source, scraped_at) VALUES ('u', 'h', 't', 'c', 'l', 's', 'x')")
    conn.execute("INSERT INTO applications (job_id, template_path, vorlage, created_at, updated_at) VALUES (1, '', 'a', 'x', 'x')")
    conn.commit()
    assert vorlagen.liste(cfg, conn)[0]["nutzungen"] == 1


def test_neuer_slug_vermeidet_kollision(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "modern-blau")
    assert vorlagen.neuer_slug(cfg, "Modern Blau") == "modern-blau-2"
    assert vorlagen.neuer_slug(cfg, "Grün") == "gruen"


def test_neuer_slug_ohne_name(tmp_path):
    with pytest.raises(vorlagen.VorlagenError, match="Name"):
        vorlagen.neuer_slug(make_cfg(tmp_path), "  ")


def test_dupliziere(tmp_path):
    cfg = make_cfg(tmp_path)
    quelle = vorlage_anlegen(cfg.vorlagen_dir, "a")
    (quelle / "styles.css").write_text("body{}")
    slug = vorlagen.dupliziere(cfg, "a", "Kopie von A")
    assert slug == "kopie-von-a"
    assert (cfg.vorlagen_dir / slug / "styles.css").read_text() == "body{}"
    eintrag = next(e for e in vorlagen.liste(cfg, db.connect(cfg.db_path)) if e["slug"] == slug)
    assert eintrag["name"] == "Kopie von A"
    assert eintrag["herkunft"] == "kopie"


def test_umbenennen_aendert_nur_namen(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "a")
    vorlagen.umbenennen(cfg, "a", "Neu")
    eintrag = vorlagen.liste(cfg, db.connect(cfg.db_path))[0]
    assert (eintrag["slug"], eintrag["name"]) == ("a", "Neu")


def test_loesche_verweigert_bei_nutzung(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "a")
    vorlage_anlegen(cfg.vorlagen_dir, "b")
    conn = db.connect(cfg.db_path)
    conn.execute("INSERT INTO jobs (url, dedupe_hash, title, company, location, source, scraped_at) VALUES ('u', 'h', 't', 'c', 'l', 's', 'x')")
    conn.execute("INSERT INTO applications (job_id, template_path, vorlage, created_at, updated_at) VALUES (1, '', 'b', 'x', 'x')")
    conn.commit()
    with pytest.raises(vorlagen.VorlageInBenutzung, match="1 Bewerbung"):
        vorlagen.loesche(cfg, conn, "b")


def test_loesche_verweigert_standard(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "a")
    conn = db.connect(cfg.db_path)
    with pytest.raises(vorlagen.VorlageInBenutzung, match="Standard"):
        vorlagen.loesche(cfg, conn, "a")


def test_loesche_entfernt_ordner(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "a")
    vorlage_anlegen(cfg.vorlagen_dir, "b")
    conn = db.connect(cfg.db_path)
    vorlagen.loesche(cfg, conn, "b")
    assert not (cfg.vorlagen_dir / "b").exists()


def test_fehlende_verweise(tmp_path):
    datei = tmp_path / "index.html"
    (tmp_path / "da.png").write_bytes(b"x")
    datei.write_text(
        '<img src="da.png"><img src="weg.png"><img src="eigen/portrait.jpg">'
        '<a href="mailto:a@b.de">m</a><a href="https://x.de">x</a>'
    )
    assert vorlagen.fehlende_verweise(datei) == ["weg.png"]
```

- [ ] **Step 4: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_vorlagen.py -v`
Expected: FAIL (`ModuleNotFoundError`/`ImportError: cannot import name 'vorlagen'`)

- [ ] **Step 5: `vorlagen.py` implementieren**

```python
"""Bewerbungsvorlagen: je Vorlage ein Ordner unter cfg.vorlagen_dir.

Aufbau eines Vorlagen-Ordners (siehe Spec 2026-09-23-mehrere-vorlagen):
vorlage.yaml (name, erstellt, herkunft), index.html mit data-slot-Blöcken,
optional styles.css und assets/. Der Ordnername ist der Slug — auf ihn
verweisen Bewerbungen, deshalb ändert Umbenennen nur den Anzeigenamen.
"""

import re
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

import yaml

from . import db as dbmod
from .config import Config
from .slots import extract_slots

SLUG_MUSTER = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Persönliche Dateien liegen in cfg.eigen_dir und gelten für alle Vorlagen;
# Vorlagen verweisen relativ auf eigen/<datei>.
EIGEN_DATEIEN = ("portrait.jpg", "signature.png")

_VERWEIS_RE = re.compile(r'(?:href|src)="(?!https?:|mailto:|tel:|data:|#)([^"]+)"')


class VorlagenError(Exception):
    """Fachlicher Fehler mit deutscher, benutzertauglicher Meldung."""


class VorlageFehlt(VorlagenError):
    pass


class VorlageInBenutzung(VorlagenError):
    pass


def ordner(cfg: Config, slug: str) -> Path:
    # Slug kommt auch aus URLs — nur das Muster verhindert ../-Ausflüge.
    if not SLUG_MUSTER.match(slug):
        raise VorlageFehlt(f"Unbekannte Vorlage: {slug!r}")
    return cfg.vorlagen_dir / slug


def _existiert(cfg: Config, slug: str) -> bool:
    return (ordner(cfg, slug) / "index.html").is_file()


def _pruefe_vorhanden(cfg: Config, slug: str) -> Path:
    pfad = ordner(cfg, slug)
    if not (pfad / "index.html").is_file():
        raise VorlageFehlt(f"Vorlage „{slug}“ fehlt — andere Vorlage wählen.")
    return pfad


def lade(cfg: Config, slug: str) -> tuple[str, dict[str, str]]:
    html = (_pruefe_vorhanden(cfg, slug) / "index.html").read_text()
    try:
        slots = extract_slots(html)
    except ValueError as exc:
        raise VorlagenError(f"Vorlage fehlerhaft („{slug}“): {exc}") from exc
    if not slots:
        raise VorlagenError(f"Vorlage „{slug}“ enthält keine data-slot-Markierungen.")
    return html, slots


def slugs(cfg: Config) -> list[str]:
    if not cfg.vorlagen_dir.is_dir():
        return []
    return sorted(
        p.name
        for p in cfg.vorlagen_dir.iterdir()
        if p.is_dir() and SLUG_MUSTER.match(p.name) and (p / "index.html").is_file()
    )


def _meta(pfad: Path) -> dict:
    datei = pfad / "vorlage.yaml"
    if not datei.exists():
        return {}
    return yaml.safe_load(datei.read_text()) or {}


def schreibe_meta(pfad: Path, name: str, herkunft: str) -> None:
    (pfad / "vorlage.yaml").write_text(
        yaml.safe_dump(
            {"name": name, "erstellt": date.today().isoformat(), "herkunft": herkunft},
            allow_unicode=True,
            sort_keys=False,
        )
    )


def standard(cfg: Config, conn: sqlite3.Connection) -> str:
    vorhanden = slugs(cfg)
    if not vorhanden:
        raise VorlagenError("Keine Vorlage vorhanden — erst eine anlegen oder hochladen.")
    gesetzt = dbmod.einstellung(conn, "standard_vorlage")
    if gesetzt in vorhanden:
        return gesetzt
    if gesetzt is not None:
        print(
            f"Warnung: Standardvorlage „{gesetzt}“ fehlt, nutze „{vorhanden[0]}“.",
            file=sys.stderr,
        )
    return vorhanden[0]


def setze_standard(cfg: Config, conn: sqlite3.Connection, slug: str) -> None:
    lade(cfg, slug)
    dbmod.setze_einstellung(conn, "standard_vorlage", slug)


def _nutzungen(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        zeile["vorlage"]: zeile["anzahl"]
        for zeile in conn.execute(
            "SELECT vorlage, COUNT(*) AS anzahl FROM applications GROUP BY vorlage"
        ).fetchall()
    }


def liste(cfg: Config, conn: sqlite3.Connection) -> list[dict]:
    vorhanden = slugs(cfg)
    std = standard(cfg, conn) if vorhanden else None
    nutzungen = _nutzungen(conn)
    eintraege = []
    for slug in vorhanden:
        meta = _meta(ordner(cfg, slug))
        try:
            slot_namen = list(lade(cfg, slug)[1])
            fehler = None
        except VorlagenError as exc:
            slot_namen, fehler = [], str(exc)
        eintraege.append(
            {
                "slug": slug,
                "name": meta.get("name") or slug,
                "herkunft": meta.get("herkunft") or "unbekannt",
                "erstellt": str(meta.get("erstellt") or ""),
                "slots": slot_namen,
                "ist_standard": slug == std,
                "nutzungen": nutzungen.get(slug, 0),
                "fehler": fehler,
            }
        )
    return eintraege


def neuer_slug(cfg: Config, name: str) -> str:
    # Lazy: applications importiert dieses Modul.
    from .applications import slugify

    if not name.strip():
        raise VorlagenError("Name fehlt.")
    basis = slugify(name)
    kandidat, nummer = basis, 2
    while (cfg.vorlagen_dir / kandidat).exists():
        kandidat = f"{basis}-{nummer}"
        nummer += 1
    return kandidat


def dupliziere(cfg: Config, slug: str, name: str) -> str:
    quelle = _pruefe_vorhanden(cfg, slug)
    neu = neuer_slug(cfg, name)
    ziel = cfg.vorlagen_dir / neu
    shutil.copytree(quelle, ziel)
    schreibe_meta(ziel, name.strip(), "kopie")
    return neu


def umbenennen(cfg: Config, slug: str, name: str) -> None:
    pfad = _pruefe_vorhanden(cfg, slug)
    if not name.strip():
        raise VorlagenError("Name fehlt.")
    meta = _meta(pfad)
    meta["name"] = name.strip()
    (pfad / "vorlage.yaml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    )


def loesche(cfg: Config, conn: sqlite3.Connection, slug: str) -> None:
    pfad = _pruefe_vorhanden(cfg, slug)
    anzahl = _nutzungen(conn).get(slug, 0)
    if anzahl:
        raise VorlageInBenutzung(
            f"Vorlage „{slug}“ wird von {anzahl} Bewerbung(en) genutzt."
        )
    if standard(cfg, conn) == slug:
        raise VorlageInBenutzung(
            f"Vorlage „{slug}“ ist Standard — erst eine andere als Standard setzen."
        )
    shutil.rmtree(pfad)


def fehlende_verweise(html_datei: Path) -> list[str]:
    """Relative Verweise der Datei, die ins Leere zeigen.

    eigen/… zählt als vorhanden: diese Dateien kommen erst beim Export bzw.
    über die Vorschau-Route dazu.
    """
    basis = html_datei.parent
    return sorted(
        {
            ziel
            for ziel in _VERWEIS_RE.findall(html_datei.read_text())
            if not ziel.startswith("eigen/") and not (basis / ziel).exists()
        }
    )
```

- [ ] **Step 6: Tests laufen lassen**

Run: `uv run pytest tests/test_vorlagen.py -v && uv run pytest`
Expected: PASS (neue Tests und gesamte Suite)

- [ ] **Step 7: Commit**

```bash
git add src/bewerbungs_pipeline/config.py src/bewerbungs_pipeline/vorlagen.py tests/vorlagen_hilfe.py tests/test_vorlagen.py
git commit -m "feat: Modul vorlagen für mehrere Bewerbungsvorlagen

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 3: ZIP-Import mit Sicherheitsprüfung (`vorlagen_zip.py`)

**Files:**
- Create: `src/bewerbungs_pipeline/vorlagen_zip.py`
- Test: `tests/test_vorlagen_zip.py`

**Interfaces:**
- Consumes: `vorlagen.VorlagenError`, `vorlagen.neuer_slug`, `vorlagen.schreibe_meta`, `vorlagen.fehlende_verweise`, `slots.extract_slots`.
- Produces: `vorlagen_zip.MAX_KOMPRIMIERT: int`, `vorlagen_zip.importiere_zip(cfg, datei: Path, name: str) -> tuple[str, list[str]]` (Slug, Warnungen), `vorlagen_zip.unsichere_stellen(text: str) -> list[str]`.

- [ ] **Step 1: Failing tests schreiben** — `tests/test_vorlagen_zip.py`:

```python
import io
import stat
import zipfile
from pathlib import Path

import pytest
from vorlagen_hilfe import FIXTURES

from bewerbungs_pipeline import vorlagen, vorlagen_zip
from bewerbungs_pipeline.config import Config

INDEX = (FIXTURES / "template_assets.html").read_text()


def make_cfg(tmp_path) -> Config:
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=tmp_path / "unbenutzt.html",
        profile_path=tmp_path / "profile.yaml",
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        vorlagen_dir=tmp_path / "vorlagen",
        eigen_dir=tmp_path / "eigen",
        templates_dir=tmp_path / "templates",
    )


def zip_bauen(tmp_path, eintraege: dict[str, bytes | str], name="vorlage.zip") -> Path:
    pfad = tmp_path / name
    with zipfile.ZipFile(pfad, "w") as zf:
        for datei, inhalt in eintraege.items():
            zf.writestr(datei, inhalt)
    return pfad


def test_gueltiges_zip(tmp_path):
    cfg = make_cfg(tmp_path)
    datei = zip_bauen(tmp_path, {"index.html": INDEX, "styles.css": "body{}"})
    slug, warnungen = vorlagen_zip.importiere_zip(cfg, datei, "Modern")
    assert slug == "modern"
    assert warnungen == []
    assert (cfg.vorlagen_dir / "modern" / "styles.css").exists()
    assert vorlagen.lade(cfg, "modern")[1]["firma"] == "AC Motoren GmbH"
    assert "herkunft: zip" in (cfg.vorlagen_dir / "modern" / "vorlage.yaml").read_text()


def test_unterordner_wird_wurzel(tmp_path):
    cfg = make_cfg(tmp_path)
    datei = zip_bauen(
        tmp_path,
        {"meine/index.html": INDEX, "meine/styles.css": "", "__MACOSX/x": "", "meine/.DS_Store": ""},
    )
    slug, _ = vorlagen_zip.importiere_zip(cfg, datei, "X")
    assert (cfg.vorlagen_dir / slug / "index.html").exists()
    assert not (cfg.vorlagen_dir / slug / "__MACOSX").exists()


def test_fehlendes_asset_ist_nur_warnung(tmp_path):
    cfg = make_cfg(tmp_path)
    datei = zip_bauen(tmp_path, {"index.html": INDEX})
    _, warnungen = vorlagen_zip.importiere_zip(cfg, datei, "X")
    assert warnungen == ["Verweis ins Leere: styles.css"]


@pytest.mark.parametrize(
    ("eintraege", "meldung"),
    [
        ({"../boese.html": INDEX}, "Unzulässiger Pfad"),
        ({"/abs/index.html": INDEX}, "Unzulässiger Pfad"),
        ({"index.html": INDEX, "tool.exe": "x"}, "Nicht erlaubte Dateien: tool.exe"),
        ({"index.html": INDEX.replace("</body>", "<script>alert(1)</script></body>")}, "<script>"),
        ({"index.html": INDEX.replace("<h1 ", '<h1 onclick="x()" ')}, "onclick"),
        ({"index.html": INDEX.replace("</body>", '<a href="javascript:x()">x</a></body>')}, "javascript:"),
        ({"index.html": INDEX, "assets/a.svg": '<svg><script>x</script></svg>'}, "<script>"),
        ({"index.html": "<p>ohne slots</p>"}, "keine data-slot"),
        ({"styles.css": ""}, "index.html fehlt"),
        ({"a/index.html": INDEX, "b/index.html": INDEX}, "mehrere index.html"),
        ({"a/index.html": INDEX, "lose.css": ""}, "außerhalb"),
    ],
)
def test_ungueltige_zips(tmp_path, eintraege, meldung):
    cfg = make_cfg(tmp_path)
    datei = zip_bauen(tmp_path, eintraege)
    with pytest.raises(vorlagen.VorlagenError, match=meldung.replace("(", r"\(")):
        vorlagen_zip.importiere_zip(cfg, datei, "X")
    # Nichts bleibt liegen, auch kein Temp-Ordner.
    assert not cfg.vorlagen_dir.exists() or list(cfg.vorlagen_dir.iterdir()) == []


def test_symlink_wird_abgelehnt(tmp_path):
    cfg = make_cfg(tmp_path)
    pfad = tmp_path / "link.zip"
    with zipfile.ZipFile(pfad, "w") as zf:
        zf.writestr("index.html", INDEX)
        info = zipfile.ZipInfo("assets/link.png")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(vorlagen.VorlagenError, match="Symlink"):
        vorlagen_zip.importiere_zip(cfg, pfad, "X")


def test_kein_zip(tmp_path):
    cfg = make_cfg(tmp_path)
    datei = tmp_path / "x.zip"
    datei.write_text("kein zip")
    with pytest.raises(vorlagen.VorlagenError, match="Keine gültige ZIP"):
        vorlagen_zip.importiere_zip(cfg, datei, "X")


def test_zu_viele_eintraege(tmp_path):
    cfg = make_cfg(tmp_path)
    eintraege = {"index.html": INDEX} | {f"assets/{i}.png": "x" for i in range(200)}
    with pytest.raises(vorlagen.VorlagenError, match="Zu viele Dateien"):
        vorlagen_zip.importiere_zip(cfg, zip_bauen(tmp_path, eintraege), "X")


def test_zip_bombe_mit_gelogener_groesse(tmp_path, monkeypatch):
    """Der Header kann eine kleine file_size behaupten — gezählt wird, was
    tatsächlich herauskommt."""
    cfg = make_cfg(tmp_path)
    monkeypatch.setattr(vorlagen_zip, "MAX_ENTPACKT", 1000)
    datei = zip_bauen(tmp_path, {"index.html": INDEX, "assets/gross.png": b"\0" * 5000})
    original = zipfile.ZipFile.infolist

    def luegend(self):
        infos = original(self)
        for info in infos:
            info.file_size = 1
        return infos

    monkeypatch.setattr(zipfile.ZipFile, "infolist", luegend)
    with pytest.raises(vorlagen.VorlagenError, match="zu groß"):
        vorlagen_zip.importiere_zip(cfg, datei, "X")


def test_slug_kollision(tmp_path):
    cfg = make_cfg(tmp_path)
    datei = zip_bauen(tmp_path, {"index.html": INDEX})
    assert vorlagen_zip.importiere_zip(cfg, datei, "X")[0] == "x"
    assert vorlagen_zip.importiere_zip(cfg, datei, "X")[0] == "x-2"
```

Hinweis zum Bomben-Test: Wenn `ZipFile.open` wegen der manipulierten `file_size` mit `zipfile.BadZipFile` („Bad CRC“ o. ä.) abbricht, bevor das Limit greift, prüft die Implementierung das Limit **vor** dem CRC-Abgleich, indem sie blockweise liest (siehe unten, `_lies_begrenzt`). Der Test muss mit „zu groß“ scheitern, nicht mit „Keine gültige ZIP“.

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_vorlagen_zip.py -v`
Expected: FAIL (`ImportError: cannot import name 'vorlagen_zip'`)

- [ ] **Step 3: `vorlagen_zip.py` implementieren**

```python
"""Import fertiger HTML-Vorlagen als ZIP.

Uploads sind fremde Dateien: sie landen im Vorschau-iframe und im
Export-Chromium. Darum werden Pfade, Größe, Dateitypen und aktive Inhalte
geprüft, bevor irgendetwas im Vorlagen-Ordner ankommt.
"""

import shutil
import stat
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

from .config import Config
from .slots import extract_slots
from .vorlagen import VorlagenError, fehlende_verweise, neuer_slug, schreibe_meta

MAX_KOMPRIMIERT = 10 * 1024 * 1024
MAX_ENTPACKT = 30 * 1024 * 1024
MAX_EINTRAEGE = 200
ERLAUBTE_ENDUNGEN = {
    ".html", ".htm", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".webp", ".woff", ".woff2", ".ttf", ".otf",
}
_AKTIVE_ENDUNGEN = {".html", ".htm", ".svg"}
_URL_ATTRIBUTE = {"href", "src", "xlink:href", "action", "formaction"}


class _AktivInhaltParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.funde: list[str] = []

    def _pruefe(self, tag: str, attrs) -> None:
        if tag == "script":
            self.funde.append("<script>")
        for name, wert in attrs:
            name = name.lower()
            if name.startswith("on"):
                self.funde.append(f"{name}-Attribut")
            if name in _URL_ATTRIBUTE and (wert or "").strip().lower().startswith("javascript:"):
                self.funde.append("javascript:-Verweis")

    def handle_starttag(self, tag, attrs):
        self._pruefe(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._pruefe(tag, attrs)


def unsichere_stellen(text: str) -> list[str]:
    parser = _AktivInhaltParser()
    parser.feed(text)
    parser.close()
    return sorted(set(parser.funde))


def _ignoriert(name: str) -> bool:
    return name.startswith("__MACOSX/") or PurePosixPath(name).name == ".DS_Store"


def _pruefe_eintrag(info: zipfile.ZipInfo) -> None:
    name = info.filename
    teile = PurePosixPath(name).parts
    if name.startswith("/") or "\\" in name or ".." in teile or ":" in name:
        raise VorlagenError(f"Unzulässiger Pfad im ZIP: {name}")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise VorlagenError(f"Symlink im ZIP nicht erlaubt: {name}")


def _wurzel(namen: list[str]) -> str:
    kandidaten = [
        n for n in namen
        if PurePosixPath(n).name == "index.html" and len(PurePosixPath(n).parts) <= 2
    ]
    if not kandidaten:
        raise VorlagenError("index.html fehlt (im ZIP oder in genau einem Unterordner).")
    if len(kandidaten) > 1:
        raise VorlagenError("ZIP enthält mehrere index.html — unklar, welche gilt.")
    wurzel = str(PurePosixPath(kandidaten[0]).parent)
    if wurzel == ".":
        return ""
    wurzel += "/"
    ausserhalb = [n for n in namen if not n.startswith(wurzel)]
    if ausserhalb:
        raise VorlagenError(f"Dateien außerhalb von {wurzel}: {', '.join(ausserhalb)}")
    return wurzel


def _lies_begrenzt(zf: zipfile.ZipFile, info: zipfile.ZipInfo, rest: int) -> bytes:
    """Liest blockweise und bricht ab, sobald mehr herauskommt als erlaubt —
    die file_size im Header kann lügen."""
    teile, gelesen = [], 0
    with zf.open(info) as quelle:
        while block := quelle.read(64 * 1024):
            gelesen += len(block)
            if gelesen > rest:
                raise VorlagenError("ZIP entpackt zu groß (max. 30 MB).")
            teile.append(block)
    return b"".join(teile)


def importiere_zip(cfg: Config, datei: Path, name: str) -> tuple[str, list[str]]:
    if datei.stat().st_size > MAX_KOMPRIMIERT:
        raise VorlagenError("ZIP zu groß (max. 10 MB).")
    try:
        zf = zipfile.ZipFile(datei)
    except zipfile.BadZipFile as exc:
        raise VorlagenError("Keine gültige ZIP-Datei.") from exc

    cfg.vorlagen_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".tmp-", dir=cfg.vorlagen_dir))
    try:
        with zf:
            eintraege = [
                i for i in zf.infolist() if not i.is_dir() and not _ignoriert(i.filename)
            ]
            if len(eintraege) > MAX_EINTRAEGE:
                raise VorlagenError(f"Zu viele Dateien im ZIP (max. {MAX_EINTRAEGE}).")
            for info in eintraege:
                _pruefe_eintrag(info)
            verboten = sorted(
                i.filename for i in eintraege
                if PurePosixPath(i.filename).suffix.lower() not in ERLAUBTE_ENDUNGEN
            )
            if verboten:
                raise VorlagenError(f"Nicht erlaubte Dateien: {', '.join(verboten)}")
            if sum(i.file_size for i in eintraege) > MAX_ENTPACKT:
                raise VorlagenError("ZIP entpackt zu groß (max. 30 MB).")
            wurzel = _wurzel([i.filename for i in eintraege])

            rest = MAX_ENTPACKT
            for info in eintraege:
                try:
                    daten = _lies_begrenzt(zf, info, rest)
                except zipfile.BadZipFile as exc:
                    raise VorlagenError("Keine gültige ZIP-Datei.") from exc
                rest -= len(daten)
                ziel = tmp / info.filename[len(wurzel):]
                ziel.parent.mkdir(parents=True, exist_ok=True)
                ziel.write_bytes(daten)

        for pfad in tmp.rglob("*"):
            if pfad.suffix.lower() in _AKTIVE_ENDUNGEN:
                try:
                    text = pfad.read_text(encoding="utf-8")
                except UnicodeDecodeError as exc:
                    raise VorlagenError(f"{pfad.name} ist nicht UTF-8-kodiert.") from exc
                funde = unsichere_stellen(text)
                if funde:
                    raise VorlagenError(
                        f"{pfad.relative_to(tmp)} enthält aktive Inhalte: {', '.join(funde)}"
                    )

        index = tmp / "index.html"
        try:
            slots = extract_slots(index.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise VorlagenError(f"Vorlage fehlerhaft: {exc}") from exc
        if not slots:
            raise VorlagenError("index.html enthält keine data-slot-Markierungen.")

        warnungen = [f"Verweis ins Leere: {z}" for z in fehlende_verweise(index)]
        slug = neuer_slug(cfg, name)
        schreibe_meta(tmp, name.strip(), "zip")
        tmp.rename(cfg.vorlagen_dir / slug)
        return slug, warnungen
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
```

Im Fehlerfall ist `cfg.vorlagen_dir` danach leer, aber vorhanden — der Test in Step 1 akzeptiert beides.

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_vorlagen_zip.py -v`
Expected: PASS. Falls der `onclick`-Fall an der Fixture scheitert (kein `<h1 ` darin): `tests/fixtures/template_assets.html` enthält `<h1 data-slot="firma">` — die Ersetzung `"<h1 "` → `'<h1 onclick="x()" '` greift also.

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/vorlagen_zip.py tests/test_vorlagen_zip.py
git commit -m "feat: ZIP-Import für Vorlagen mit Sicherheitsprüfung

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 4: Migration und mitgelieferte Beispielvorlage

**Files:**
- Modify: `src/bewerbungs_pipeline/vorlagen.py` (Funktion `migriere` anhängen)
- Create: `templates/beispiel/index.html`, `templates/beispiel/styles.css`, `templates/beispiel/assets/fonts/*`, `templates/beispiel/vorlage.yaml`
- Test: `tests/test_vorlagen_migration.py`

**Interfaces:**
- Consumes: alles aus Task 2.
- Produces: `vorlagen.migriere(cfg, conn) -> list[str]` (Meldungen für stderr).

- [ ] **Step 1: Failing tests schreiben** — `tests/test_vorlagen_migration.py`:

```python
from pathlib import Path

from vorlagen_hilfe import FIXTURES, vorlage_anlegen

from bewerbungs_pipeline import db, vorlagen
from bewerbungs_pipeline.config import Config

ALT_HTML = (
    '<html><head><link rel="stylesheet" href="styles.css"></head><body>'
    '<img src="assets/portrait.jpg"><h1 data-slot="firma">X</h1>'
    '<img src="assets/signature.png"></body></html>'
)


def make_cfg(tmp_path) -> Config:
    return Config(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        template_path=tmp_path / "unbenutzt.html",
        profile_path=tmp_path / "profile.yaml",
        llm_base_url="",
        llm_api_key="",
        llm_model="",
        vorlagen_dir=tmp_path / "data" / "vorlagen",
        eigen_dir=tmp_path / "data" / "eigen",
        templates_dir=tmp_path / "templates",
    )


def altbestand(cfg):
    t = cfg.templates_dir
    (t / "assets" / "fonts").mkdir(parents=True)
    (t / "bewerbung.html").write_text(ALT_HTML)
    (t / "styles.css").write_text("body{}")
    (t / "assets" / "fonts" / "f.woff2").write_bytes(b"f")
    (t / "assets" / "portrait.jpg").write_bytes(b"jpg")
    (t / "assets" / "signature.png").write_bytes(b"png")


def bewerbung_ohne_vorlage(conn):
    conn.execute("INSERT INTO jobs (url, dedupe_hash, title, company, location, source, scraped_at) VALUES ('u', 'h', 't', 'c', 'l', 's', 'x')")
    conn.execute("INSERT INTO applications (job_id, template_path, created_at, updated_at) VALUES (1, 'templates/bewerbung.html', 'x', 'x')")
    conn.commit()


def test_migration_uebernimmt_altbestand(tmp_path):
    cfg = make_cfg(tmp_path)
    altbestand(cfg)
    conn = db.connect(cfg.db_path)
    bewerbung_ohne_vorlage(conn)

    meldungen = vorlagen.migriere(cfg, conn)

    ziel = cfg.vorlagen_dir / "bewerbung"
    html = (ziel / "index.html").read_text()
    assert 'src="eigen/portrait.jpg"' in html
    assert 'src="eigen/signature.png"' in html
    assert (ziel / "styles.css").read_text() == "body{}"
    assert (ziel / "assets" / "fonts" / "f.woff2").exists()
    assert not (ziel / "assets" / "portrait.jpg").exists()
    assert (cfg.eigen_dir / "portrait.jpg").read_bytes() == b"jpg"
    assert (cfg.templates_dir / "assets" / "portrait.jpg").exists()  # kopiert, nicht verschoben
    assert "herkunft: migriert" in (ziel / "vorlage.yaml").read_text()
    assert vorlagen.standard(cfg, conn) == "bewerbung"
    assert conn.execute("SELECT vorlage FROM applications").fetchone()[0] == "bewerbung"
    assert meldungen


def test_migration_ist_idempotent(tmp_path):
    cfg = make_cfg(tmp_path)
    altbestand(cfg)
    conn = db.connect(cfg.db_path)
    vorlagen.migriere(cfg, conn)
    (cfg.vorlagen_dir / "bewerbung" / "index.html").write_text(ALT_HTML.replace("X", "geändert"))
    assert vorlagen.migriere(cfg, conn) == []
    assert "geändert" in (cfg.vorlagen_dir / "bewerbung" / "index.html").read_text()


def test_leerer_zustand_bekommt_beispielvorlage(tmp_path):
    cfg = make_cfg(tmp_path)
    beispiel = cfg.templates_dir / "beispiel"
    beispiel.mkdir(parents=True)
    (beispiel / "index.html").write_text((FIXTURES / "template_mini.html").read_text())
    (beispiel / "vorlage.yaml").write_text("name: Beispiel\nherkunft: mitgeliefert\n")
    conn = db.connect(cfg.db_path)

    vorlagen.migriere(cfg, conn)

    assert vorlagen.slugs(cfg) == ["beispiel"]
    assert vorlagen.standard(cfg, conn) == "beispiel"


def test_vorhandene_vorlagen_bleiben_unangetastet(tmp_path):
    cfg = make_cfg(tmp_path)
    vorlage_anlegen(cfg.vorlagen_dir, "eigene")
    conn = db.connect(cfg.db_path)
    assert vorlagen.migriere(cfg, conn) == []
    assert vorlagen.slugs(cfg) == ["eigene"]


def test_mitgelieferte_beispielvorlage_ist_gueltig(tmp_path):
    """Die echte Vorlage im Repo muss laden und darf keine persönlichen
    Daten oder Verweise auf fehlende Dateien enthalten."""
    repo_templates = Path(__file__).parent.parent / "templates"
    cfg = make_cfg(tmp_path)
    cfg = Config(**{**cfg.__dict__, "vorlagen_dir": repo_templates})
    html, slots = vorlagen.lade(cfg, "beispiel")
    assert "anschreiben_text" in slots
    assert "Ritter" not in html
    assert vorlagen.fehlende_verweise(repo_templates / "beispiel" / "index.html") == []
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_vorlagen_migration.py -v`
Expected: FAIL (`AttributeError: ... has no attribute 'migriere'`; der letzte Test scheitert, weil `templates/beispiel/` fehlt)

- [ ] **Step 3: `migriere` implementieren** — ans Ende von `vorlagen.py`:

```python
def _migriere_altvorlage(cfg: Config, conn: sqlite3.Connection) -> list[str]:
    """Übernimmt templates/bewerbung.html (Stand vor mehreren Vorlagen)."""
    alt = cfg.templates_dir / "bewerbung.html"
    ziel = cfg.vorlagen_dir / "bewerbung"
    if not alt.is_file() or ziel.exists():
        return []

    assets = cfg.templates_dir / "assets"
    cfg.vorlagen_dir.mkdir(parents=True, exist_ok=True)
    tmp = cfg.vorlagen_dir / ".tmp-migration"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    html = alt.read_text()
    for datei in EIGEN_DATEIEN:
        html = html.replace(f"assets/{datei}", f"eigen/{datei}")
    (tmp / "index.html").write_text(html)
    if (cfg.templates_dir / "styles.css").is_file():
        shutil.copy2(cfg.templates_dir / "styles.css", tmp / "styles.css")
    if assets.is_dir():
        shutil.copytree(assets, tmp / "assets", ignore=shutil.ignore_patterns(*EIGEN_DATEIEN))
    schreibe_meta(tmp, "Bewerbung", "migriert")
    tmp.rename(ziel)

    # Kopieren statt verschieben: die Originale bleiben als Rückfallebene.
    cfg.eigen_dir.mkdir(parents=True, exist_ok=True)
    for datei in EIGEN_DATEIEN:
        quelle, kopie = assets / datei, cfg.eigen_dir / datei
        if quelle.is_file() and not kopie.exists():
            shutil.copy2(quelle, kopie)

    if dbmod.einstellung(conn, "standard_vorlage") is None:
        dbmod.setze_einstellung(conn, "standard_vorlage", "bewerbung")
    return [f"Vorlage {alt} nach {ziel} übernommen (Standard)."]


def migriere(cfg: Config, conn: sqlite3.Connection) -> list[str]:
    """Einmalige, idempotente Umstellung; läuft bei jedem Start."""
    meldungen = _migriere_altvorlage(cfg, conn)

    beispiel = cfg.templates_dir / "beispiel"
    if not slugs(cfg) and (beispiel / "index.html").is_file():
        shutil.copytree(beispiel, cfg.vorlagen_dir / "beispiel", dirs_exist_ok=True)
        meldungen.append("Beispielvorlage angelegt.")

    if slugs(cfg):
        cur = conn.execute(
            "UPDATE applications SET vorlage = ? WHERE vorlage IS NULL",
            (standard(cfg, conn),),
        )
        conn.commit()
        if cur.rowcount:
            meldungen.append(f"{cur.rowcount} Bewerbung(en) der Standardvorlage zugeordnet.")
    return meldungen
```

- [ ] **Step 4: Beispielvorlage anlegen** (neutral, ohne persönliche Daten):

```bash
mkdir -p templates/beispiel/assets
cp templates/bewerbung.html templates/beispiel/index.html
cp templates/styles.css templates/beispiel/styles.css
cp -r templates/assets/fonts templates/beispiel/assets/fonts
```

Kopieren statt verschieben: `templates/styles.css` und `templates/assets/fonts/` braucht die Migration bestehender Installationen (Task 4 Step 3) weiterhin.

Dann in `templates/beispiel/index.html`:
1. Persönliche Angaben ersetzen: jede Angabe aus `profile.yaml` (Name, Adresse, Telefon, E-Mail, Geburtsdatum, Website, …) sowie jede Stelle mit „Alain“/„Ritter“ → neutrale Werte (`Max Mustermann`, `Musterstraße 1`, `12345 Musterstadt`, `0123 456789`, `max@example.org`). Kontrolle: `grep -n -i -E "ritter|alain|$(yq -r '.email' profile.yaml)" templates/beispiel/index.html` liefert nichts.
2. Inhalte der `data-slot`-Blöcke (`anschreiben_text`, `firma`, `adressat`, …) durch einen neutralen Beispieltext ersetzen (Firma „Beispiel GmbH“, Anschreiben 3 kurze Absätze über eine fiktive Stelle) — die Slots selbst bleiben unverändert.
3. `assets/portrait.jpg` → `eigen/portrait.jpg`, `assets/signature.png` → `eigen/signature.png`.
4. `<link>`s zu `fonts.googleapis.com`/`fonts.gstatic.com` bleiben (sind auch in der Altvorlage).

`templates/beispiel/vorlage.yaml`:

```yaml
name: Beispiel
erstellt: '2026-09-23'
herkunft: mitgeliefert
```

```bash
git add templates/beispiel
```

- [ ] **Step 5: Tests laufen lassen**

Run: `uv run pytest tests/test_vorlagen_migration.py -v && uv run pytest`
Expected: PASS

- [ ] **Step 6: Beispielvorlage im Browser prüfen**

Run: `chromium --headless --screenshot=/tmp/claude-1000/beispiel.png --window-size=900,1300 file://$PWD/templates/beispiel/index.html` (oder vergleichbarer Browser) und Screenshot ansehen: Layout wie die eigene Bewerbung, Portrait/Unterschrift fehlen (erwartet, `eigen/` existiert dort nicht), keine persönlichen Daten.

- [ ] **Step 7: Commit**

```bash
git add src/bewerbungs_pipeline/vorlagen.py tests/test_vorlagen_migration.py templates/beispiel
git commit -m "feat: Migration auf Vorlagen-Ordner und neutrale Beispielvorlage

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 5: Bewerbungen nutzen ihre eigene Vorlage (+ Config-Umstellung, Vorlagenwechsel)

Größter Task: `Config.template_path` verschwindet, damit müssen alle Stellen, die ihn nutzen, im selben Commit umgestellt werden — sonst ist die Suite rot.

**Files:**
- Modify: `src/bewerbungs_pipeline/config.py`, `applications.py`, `generate.py`, `web/app.py:101-107`, `web/routes/preview.py`, `web/routes/api_applications.py`, `web/routes/api_jobs.py:62-68`, `web/routes/api_profile.py`, `web/schemas.py:66-72`
- Modify tests: `tests/conftest.py`, `test_applications.py`, `test_generate.py`, `test_api_applications.py`, `test_api_jobs.py`, `test_api_tasks.py`, `test_web_preview.py`, `test_web_spa.py`, `test_web_sicherheit.py`, `test_web_schemas.py`, `test_config.py`, `test_vorlagen.py`, `test_vorlagen_zip.py`, `test_vorlagen_migration.py`

**Interfaces:**
- Consumes: `vorlagen.lade`, `vorlagen.standard`, `vorlagen.ordner`, `vorlagen.fehlende_verweise`, `vorlagen.VorlagenError`.
- Produces:
  - `Config(db_path, out_dir, profile_path, vorlagen_dir, eigen_dir, templates_dir, llm_base_url, llm_api_key, llm_model, web_token="")`
  - `applications.create(conn, job_id, cfg, client, vorlage: str | None = None) -> int`
  - `applications.get(conn, app_id, cfg) -> dict | None`, `applications.get_by_job(conn, job_id, cfg) -> dict | None` — Dict enthält `vorlage: str | None` statt `template_path`; `slots` nur die der aktiven Vorlage (bei fehlender/kaputter Vorlage alle)
  - `applications.wechsle_vorlage(conn, app_id, slug, cfg, client) -> list[str]` (neu erzeugte Slot-Namen)
  - `generate.generate_application(conn, job_id, cfg, client, vorlage: str | None = None) -> Path`
  - `schemas.ApplicationOut.vorlage: str | None`
  - Web: `/vorlagen-assets/{slug}/{pfad}` (Vorlagendateien + `eigen/…`), `/eigen/{datei}`; `preview.pfade_umschreiben(quelltext, praefix)`
  - Profil-Upload schreibt nach `cfg.eigen_dir`, liefert `{"pfad": "/eigen/<datei>"}`

- [ ] **Step 1: Test-Isolation absichern** — in `tests/conftest.py` zusätzliche autouse-Fixture:

```python
@pytest.fixture(autouse=True)
def _keine_echten_verzeichnisse(tmp_path, monkeypatch):
    """load_config() (CLI) liest Pfade aus der Umgebung — ohne diese
    Umlenkung würden Tests echte Vorlagen unter data/ und templates/
    migrieren oder verändern."""
    monkeypatch.setenv("VORLAGEN_DIR", str(tmp_path / "vorlagen"))
    monkeypatch.setenv("EIGEN_DIR", str(tmp_path / "eigen"))
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path / "templates"))
```

- [ ] **Step 2: Config final umstellen** — `config.py` komplett:

```python
@dataclass(frozen=True)
class Config:
    db_path: Path
    out_dir: Path
    profile_path: Path
    vorlagen_dir: Path
    eigen_dir: Path
    templates_dir: Path
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    web_token: str = ""


def load_config() -> Config:
    return Config(
        db_path=Path(os.getenv("DB_PATH", "data/jobs.db")),
        out_dir=Path(os.getenv("OUT_DIR", "out")),
        profile_path=Path(os.getenv("PROFILE_PATH", "profile.yaml")),
        vorlagen_dir=Path(os.getenv("VORLAGEN_DIR", "data/vorlagen")),
        eigen_dir=Path(os.getenv("EIGEN_DIR", "data/eigen")),
        templates_dir=Path(os.getenv("TEMPLATES_DIR", "templates")),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        web_token=os.getenv("JOBS_WEB_TOKEN", ""),
    )
```

Keine Defaults für die Verzeichnisse: ein vergessener Test-`Config(...)` scheitert laut statt echte Daten anzufassen.

- [ ] **Step 3: Test-Helfer ergänzen** — in `tests/vorlagen_hilfe.py`:

```python
from bewerbungs_pipeline.config import Config


def cfg_mit_vorlage(
    tmp_path: Path,
    html_datei: Path = FIXTURES / "template_mini.html",
    profil: str | None = "name: Alain Ritter\n",
    **abweichend,
) -> Config:
    """Config in tmp_path mit einer Standardvorlage „mini“."""
    profile_path = tmp_path / "profile.yaml"
    if profil is not None:
        profile_path.write_text(profil)
    werte = dict(
        db_path=tmp_path / "jobs.db",
        out_dir=tmp_path / "out",
        profile_path=profile_path,
        vorlagen_dir=tmp_path / "vorlagen",
        eigen_dir=tmp_path / "eigen",
        templates_dir=tmp_path / "templates",
        llm_base_url="http://localhost",
        llm_api_key="test",
        llm_model="test-model",
    )
    werte.update(abweichend)
    cfg = Config(**werte)
    vorlage_anlegen(cfg.vorlagen_dir, "mini", html_datei)
    return cfg
```

- [ ] **Step 4: Bestehende Tests umstellen** — in jeder Datei die lokale `make_cfg`/`Config(...)` so ändern, dass `template_path=…` entfällt und stattdessen `cfg_mit_vorlage` genutzt wird. Muster (z. B. `tests/test_applications.py:32-43`):

```python
from vorlagen_hilfe import cfg_mit_vorlage, vorlage_anlegen


def make_cfg(tmp_path) -> Config:
    return cfg_mit_vorlage(tmp_path, profil="name: Alain Ritter\nemail: cosmwave@gmail.com\n")
```

Sonderfälle:

`test_applications.py::test_create_reports_malformed_template` (Zeile 97):

```python
def test_create_reports_malformed_template(tmp_path):
    cfg = make_cfg(tmp_path)
    (cfg.vorlagen_dir / "mini" / "index.html").write_text('<p data-slot="x">kaputt')
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    with pytest.raises(applications.ApplicationError, match="Vorlage fehlerhaft"):
        applications.create(conn, job_id, cfg, FakeClient(GOOD))
```

`test_applications.py::test_export_warnt_bei_fehlendem_asset` (Zeile 218): statt `replace(cfg, template_path=vorlage)` den Inhalt nach `cfg.vorlagen_dir / "mini" / "index.html"` schreiben.

`test_generate.py::test_generate_reports_malformed_template_as_system_exit` (Zeile 90): analog, kaputtes HTML nach `cfg.vorlagen_dir / "mini" / "index.html"`.

`test_web_preview.py`: `make_cfg(tmp_path, template_path=…)` → `cfg_mit_vorlage(tmp_path, html_datei=…)`; `test_vorschau_schreibt_assetpfade_um` nutzt `cfg_mit_vorlage(tmp_path, html_datei=TEMPLATE_MIT_ASSETS)` und erwartet `"/vorlagen-assets/mini/styles.css"`. `test_pfade_umschreiben_*` rufen `preview_routen.pfade_umschreiben(html, "/vorlagen-assets/mini/")` auf und erwarten `href="/vorlagen-assets/mini/styles.css"` bzw. `src="/vorlagen-assets/mini/assets/foto.png"`.

`test_web_sicherheit.py`: `make_cfg` → `cfg_mit_vorlage(tmp_path, profil=None, llm_base_url="", llm_api_key="", llm_model="")`; Zeile 77 erwartet `(cfg.eigen_dir / "signature.png").read_bytes() == PNG`.

`test_web_schemas.py:73`: `"template_path": "t.html"` → `"vorlage": "mini"`.

`test_config.py`:

```python
def test_defaults(monkeypatch):
    for var in ("DB_PATH", "OUT_DIR", "VORLAGEN_DIR", "EIGEN_DIR", "TEMPLATES_DIR"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.db_path == Path("data/jobs.db")
    assert cfg.vorlagen_dir == Path("data/vorlagen")
    assert cfg.eigen_dir == Path("data/eigen")
    assert cfg.templates_dir == Path("templates")
```

`test_vorlagen.py`, `test_vorlagen_zip.py`, `test_vorlagen_migration.py`: in den lokalen `make_cfg` die Zeile `template_path=…` streichen.

Alle Aufrufe `applications.get(conn, x)` / `get_by_job(conn, x)` in Tests bekommen `cfg` als drittes Argument.

Kontrolle: `grep -rn "template_path" src tests` liefert nur noch `db.py` (Altspalte) und die INSERT-Zeile in `applications.py`.

- [ ] **Step 5: Neue Tests schreiben** — in `tests/test_applications.py`:

```python
ANDERE = """<!DOCTYPE html>
<html><body>
  <h1 data-slot="firma">Andere GmbH</h1>
  <p data-slot="gruss">Viele Grüße</p>
</body></html>"""


def test_create_merkt_vorlage(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    assert applications.get(conn, app_id, cfg)["vorlage"] == "mini"


def test_create_mit_expliziter_vorlage(tmp_path):
    cfg = make_cfg(tmp_path)
    datei = tmp_path / "andere.html"
    datei.write_text(ANDERE)
    vorlage_anlegen(cfg.vorlagen_dir, "andere", datei)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(
        conn, seed(cfg), cfg,
        FakeClient({"firma": "Beispiel AG", "gruss": "Viele Grüße"}),
        vorlage="andere",
    )
    bewerbung = applications.get(conn, app_id, cfg)
    assert bewerbung["vorlage"] == "andere"
    assert set(bewerbung["slots"]) == {"firma", "gruss"}


def test_render_nutzt_vorlage_der_bewerbung_nicht_den_standard(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    datei = tmp_path / "andere.html"
    datei.write_text(ANDERE)
    vorlage_anlegen(cfg.vorlagen_dir, "andere", datei)
    db.setze_einstellung(conn, "standard_vorlage", "andere")
    assert "Dieser Text ist statisch" in applications.render(conn, app_id, cfg)


def test_wechsle_vorlage_behaelt_gemeinsame_und_erzeugt_neue(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    applications.set_slot(conn, app_id, "firma", "Handarbeit AG")
    datei = tmp_path / "andere.html"
    datei.write_text(ANDERE)
    vorlage_anlegen(cfg.vorlagen_dir, "andere", datei)

    neu = applications.wechsle_vorlage(
        conn, app_id, "andere", cfg, FakeClient({"gruss": "Mit freundlichen Grüßen"})
    )

    assert neu == ["gruss"]
    bewerbung = applications.get(conn, app_id, cfg)
    assert bewerbung["vorlage"] == "andere"
    assert bewerbung["slots"]["firma"]["value"] == "Handarbeit AG"
    assert bewerbung["slots"]["firma"]["source"] == "manuell"
    assert set(bewerbung["slots"]) == {"firma", "gruss"}

    # Zurückwechseln: alte Slots sind noch da, kein LLM-Aufruf nötig.
    class KeinAufruf:
        chat = None

    assert applications.wechsle_vorlage(conn, app_id, "mini", cfg, KeinAufruf()) == []
    assert applications.get(conn, app_id, cfg)["slots"]["motivation"]["value"] == GOOD["motivation"]


def test_wechsle_vorlage_llm_fehler_aendert_nichts(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    datei = tmp_path / "andere.html"
    datei.write_text(ANDERE)
    vorlage_anlegen(cfg.vorlagen_dir, "andere", datei)

    with pytest.raises(applications.ApplicationError, match="Texterzeugung"):
        applications.wechsle_vorlage(conn, app_id, "andere", cfg, FakeClient({"falsch": "x"}))

    assert applications.get(conn, app_id, cfg)["vorlage"] == "mini"
    anzahl = conn.execute(
        "SELECT COUNT(*) FROM application_slots WHERE application_id = ?", (app_id,)
    ).fetchone()[0]
    assert anzahl == len(GOOD)


def test_wechsle_vorlage_unbekannt(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    with pytest.raises(applications.ApplicationError, match="fehlt"):
        applications.wechsle_vorlage(conn, app_id, "gibtsnicht", cfg, FakeClient({}))


def test_get_bei_geloeschter_vorlage_zeigt_alle_slots(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    import shutil
    shutil.rmtree(cfg.vorlagen_dir / "mini")
    bewerbung = applications.get(conn, app_id, cfg)
    assert set(bewerbung["slots"]) == set(GOOD)
    with pytest.raises(applications.ApplicationError, match="fehlt"):
        applications.render(conn, app_id, cfg)


def test_export_kopiert_eigene_dateien(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path)
    cfg.eigen_dir.mkdir()
    (cfg.eigen_dir / "portrait.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(applications.pdf, "erzeuge", lambda html, ziel: ziel)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    out_dir = applications.export(conn, app_id, cfg)
    assert (out_dir / "eigen" / "portrait.jpg").read_bytes() == b"jpg"
```

Hinweis: `FakeClient({"falsch": "x"})` liefert zweimal ungültige Antworten → `generate_slot_texts` wirft `GenerationError` → `ApplicationError("Texterzeugung fehlgeschlagen: …")`. Falls `validate_values` fehlende Slots nicht bemängelt, stattdessen einen Client nutzen, dessen `create` eine `GenerationError` wirft:

```python
class FehlerClient:
    def __init__(self):
        def boom(**kw):
            raise applications.GenerationError("kaputt")
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=boom))
```

In `tests/test_web_preview.py` zusätzlich:

```python
def test_vorlagen_asset_liefert_datei_und_eigen(tmp_path):
    cfg = cfg_mit_vorlage(tmp_path, html_datei=TEMPLATE_MIT_ASSETS)
    (cfg.vorlagen_dir / "mini" / "styles.css").write_text("body{}")
    cfg.eigen_dir.mkdir()
    (cfg.eigen_dir / "portrait.jpg").write_bytes(b"jpg")
    client = TestClient(create_app(cfg))
    assert client.get("/vorlagen-assets/mini/styles.css").text == "body{}"
    assert client.get("/vorlagen-assets/mini/eigen/portrait.jpg").content == b"jpg"
    assert client.get("/eigen/portrait.jpg").content == b"jpg"


@pytest.mark.parametrize(
    "pfad",
    [
        "/vorlagen-assets/mini/../../jobs.db",
        "/vorlagen-assets/mini/%2e%2e/%2e%2e/jobs.db",
        "/vorlagen-assets/mini/index.html",
        "/vorlagen-assets/mini/eigen/../../jobs.db",
        "/vorlagen-assets/..%2f/jobs.db",
        "/eigen/geheim.txt",
    ],
)
def test_vorlagen_asset_weist_ab(tmp_path, pfad):
    cfg = cfg_mit_vorlage(tmp_path)
    (tmp_path / "eigen").mkdir()
    (tmp_path / "eigen" / "geheim.txt").write_text("x")
    client = TestClient(create_app(cfg))
    assert client.get(pfad).status_code == 404
```

(`import pytest` oben ergänzen.)

- [ ] **Step 6: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest -x -q`
Expected: FAIL (u. a. `TypeError: get() missing 1 required positional argument` bzw. `AttributeError: 'Config' object has no attribute 'template_path'` im Produktionscode)

- [ ] **Step 7: `applications.py` umstellen**

Imports ergänzen: `from . import db as dbmod, llm, pdf, vorlagen` (bestehende Importe beibehalten, `vorlagen` hinzufügen).

`_template_slots` ersetzen durch:

```python
def _vorlage(cfg: Config, slug: str) -> tuple[str, dict[str, str]]:
    try:
        return vorlagen.lade(cfg, slug)
    except vorlagen.VorlagenError as exc:
        raise ApplicationError(str(exc)) from exc
```

`create`:

```python
def create(conn, job_id: int, cfg: Config, client, vorlage: str | None = None) -> int:
    row = dbmod.get_job(conn, job_id)
    if row is None:
        raise ApplicationError(f"Stelle {job_id} nicht gefunden.")
    if row["status"] != "selected":
        raise ApplicationError(
            f"Stelle {job_id} hat Status '{row['status']}' — erst auswählen."
        )

    if vorlage is None:
        try:
            vorlage = vorlagen.standard(cfg, conn)
        except vorlagen.VorlagenError as exc:
            raise ApplicationError(str(exc)) from exc
    _template, slots = _vorlage(cfg, vorlage)
    profile = _load_profile(cfg)
    row = ensure_description(conn, row)
    job = dbmod.row_to_item(row)

    try:
        values = generate_slot_texts(client, cfg.llm_model, job, slots, profile)
    except GenerationError as exc:
        raise ApplicationError(f"Texterzeugung fehlgeschlagen: {exc}") from exc

    now = _now()
    # template_path ist in Bestands-DBs NOT NULL, wird aber nicht mehr genutzt.
    conn.execute(
        """INSERT INTO applications (job_id, template_path, vorlage, created_at, updated_at)
           VALUES (?, '', ?, ?, ?)
           ON CONFLICT(job_id) DO UPDATE SET
               vorlage = excluded.vorlage,
               updated_at = excluded.updated_at""",
        (job_id, vorlage, now, now),
    )
    # … Rest (SELECT id, DELETE slots, INSERT slots, commit, return) unverändert
```

`_row_to_application`, `get`, `get_by_job`:

```python
def _row_to_application(conn, row, cfg: Config) -> dict:
    slot_rows = conn.execute(
        """SELECT slot, value, source, updated_at FROM application_slots
           WHERE application_id = ? ORDER BY slot""",
        (row["id"],),
    ).fetchall()
    # Nur die Slots der aktiven Vorlage — Werte früherer Vorlagen bleiben in
    # der DB, damit ein Zurückwechseln nichts verliert. Ist die Vorlage weg
    # oder kaputt, alle zeigen: der Nutzer soll weiterarbeiten können.
    try:
        aktiv = set(vorlagen.lade(cfg, row["vorlage"])[1]) if row["vorlage"] else None
    except vorlagen.VorlagenError:
        aktiv = None
    return {
        "id": row["id"],
        "job_id": row["job_id"],
        "vorlage": row["vorlage"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "slots": {
            r["slot"]: {
                "value": r["value"],
                "source": r["source"],
                "updated_at": r["updated_at"],
            }
            for r in slot_rows
            if aktiv is None or r["slot"] in aktiv
        },
    }


def get(conn, app_id: int, cfg: Config) -> dict | None:
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    return _row_to_application(conn, row, cfg) if row else None


def get_by_job(conn, job_id: int, cfg: Config) -> dict | None:
    row = conn.execute(
        "SELECT * FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()
    return _row_to_application(conn, row, cfg) if row else None
```

`render`:

```python
def render(conn, app_id: int, cfg: Config) -> str:
    application = get(conn, app_id, cfg)
    if application is None:
        raise ApplicationError(f"Bewerbung {app_id} nicht gefunden.")
    if not application["vorlage"]:
        raise ApplicationError("Bewerbung hat keine Vorlage — bitte eine wählen.")
    template, _ = _vorlage(cfg, application["vorlage"])
    values = {name: data["value"] for name, data in application["slots"].items()}
    try:
        return fill_slots(template, values)
    except ValueError as exc:
        raise ApplicationError(f"Vorlage fehlerhaft: {exc}") from exc
```

`_VERWEIS_RE` und die Schleife in `_pruefe_verweise` entfernen; `_pruefe_verweise` delegiert:

```python
def _pruefe_verweise(html_datei: Path) -> None:
    """Warnt vor Verweisen ins Leere, statt sie still mitzuexportieren.

    Eine fehlende Unterschrift oder ein fehlendes Foto faellt sonst erst im
    fertigen PDF auf — dann als kaputtes Bild beim Empfaenger.
    """
    for ziel in vorlagen.fehlende_verweise(html_datei):
        print(f"Warnung: Vorlage verweist auf {ziel} — Datei fehlt.", file=sys.stderr)
```

Achtung: `fehlende_verweise` behandelt `eigen/…` als vorhanden. Im Export liegt `eigen/` aber tatsächlich neben der Datei — fehlt dort z. B. das Portrait, soll weiter gewarnt werden. Deshalb in `export` nach dem Kopieren zusätzlich prüfen:

In `export` den Block ab `template_css = …` ersetzen durch:

```python
    vorlagen_ordner = vorlagen.ordner(cfg, application["vorlage"])
    if (vorlagen_ordner / "styles.css").exists():
        shutil.copy(vorlagen_ordner / "styles.css", out_dir / "styles.css")
    if (vorlagen_ordner / "assets").is_dir():
        shutil.copytree(vorlagen_ordner / "assets", out_dir / "assets", dirs_exist_ok=True)
    if cfg.eigen_dir.is_dir():
        shutil.copytree(cfg.eigen_dir, out_dir / "eigen", dirs_exist_ok=True)

    _pruefe_verweise(out_dir / "index.html")
    for datei in vorlagen.EIGEN_DATEIEN:
        if f"eigen/{datei}" in html and not (out_dir / "eigen" / datei).exists():
            print(
                f"Warnung: Vorlage verweist auf eigen/{datei} — im Profil hochladen.",
                file=sys.stderr,
            )
```

(`html` ist die bereits vorhandene Variable aus `render`.) `export` holt `application = get(conn, app_id, cfg)`.

`regenerate_slot`: `get(conn, app_id, cfg)` und `_, vorlagen_slots = _vorlage(cfg, application["vorlage"])`.

Neu am Dateiende:

```python
def wechsle_vorlage(conn, app_id: int, slug: str, cfg: Config, client) -> list[str]:
    """Stellt eine Bewerbung auf eine andere Vorlage um.

    Vorhandene Slotwerte bleiben — auch manuell bearbeitete. Nur Slots, die
    es für diese Bewerbung noch nie gab, schreibt das LLM. Das passiert vor
    jedem Schreibzugriff: scheitert es, bleibt die Bewerbung unverändert.
    """
    application = get(conn, app_id, cfg)
    if application is None:
        raise ApplicationError(f"Bewerbung {app_id} nicht gefunden.")
    _, slots = _vorlage(cfg, slug)

    vorhanden = {
        r["slot"]
        for r in conn.execute(
            "SELECT slot FROM application_slots WHERE application_id = ?", (app_id,)
        ).fetchall()
    }
    fehlend = {name: beispiel for name, beispiel in slots.items() if name not in vorhanden}
    werte: dict[str, str] = {}
    if fehlend:
        job = dbmod.row_to_item(dbmod.get_job(conn, application["job_id"]))
        profile = _load_profile(cfg)
        try:
            werte = generate_slot_texts(client, cfg.llm_model, job, fehlend, profile)
        except GenerationError as exc:
            raise ApplicationError(f"Texterzeugung fehlgeschlagen: {exc}") from exc

    now = _now()
    conn.execute(
        "UPDATE applications SET vorlage = ?, updated_at = ? WHERE id = ?",
        (slug, now, app_id),
    )
    conn.executemany(
        """INSERT INTO application_slots (application_id, slot, value, source, updated_at)
           VALUES (?, ?, ?, 'llm', ?)""",
        [(app_id, name, werte[name], now) for name in fehlend],
    )
    conn.commit()
    return sorted(fehlend)
```

- [ ] **Step 8: `generate.py`**

```python
def generate_application(
    conn, job_id: int, cfg: Config, client, vorlage: str | None = None
) -> Path:
    """Fassade fürs CLI: Bewerbung erzeugen und sofort exportieren."""
    try:
        app_id = applications.create(conn, job_id, cfg, client, vorlage)
        return applications.export(conn, app_id, cfg)
    except ApplicationError as exc:
        raise SystemExit(str(exc)) from exc
```

- [ ] **Step 9: Web anpassen**

`web/schemas.py` — `ApplicationOut`: `template_path: str` → `vorlage: str | None`.

`web/routes/api_applications.py` — alle `applications.get(conn, app_id)` → `applications.get(conn, app_id, request.app.state.cfg)`; dafür `seite`, `slot_fragment`, `slot_speichern` einen Parameter `request: Request` bekommen lassen.

`web/routes/api_jobs.py::detail`:

```python
@router.get("/jobs/{job_id}")
def detail(
    job_id: int, request: Request, conn: sqlite3.Connection = Depends(get_conn)
) -> JobOut:
    row = db.get_job(conn, job_id)
    if row is None:
        raise HTTPException(404, "Stelle nicht gefunden.")
    bewerbung = applications.get_by_job(conn, job_id, request.app.state.cfg)
    return job_out(row, application_id=bewerbung["id"] if bewerbung else None)
```

`web/routes/api_profile.py` — Kommentar und Ziel:

```python
# Dateiname ist fest (Vorlagen verweisen auf eigen/portrait.jpg bzw.
# eigen/signature.png) — ein Upload ersetzt genau diese Datei, keine
# beliebigen Namen/Formate. Geprüft wird die Signatur der Bytes, nicht der
# Content-Type: den setzt der Client.
…
    cfg = request.app.state.cfg
    ziel = cfg.eigen_dir / dateiname
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(inhalt)
    return {"pfad": f"/eigen/{dateiname}"}
```

`web/app.py` — Block `vorlagen_ordner = cfg.template_path.parent … app.mount(...)` ersatzlos löschen (und den nun ungenutzten `StaticFiles`-Import entfernen); im Docstring von `spa` `/template-assets/*` durch `/vorlagen/*, /vorlagen-assets/*, /eigen/*` ersetzen.

`web/routes/preview.py`:

```python
def pfade_umschreiben(quelltext: str, praefix: str) -> str:
    """Macht relative Vorlagen-Pfade im iframe auflösbar.

    Betrifft nur die Vorschau — die exportierte Datei in out/ bleibt
    unverändert, dort liegen styles.css, assets/ und eigen/ daneben.
    """
    return _ASSET_RE.sub(rf'\g<attr>{praefix}\g<pfad>"', quelltext)
```

`vorschau`:

```python
@router.get("/applications/{app_id}/preview", response_class=HTMLResponse)
def vorschau(
    request: Request, app_id: int, conn: sqlite3.Connection = Depends(get_conn)
):
    cfg = request.app.state.cfg
    try:
        quelltext = applications.render(conn, app_id, cfg)
    except ApplicationError as exc:
        return _fehler(exc)
    slug = applications.get(conn, app_id, cfg)["vorlage"]
    return HTMLResponse(
        skalierung_injizieren(pfade_umschreiben(quelltext, f"/vorlagen-assets/{slug}/"))
    )
```

Neue Routen am Ende von `preview.py` (Imports: `from fastapi import HTTPException`, `from fastapi.responses import FileResponse`, `from ... import vorlagen`):

```python
# HTML nie direkt ausliefern: es gehört in die Vorschau-Route, die die
# Vorlage kontrolliert rendert (CSP, Slots). Sonst liefe eine per Hand
# abgelegte Vorlage mit Skript ungeschützt im App-Origin.
_NUR_UEBER_VORSCHAU = {".html", ".htm"}


def _datei_unter(basis: Path, relativ: str) -> FileResponse:
    basis = basis.resolve()
    datei = (basis / relativ).resolve()
    if (
        not datei.is_relative_to(basis)
        or not datei.is_file()
        or datei.suffix.lower() in _NUR_UEBER_VORSCHAU
    ):
        raise HTTPException(404)
    return FileResponse(datei)


@router.get("/vorlagen-assets/{slug}/{pfad:path}")
def vorlagen_asset(slug: str, pfad: str, request: Request) -> FileResponse:
    cfg = request.app.state.cfg
    if pfad.startswith("eigen/"):
        return eigene_datei(pfad.removeprefix("eigen/"), request)
    try:
        basis = vorlagen.ordner(cfg, slug)
    except vorlagen.VorlagenError:
        raise HTTPException(404) from None
    return _datei_unter(basis, pfad)


@router.get("/eigen/{datei}")
def eigene_datei(datei: str, request: Request) -> FileResponse:
    if datei not in vorlagen.EIGEN_DATEIEN:
        raise HTTPException(404)
    return _datei_unter(request.app.state.cfg.eigen_dir, datei)
```

(`from pathlib import Path` ergänzen.)

- [ ] **Step 10: Tests laufen lassen**

Run: `uv run pytest -q`
Expected: PASS (gesamte Suite). Danach: `grep -rn "template_path\|template-assets" src tests` → nur `db.py` (Schema) und die INSERT-Zeile in `applications.py`.

- [ ] **Step 11: Commit**

```bash
git add -A src tests
git commit -m "feat: jede Bewerbung nutzt ihre eigene Vorlage, Vorlagenwechsel

Behebt nebenbei, dass alte Bewerbungen still mit der jeweils globalen
Vorlage gerendert wurden.

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 6: Vorschau-Sicherheit (CSP mit Nonce) und Vorlagen-Vorschau

**Files:**
- Modify: `src/bewerbungs_pipeline/web/routes/preview.py`
- Test: `tests/test_web_preview.py`

**Interfaces:**
- Consumes: `vorlagen.lade`, `vorlagen.VorlageFehlt`, `vorlagen.VorlagenError`, `pfade_umschreiben` (Task 5).
- Produces: `GET /vorlagen/{slug}/vorschau` (HTML), `skalierung_injizieren(quelltext, nonce: str)`; beide Vorschauen senden `Content-Security-Policy`.

- [ ] **Step 1: Failing tests** — in `tests/test_web_preview.py`:

```python
import re


def _nonce(antwort) -> str:
    csp = antwort.headers["content-security-policy"]
    treffer = re.search(r"'nonce-([^']+)'", csp)
    assert treffer, csp
    return treffer.group(1)


def test_bewerbungsvorschau_hat_csp_mit_nonce(tmp_path):
    cfg = cfg_mit_vorlage(tmp_path)
    app_id = bewerbung_anlegen(cfg, seed(cfg))
    antwort = TestClient(create_app(cfg)).get(f"/applications/{app_id}/preview")
    csp = antwort.headers["content-security-policy"]
    assert "object-src 'none'" in csp
    assert "base-uri 'none'" in csp
    # Nonce ändert sich pro Antwort und steht am injizierten Skalierungsskript.
    assert f'<script nonce="{_nonce(antwort)}">' in antwort.text


def test_vorlagen_vorschau(tmp_path):
    cfg = cfg_mit_vorlage(tmp_path, html_datei=TEMPLATE_MIT_ASSETS)
    antwort = TestClient(create_app(cfg)).get("/vorlagen/mini/vorschau")
    assert antwort.status_code == 200
    assert "AC Motoren GmbH" in antwort.text
    assert "/vorlagen-assets/mini/styles.css" in antwort.text
    assert "content-security-policy" in antwort.headers


def test_vorlagen_vorschau_unbekannt(tmp_path):
    cfg = cfg_mit_vorlage(tmp_path)
    client = TestClient(create_app(cfg))
    assert client.get("/vorlagen/gibtsnicht/vorschau").status_code == 404
    assert client.get("/vorlagen/..%2f..%2fx/vorschau").status_code == 404


def test_vorlagen_vorschau_kaputt(tmp_path):
    cfg = cfg_mit_vorlage(tmp_path)
    (cfg.vorlagen_dir / "mini" / "index.html").write_text("<p>ohne</p>")
    antwort = TestClient(create_app(cfg)).get("/vorlagen/mini/vorschau")
    assert antwort.status_code == 422
    assert "keine data-slot" in antwort.text


def test_skalierung_traegt_nonce():
    html = preview_routen.skalierung_injizieren("<html><body></body></html>", "abc")
    assert '<script nonce="abc">' in html
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `uv run pytest tests/test_web_preview.py -v`
Expected: FAIL (fehlender Header, 404 für `/vorlagen/mini/vorschau`, `skalierung_injizieren` nimmt kein zweites Argument)

- [ ] **Step 3: Implementieren** in `preview.py`:

`_SKALIERUNGS_SNIPPET`: `<script>` → `<script nonce="{nonce}">` und die geschweiften Klammern im JS/CSS verdoppeln ist fehleranfällig — stattdessen Platzhalter ersetzen:

```python
_SKALIERUNGS_SNIPPET = """
<style>
  …unverändert…
</style>
<script nonce="__NONCE__">
…unverändert…
</script>
</body>
"""


def skalierung_injizieren(quelltext: str, nonce: str) -> str:
    """…Docstring unverändert…"""
    if "</body>" not in quelltext:
        return quelltext
    return quelltext.replace(
        "</body>", _SKALIERUNGS_SNIPPET.replace("__NONCE__", nonce), 1
    )


def _vorschau_antwort(quelltext: str, slug: str) -> HTMLResponse:
    """Liefert Vorlagen-HTML mit einer CSP aus, die nur das eigene
    Skalierungsskript zulässt — Skripte aus der Vorlage bleiben blockiert,
    auch wenn jemand eine Vorlage von Hand in data/vorlagen/ legt."""
    nonce = secrets.token_urlsafe(16)
    inhalt = skalierung_injizieren(
        pfade_umschreiben(quelltext, f"/vorlagen-assets/{slug}/"), nonce
    )
    return HTMLResponse(
        inhalt,
        headers={
            "Content-Security-Policy": (
                f"script-src 'nonce-{nonce}'; object-src 'none'; base-uri 'none'"
            )
        },
    )
```

(`import secrets` ergänzen.)

`vorschau` endet mit `return _vorschau_antwort(quelltext, slug)`.

Neue Route:

```python
@router.get("/vorlagen/{slug}/vorschau", response_class=HTMLResponse)
def vorlagen_vorschau(slug: str, request: Request):
    """Vorlage mit ihren eigenen Beispieltexten — für die Vorlagen-Karten."""
    try:
        quelltext, _ = vorlagen.lade(request.app.state.cfg, slug)
    except vorlagen.VorlageFehlt as exc:
        return _fehler(exc, 404)
    except vorlagen.VorlagenError as exc:
        return _fehler(exc, 422)
    return _vorschau_antwort(quelltext, slug)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/bewerbungs_pipeline/web/routes/preview.py tests/test_web_preview.py
git commit -m "feat(web): Vorlagen-Vorschau und CSP für Vorschauen

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 7: JSON-API für Vorlagen und Vorlagenwechsel

**Files:**
- Create: `src/bewerbungs_pipeline/web/routes/api_vorlagen.py`
- Modify: `src/bewerbungs_pipeline/web/app.py` (Router registrieren), `web/schemas.py`, `web/routes/api_applications.py`
- Test: `tests/test_api_vorlagen.py`, `tests/test_api_applications.py`

**Interfaces:**
- Consumes: `vorlagen.*` (Task 2), `vorlagen_zip.importiere_zip`, `vorlagen_zip.MAX_KOMPRIMIERT` (Task 3), `applications.wechsle_vorlage`, `applications.create(..., vorlage=)` (Task 5), `tasks.start`.
- Produces (HTTP):
  - `GET /api/vorlagen` → `list[VorlageOut]`
  - `POST /api/vorlagen` (multipart `datei`, optional `name`) → `VorlageImportOut {slug, warnungen}`; 413 zu groß, 422 ungültig
  - `POST /api/vorlagen/{slug}/kopie` `{name}` → `{slug}`
  - `PATCH /api/vorlagen/{slug}` `{name?, standard?}` → `VorlageOut`
  - `DELETE /api/vorlagen/{slug}` → `{geloescht: slug}`; 409 bei Nutzung/Standard
  - `POST /api/applications` `{job_id, vorlage?}` (bestehend, erweitert)
  - `POST /api/applications/{id}/vorlage` `{vorlage}` → `TaskRef`; 404 unbekannte Bewerbung/Vorlage, 422 kaputte Vorlage
  - Schemas: `VorlageOut(slug, name, herkunft, erstellt, slots: list[str], ist_standard: bool, nutzungen: int, fehler: str | None)`, `VorlageImportOut(slug, warnungen: list[str])`, `VorlageName(name: str)`, `VorlageAenderung(name: str | None = None, standard: bool = False)`, `VorlageWahl(vorlage: str)`; `ApplicationCreate.vorlage: str | None = None`

- [ ] **Step 1: Failing tests** — `tests/test_api_vorlagen.py`:

```python
import io
import zipfile

from fastapi.testclient import TestClient
from vorlagen_hilfe import FIXTURES, cfg_mit_vorlage, vorlage_anlegen

from bewerbungs_pipeline import db
from bewerbungs_pipeline.web.app import create_app

INDEX = (FIXTURES / "template_mini.html").read_text()


def zip_bytes(eintraege: dict[str, str]) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as zf:
        for name, inhalt in eintraege.items():
            zf.writestr(name, inhalt)
    return puffer.getvalue()


def client_fuer(tmp_path):
    cfg = cfg_mit_vorlage(tmp_path)
    return cfg, TestClient(create_app(cfg))


def test_liste(tmp_path):
    _, client = client_fuer(tmp_path)
    daten = client.get("/api/vorlagen").json()
    assert daten[0]["slug"] == "mini"
    assert daten[0]["ist_standard"] is True
    assert "firma" in daten[0]["slots"]


def test_upload(tmp_path):
    cfg, client = client_fuer(tmp_path)
    antwort = client.post(
        "/api/vorlagen",
        files={"datei": ("Modern Blau.zip", zip_bytes({"index.html": INDEX}), "application/zip")},
    )
    assert antwort.status_code == 200, antwort.text
    assert antwort.json() == {"slug": "modern-blau", "warnungen": []}


def test_upload_mit_name(tmp_path):
    _, client = client_fuer(tmp_path)
    antwort = client.post(
        "/api/vorlagen",
        files={"datei": ("x.zip", zip_bytes({"index.html": INDEX}), "application/zip")},
        data={"name": "Klassisch"},
    )
    assert antwort.json()["slug"] == "klassisch"


def test_upload_ungueltig(tmp_path):
    _, client = client_fuer(tmp_path)
    antwort = client.post(
        "/api/vorlagen",
        files={"datei": ("x.zip", zip_bytes({"index.html": "<script>x</script>"}), "application/zip")},
    )
    assert antwort.status_code == 422
    assert "<script>" in antwort.json()["detail"]


def test_upload_zu_gross(tmp_path, monkeypatch):
    from bewerbungs_pipeline import vorlagen_zip

    monkeypatch.setattr(vorlagen_zip, "MAX_KOMPRIMIERT", 10)
    _, client = client_fuer(tmp_path)
    antwort = client.post(
        "/api/vorlagen",
        files={"datei": ("x.zip", zip_bytes({"index.html": INDEX}), "application/zip")},
    )
    assert antwort.status_code == 413


def test_kopie_umbenennen_standard_loeschen(tmp_path):
    _, client = client_fuer(tmp_path)
    slug = client.post("/api/vorlagen/mini/kopie", json={"name": "Zwei"}).json()["slug"]
    assert slug == "zwei"
    antwort = client.patch(f"/api/vorlagen/{slug}", json={"name": "Zweite", "standard": True})
    assert antwort.json()["name"] == "Zweite"
    assert antwort.json()["ist_standard"] is True
    assert client.delete("/api/vorlagen/zwei").status_code == 409  # Standard
    assert client.delete("/api/vorlagen/mini").json() == {"geloescht": "mini"}


def test_fehlercodes(tmp_path):
    _, client = client_fuer(tmp_path)
    assert client.patch("/api/vorlagen/gibtsnicht", json={"name": "x"}).status_code == 404
    assert client.delete("/api/vorlagen/..").status_code in (404, 405)
    assert client.post("/api/vorlagen/mini/kopie", json={"name": " "}).status_code == 422
```

In `tests/test_api_applications.py` ergänzen (Import `from vorlagen_hilfe import vorlage_anlegen`; vorhandene Helfer `seed`, `FakeClient`, `GOOD` nutzen; Task-Ergebnis wie in den bestehenden Tests dieser Datei abwarten — dort gibt es bereits ein Muster für `tasks`/Polling bzw. Monkeypatch von `client_aus_config`):

```python
def test_vorlage_wechseln_startet_task(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path)
    job_id = seed(cfg)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, job_id, cfg, FakeClient(GOOD))
    vorlage_anlegen(cfg.vorlagen_dir, "zwei")  # gleiche Slots → kein LLM nötig
    client = TestClient(create_app(cfg))

    antwort = client.post(f"/api/applications/{app_id}/vorlage", json={"vorlage": "zwei"})
    assert antwort.status_code == 200
    warte_auf_task(client, antwort.json()["task_id"])  # Helfer der Datei bzw. unten
    assert client.get(f"/api/applications/{app_id}").json()["application"]["vorlage"] == "zwei"


def test_vorlage_wechseln_unbekannt(tmp_path):
    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    client = TestClient(create_app(cfg))
    assert client.post(f"/api/applications/{app_id}/vorlage", json={"vorlage": "weg"}).status_code == 404
    assert client.post("/api/applications/999/vorlage", json={"vorlage": "mini"}).status_code == 404


def test_detail_bei_geloeschter_vorlage(tmp_path):
    import shutil

    cfg = make_cfg(tmp_path)
    conn = db.connect(cfg.db_path)
    app_id = applications.create(conn, seed(cfg), cfg, FakeClient(GOOD))
    shutil.rmtree(cfg.vorlagen_dir / "mini")
    client = TestClient(create_app(cfg))
    assert client.get(f"/api/applications/{app_id}").status_code == 200
    vorschau = client.get(f"/applications/{app_id}/preview")
    assert vorschau.status_code == 400
    assert "fehlt" in vorschau.text
```

Falls `test_api_applications.py` noch keinen Warte-Helfer hat:

```python
def warte_auf_task(client, task_id: str) -> dict:
    import time

    for _ in range(100):
        task = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] != "läuft":
            assert task["status"] == "fertig", task
            return task
        time.sleep(0.05)
    raise AssertionError("Task hängt")
```

Hinweis: Der Wechsel-Task ruft `client_aus_config(cfg)` auf; mit `llm_base_url="http://localhost"` klappt die Client-Erzeugung ohne Netz (Aufruf passiert nicht, da keine Slots fehlen).

- [ ] **Step 2: Fehlschlag prüfen**

Run: `uv run pytest tests/test_api_vorlagen.py tests/test_api_applications.py -v`
Expected: FAIL (404 für `/api/vorlagen`)

- [ ] **Step 3: Schemas** — in `web/schemas.py`:

```python
class ApplicationCreate(BaseModel):
    job_id: int
    vorlage: str | None = None


class VorlageOut(BaseModel):
    slug: str
    name: str
    herkunft: str
    erstellt: str
    slots: list[str]
    ist_standard: bool
    nutzungen: int
    fehler: str | None = None


class VorlageImportOut(BaseModel):
    slug: str
    warnungen: list[str]


class VorlageName(BaseModel):
    name: str


class VorlageAenderung(BaseModel):
    name: str | None = None
    standard: bool = False


class VorlageWahl(BaseModel):
    vorlage: str
```

- [ ] **Step 4: Router** — `web/routes/api_vorlagen.py`:

```python
import sqlite3
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile

from ... import vorlagen, vorlagen_zip
from ..app import get_conn
from ..schemas import VorlageAenderung, VorlageImportOut, VorlageName, VorlageOut

router = APIRouter(prefix="/api/vorlagen")


def _http(exc: vorlagen.VorlagenError) -> HTTPException:
    if isinstance(exc, vorlagen.VorlageFehlt):
        return HTTPException(404, str(exc))
    if isinstance(exc, vorlagen.VorlageInBenutzung):
        return HTTPException(409, str(exc))
    return HTTPException(422, str(exc))


def _eintrag(cfg, conn, slug: str) -> VorlageOut:
    for eintrag in vorlagen.liste(cfg, conn):
        if eintrag["slug"] == slug:
            return VorlageOut.model_validate(eintrag)
    raise HTTPException(404, f"Unbekannte Vorlage: {slug}")


@router.get("")
def liste(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> list[VorlageOut]:
    return [VorlageOut.model_validate(e) for e in vorlagen.liste(request.app.state.cfg, conn)]


@router.post("")
async def hochladen(
    request: Request, datei: UploadFile, name: str | None = Form(None)
) -> VorlageImportOut:
    inhalt = await datei.read(vorlagen_zip.MAX_KOMPRIMIERT + 1)
    if len(inhalt) > vorlagen_zip.MAX_KOMPRIMIERT:
        raise HTTPException(413, "ZIP zu groß (max. 10 MB).")
    anzeigename = (name or "").strip() or Path(datei.filename or "Vorlage").stem
    with tempfile.TemporaryDirectory() as tmp:
        pfad = Path(tmp) / "upload.zip"
        pfad.write_bytes(inhalt)
        try:
            slug, warnungen = vorlagen_zip.importiere_zip(
                request.app.state.cfg, pfad, anzeigename
            )
        except vorlagen.VorlagenError as exc:
            raise _http(exc) from exc
    return VorlageImportOut(slug=slug, warnungen=warnungen)


@router.post("/{slug}/kopie")
def kopie(slug: str, body: VorlageName, request: Request) -> dict:
    try:
        return {"slug": vorlagen.dupliziere(request.app.state.cfg, slug, body.name)}
    except vorlagen.VorlagenError as exc:
        raise _http(exc) from exc


@router.patch("/{slug}")
def aendern(
    slug: str,
    body: VorlageAenderung,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
) -> VorlageOut:
    cfg = request.app.state.cfg
    try:
        if body.name is not None:
            vorlagen.umbenennen(cfg, slug, body.name)
        if body.standard:
            vorlagen.setze_standard(cfg, conn, slug)
    except vorlagen.VorlagenError as exc:
        raise _http(exc) from exc
    return _eintrag(cfg, conn, slug)


@router.delete("/{slug}")
def loeschen(
    slug: str, request: Request, conn: sqlite3.Connection = Depends(get_conn)
) -> dict:
    try:
        vorlagen.loesche(request.app.state.cfg, conn, slug)
    except vorlagen.VorlagenError as exc:
        raise _http(exc) from exc
    return {"geloescht": slug}
```

In `web/app.py` bei den Router-Importen `from .routes import api_vorlagen as api_vorlagen_routen` und `app.include_router(api_vorlagen_routen.router)` ergänzen.

- [ ] **Step 5: Wechsel-Endpunkt** — in `web/routes/api_applications.py`:

```python
from ... import applications, db, tasks, vorlagen
from ..schemas import (…, VorlageWahl)


def bewerbung_erzeugen(cfg: Config, job_id: int, vorlage: str | None) -> int:
    """Hintergrund-Thread: eigene Verbindung, eigener Client."""
    conn = db.connect(cfg.db_path)
    try:
        return applications.create(conn, job_id, cfg, client_aus_config(cfg), vorlage)
    finally:
        conn.close()


def vorlage_wechseln_lauf(cfg: Config, app_id: int, slug: str) -> list[str]:
    """Hintergrund-Thread: fehlende Slots schreibt das LLM."""
    conn = db.connect(cfg.db_path)
    try:
        return applications.wechsle_vorlage(conn, app_id, slug, cfg, client_aus_config(cfg))
    finally:
        conn.close()


@router.post("/applications")
def erzeugen(body: ApplicationCreate, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    task_id = tasks.start(
        "Bewerbung wird geschrieben", bewerbung_erzeugen, cfg, body.job_id, body.vorlage
    )
    return TaskRef(task_id=task_id)


@router.post("/applications/{app_id}/vorlage")
def vorlage_wechseln(
    app_id: int,
    body: VorlageWahl,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
) -> TaskRef:
    cfg = request.app.state.cfg
    if applications.get(conn, app_id, cfg) is None:
        raise HTTPException(404, "Bewerbung nicht gefunden.")
    # Vorab prüfen: ein Tippfehler soll sofort auffallen, nicht erst im Task.
    try:
        vorlagen.lade(cfg, body.vorlage)
    except vorlagen.VorlageFehlt as exc:
        raise HTTPException(404, str(exc)) from exc
    except vorlagen.VorlagenError as exc:
        raise HTTPException(422, str(exc)) from exc
    task_id = tasks.start(
        "Vorlage wird gewechselt", vorlage_wechseln_lauf, cfg, app_id, body.vorlage
    )
    return TaskRef(task_id=task_id)
```

Bestehende Tests, die `bewerbung_erzeugen(cfg, job_id)` direkt aufrufen, bekommen `None` als drittes Argument (`grep -n bewerbung_erzeugen tests`).

- [ ] **Step 6: Tests laufen lassen**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/bewerbungs_pipeline/web tests/test_api_vorlagen.py tests/test_api_applications.py
git commit -m "feat(web): API für Vorlagenverwaltung und Vorlagenwechsel

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 8: CLI-Befehle und Migration beim Start

**Files:**
- Modify: `src/bewerbungs_pipeline/cli.py`, `src/bewerbungs_pipeline/web/app.py`
- Test: `tests/test_cli.py`, `tests/test_web_spa.py` (oder neue Datei `tests/test_web_start.py`)

**Interfaces:**
- Consumes: `vorlagen.*`, `vorlagen_zip.importiere_zip`, `vorlagen.migriere`, `applications.wechsle_vorlage`, `generate.generate_application(..., vorlage=)`.
- Produces: CLI `jobs vorlagen list [--json] | standard SLUG | import DATEI [--name NAME] | kopie SLUG NAME | umbenennen SLUG NAME | loeschen SLUG`, `jobs generate ID [--vorlage SLUG]`, `jobs vorlage-wechseln APP_ID SLUG`. `create_app` und `cli.main` rufen `vorlagen.migriere` auf.

- [ ] **Step 1: Failing tests** — ans Ende von `tests/test_cli.py` (die autouse-Fixture aus Task 5 lenkt `VORLAGEN_DIR`/`EIGEN_DIR`/`TEMPLATES_DIR` auf `tmp_path` um):

```python
import zipfile

from vorlagen_hilfe import FIXTURES, vorlage_anlegen


def test_vorlagen_list_leer_legt_beispiel_an(env, tmp_path, capsys):
    beispiel = tmp_path / "templates" / "beispiel"
    beispiel.mkdir(parents=True)
    (beispiel / "index.html").write_text((FIXTURES / "template_mini.html").read_text())
    assert cli.main(["vorlagen", "list", "--json"]) == 0
    daten = json.loads(capsys.readouterr().out)
    assert [d["slug"] for d in daten] == ["beispiel"]


def test_vorlagen_import_standard_loeschen(env, tmp_path, capsys):
    vorlage_anlegen(tmp_path / "vorlagen", "mini")
    zip_pfad = tmp_path / "Neu.zip"
    with zipfile.ZipFile(zip_pfad, "w") as zf:
        zf.writestr("index.html", (FIXTURES / "template_mini.html").read_text())

    assert cli.main(["vorlagen", "import", str(zip_pfad)]) == 0
    assert "neu" in capsys.readouterr().out
    assert cli.main(["vorlagen", "standard", "neu"]) == 0
    assert cli.main(["vorlagen", "loeschen", "neu"]) == 1  # ist Standard
    assert "Standard" in capsys.readouterr().err
    assert cli.main(["vorlagen", "kopie", "neu", "Dritte"]) == 0
    assert cli.main(["vorlagen", "umbenennen", "dritte", "Die Dritte"]) == 0
    assert cli.main(["vorlagen", "loeschen", "dritte"]) == 0


def test_vorlagen_import_fehler(env, tmp_path, capsys):
    kaputt = tmp_path / "k.zip"
    kaputt.write_text("x")
    assert cli.main(["vorlagen", "import", str(kaputt)]) == 1
    assert "Keine gültige ZIP" in capsys.readouterr().err


def test_migration_beim_cli_start(env, tmp_path, capsys):
    t = tmp_path / "templates"
    t.mkdir()
    (t / "bewerbung.html").write_text('<h1 data-slot="firma">X</h1>')
    cli.main(["list"])
    assert (tmp_path / "vorlagen" / "bewerbung" / "index.html").exists()
    assert "übernommen" in capsys.readouterr().err
```

In `tests/test_web_spa.py` (dessen `make_cfg` in Task 5 auf `cfg_mit_vorlage` umgestellt wurde):

```python
def test_create_app_migriert(tmp_path):
    cfg = cfg_mit_vorlage(tmp_path)
    (cfg.templates_dir).mkdir()
    (cfg.templates_dir / "bewerbung.html").write_text('<h1 data-slot="firma">X</h1>')
    create_app(cfg)
    assert (cfg.vorlagen_dir / "bewerbung" / "index.html").exists()
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `uv run pytest tests/test_cli.py tests/test_web_spa.py -v`
Expected: FAIL (`argparse` kennt `vorlagen` nicht; Migration läuft nicht)

- [ ] **Step 3: Migration in `create_app`** — in `web/app.py` direkt nach `app.state.cfg = cfg`:

```python
    # Einmalige Umstellung auf Vorlagen-Ordner (idempotent, siehe vorlagen.py).
    conn = db.connect(cfg.db_path)
    try:
        for meldung in vorlagen.migriere(cfg, conn):
            print(meldung)
    finally:
        conn.close()
```

(`from .. import db, vorlagen`.)

- [ ] **Step 4: CLI** — in `cli.py`:

```python
def _migrieren() -> None:
    from . import vorlagen

    cfg = load_config()
    conn = db.connect(cfg.db_path)
    try:
        for meldung in vorlagen.migriere(cfg, conn):
            print(meldung, file=sys.stderr)
    finally:
        conn.close()


def _cmd_vorlagen(args: argparse.Namespace) -> int:
    from . import vorlagen, vorlagen_zip

    cfg = load_config()
    conn = db.connect(cfg.db_path)
    try:
        if args.aktion == "list":
            eintraege = vorlagen.liste(cfg, conn)
            if args.json:
                _json_out(eintraege)
            else:
                for e in eintraege:
                    marke = "*" if e["ist_standard"] else " "
                    zusatz = f"  FEHLER: {e['fehler']}" if e["fehler"] else ""
                    print(f"{marke} {e['slug']:<24} {e['name']}  ({e['nutzungen']} Bewerbungen){zusatz}")
        elif args.aktion == "standard":
            vorlagen.setze_standard(cfg, conn, args.slug)
            print(f"Standard: {args.slug}")
        elif args.aktion == "import":
            datei = Path(args.datei)
            slug, warnungen = vorlagen_zip.importiere_zip(cfg, datei, args.name or datei.stem)
            for w in warnungen:
                print(f"Warnung: {w}", file=sys.stderr)
            print(f"Importiert: {slug}")
        elif args.aktion == "kopie":
            print(f"Kopie: {vorlagen.dupliziere(cfg, args.slug, args.name)}")
        elif args.aktion == "umbenennen":
            vorlagen.umbenennen(cfg, args.slug, args.name)
            print(f"Umbenannt: {args.slug} → {args.name}")
        elif args.aktion == "loeschen":
            vorlagen.loesche(cfg, conn, args.slug)
            print(f"Gelöscht: {args.slug}")
    except vorlagen.VorlagenError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


def _cmd_vorlage_wechseln(args: argparse.Namespace) -> int:
    from . import applications
    from .llm import GenerationError, client_aus_config

    cfg = load_config()
    try:
        client = client_aus_config(cfg)
    except GenerationError as exc:
        print(exc, file=sys.stderr)
        return 1
    conn = db.connect(cfg.db_path)
    try:
        neu = applications.wechsle_vorlage(conn, args.app_id, args.slug, cfg, client)
    except applications.ApplicationError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"Vorlage: {args.slug}" + (f" — neu geschrieben: {', '.join(neu)}" if neu else ""))
    return 0
```

(`from pathlib import Path` ergänzen, falls nicht vorhanden.)

`_cmd_generate`: `generate_application(conn, args.id, cfg, client, args.vorlage)`.

In `main()` vor `args = parser.parse_args(argv)`:

```python
    p_gen.add_argument("--vorlage", help="Slug der Vorlage (Standard: Standardvorlage)")

    p_vorl = sub.add_parser("vorlagen", help="Bewerbungsvorlagen verwalten")
    vorl_sub = p_vorl.add_subparsers(dest="aktion", required=True)
    p_vl = vorl_sub.add_parser("list", help="Vorlagen anzeigen (* = Standard)")
    _json_flag(p_vl)
    vorl_sub.add_parser("standard", help="Standardvorlage setzen").add_argument("slug")
    p_vi = vorl_sub.add_parser("import", help="HTML-Vorlage als ZIP importieren")
    p_vi.add_argument("datei")
    p_vi.add_argument("--name")
    p_vk = vorl_sub.add_parser("kopie", help="Vorlage duplizieren")
    p_vk.add_argument("slug")
    p_vk.add_argument("name")
    p_vu = vorl_sub.add_parser("umbenennen", help="Anzeigenamen ändern")
    p_vu.add_argument("slug")
    p_vu.add_argument("name")
    vorl_sub.add_parser("loeschen", help="Vorlage löschen").add_argument("slug")
    p_vorl.set_defaults(func=_cmd_vorlagen, json=False)

    p_vw = sub.add_parser("vorlage-wechseln", help="Vorlage einer Bewerbung wechseln")
    p_vw.add_argument("app_id", type=int)
    p_vw.add_argument("slug")
    p_vw.set_defaults(func=_cmd_vorlage_wechseln)
```

`p_gen.add_argument("--vorlage", …)` gehört direkt hinter die bestehende `p_gen.add_argument("id", …)`-Zeile.

Und in `main()`:

```python
    args = parser.parse_args(argv)
    _migrieren()
    return args.func(args)
```

Hinweis zu `p_vorl.set_defaults(json=False)`: nur `list` definiert `--json`; der Default verhindert `AttributeError` bei den anderen Aktionen. Subparser-Defaults überschreiben Parent-Defaults, `list --json` setzt also `True`.

- [ ] **Step 5: Tests laufen lassen**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 6: Manuell prüfen (echte Installation, Altbestand)**

```bash
cp -r data /tmp/claude-1000/data-backup-$(date +%s)   # Sicherung vor der echten Migration
uv run jobs vorlagen list
```

Expected: stderr „Vorlage templates/bewerbung.html nach data/vorlagen/bewerbung übernommen (Standard).“ und „N Bewerbung(en) der Standardvorlage zugeordnet.“; Ausgabe `* bewerbung  Bewerbung (N Bewerbungen)`. `ls data/eigen` zeigt `portrait.jpg signature.png`.

- [ ] **Step 7: Commit**

```bash
git add src/bewerbungs_pipeline/cli.py src/bewerbungs_pipeline/web/app.py tests/test_cli.py tests/test_web_spa.py
git commit -m "feat(cli): Vorlagen-Befehle, --vorlage, Migration beim Start

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 9: Frontend — Vorlagen-Seite, Dropdown, Profil-Pfade

**Files:**
- Modify: `frontend/src/types/api.ts`, `frontend/src/lib/api.ts`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/features/bewerbung/BewerbungPage.tsx`, `frontend/src/features/profil/ProfilPage.tsx`, `frontend/vite.config.ts`
- Create: `frontend/src/features/vorlagen/VorlagenPage.tsx`, `VorlageKarte.tsx`, `NameDialog.tsx`, `loeschSperre.ts`, `loeschSperre.test.ts`
- Build: `frontend/dist/`

**Interfaces:**
- Consumes: HTTP-API aus Task 6/7.
- Produces: Route `/vorlagen`; `api.vorlagen.{liste, hochladen, kopieren, aendern, loeschen}`, `api.applications.vorlageWechseln(appId, vorlage)`; `loeschSperre(v: VorlageOut): string | null`.

- [ ] **Step 1: Failing Vitest** — `frontend/src/features/vorlagen/loeschSperre.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { loeschSperre } from "@/features/vorlagen/loeschSperre";
import type { VorlageOut } from "@/types/api";

function vorlage(teil: Partial<VorlageOut>): VorlageOut {
  return {
    slug: "a",
    name: "A",
    herkunft: "zip",
    erstellt: "2026-09-23",
    slots: ["firma"],
    ist_standard: false,
    nutzungen: 0,
    fehler: null,
    ...teil,
  };
}

describe("loeschSperre", () => {
  it("erlaubt Löschen einer ungenutzten Vorlage", () => {
    expect(loeschSperre(vorlage({}))).toBeNull();
  });

  it("sperrt die Standardvorlage", () => {
    expect(loeschSperre(vorlage({ ist_standard: true }))).toMatch(/Standard/);
  });

  it("sperrt genutzte Vorlagen und nennt die Anzahl", () => {
    expect(loeschSperre(vorlage({ nutzungen: 1 }))).toBe("Wird von 1 Bewerbung genutzt.");
    expect(loeschSperre(vorlage({ nutzungen: 3 }))).toBe("Wird von 3 Bewerbungen genutzt.");
  });
});
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `cd frontend && npm test -- --run src/features/vorlagen`
Expected: FAIL (Modul nicht gefunden)

- [ ] **Step 3: Typen & API**

`types/api.ts` — in `ApplicationOut` `template_path: string;` → `vorlage: string | null;` und neu:

```ts
export interface VorlageOut {
  slug: string;
  name: string;
  herkunft: string;
  erstellt: string;
  slots: string[];
  ist_standard: boolean;
  nutzungen: number;
  fehler: string | null;
}

export interface VorlageImportOut {
  slug: string;
  warnungen: string[];
}
```

`lib/api.ts` — `hochladen` um Zusatzfelder erweitern:

```ts
async function hochladen<T>(
  pfad: string,
  datei: File,
  felder: Record<string, string> = {},
): Promise<T> {
  const formular = new FormData();
  formular.append("datei", datei);
  for (const [name, wert] of Object.entries(felder)) formular.append(name, wert);
  const antwort = await fetch(pfad, { method: "POST", body: formular });
  await wirfBeiFehler(antwort);
  return antwort.json() as Promise<T>;
}
```

und im `api`-Objekt (Typimporte `VorlageImportOut`, `VorlageOut` ergänzen):

```ts
  vorlagen: {
    liste: () => anfrage<VorlageOut[]>(`/api/vorlagen`),
    hochladen: (datei: File, name?: string) =>
      hochladen<VorlageImportOut>(`/api/vorlagen`, datei, name ? { name } : {}),
    kopieren: (slug: string, name: string) =>
      anfrage<{ slug: string }>(`/api/vorlagen/${slug}/kopie`, {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    aendern: (slug: string, aenderung: { name?: string; standard?: boolean }) =>
      anfrage<VorlageOut>(`/api/vorlagen/${slug}`, {
        method: "PATCH",
        body: JSON.stringify(aenderung),
      }),
    loeschen: (slug: string) =>
      anfrage<{ geloescht: string }>(`/api/vorlagen/${slug}`, { method: "DELETE" }),
  },
```

in `applications`:

```ts
    vorlageWechseln: (appId: number, vorlage: string) =>
      anfrage<TaskRef>(`/api/applications/${appId}/vorlage`, {
        method: "POST",
        body: JSON.stringify({ vorlage }),
      }),
```

- [ ] **Step 4: `loeschSperre.ts`**

```ts
import type { VorlageOut } from "@/types/api";

/** Grund, warum eine Vorlage nicht gelöscht werden kann — oder null.
 * Spiegelt die Prüfung in vorlagen.loesche, damit der Button schon vorher
 * deaktiviert ist und der Tooltip den Grund nennt. */
export function loeschSperre(vorlage: VorlageOut): string | null {
  if (vorlage.ist_standard) return "Standardvorlage — erst eine andere als Standard setzen.";
  if (vorlage.nutzungen > 0) {
    const wort = vorlage.nutzungen === 1 ? "Bewerbung" : "Bewerbungen";
    return `Wird von ${vorlage.nutzungen} ${wort} genutzt.`;
  }
  return null;
}
```

Run: `cd frontend && npm test -- --run src/features/vorlagen` → PASS.

- [ ] **Step 5: `NameDialog.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

interface NameDialogProps {
  offen: boolean;
  titel: string;
  vorgabe: string;
  bestaetigen: string;
  onSchliessen: () => void;
  onBestaetigen: (name: string) => void;
}

export function NameDialog({
  offen,
  titel,
  vorgabe,
  bestaetigen,
  onSchliessen,
  onBestaetigen,
}: NameDialogProps) {
  const [name, setName] = useState(vorgabe);
  useEffect(() => setName(vorgabe), [vorgabe, offen]);

  return (
    <Dialog open={offen} onOpenChange={(o) => !o && onSchliessen()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{titel}</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) onBestaetigen(name.trim());
          }}
          className="flex flex-col gap-4"
        >
          <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onSchliessen}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={!name.trim()}>
              {bestaetigen}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 6: `VorlageKarte.tsx`**

```tsx
import { MoreHorizontal } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { loeschSperre } from "@/features/vorlagen/loeschSperre";
import type { VorlageOut } from "@/types/api";

// A4-Breite in CSS-Pixeln; das iframe rendert in voller Breite und wird per
// transform verkleinert — so sieht jede Vorlage aus wie im Export.
const A4_BREITE = 794;
const KARTEN_BREITE = 240;
const FAKTOR = KARTEN_BREITE / A4_BREITE;

interface VorlageKarteProps {
  vorlage: VorlageOut;
  onStandard: () => void;
  onUmbenennen: () => void;
  onDuplizieren: () => void;
  onLoeschen: () => void;
}

export function VorlageKarte({
  vorlage,
  onStandard,
  onUmbenennen,
  onDuplizieren,
  onLoeschen,
}: VorlageKarteProps) {
  const sperre = loeschSperre(vorlage);

  return (
    <Card className="gap-3 p-3">
      <div
        className="overflow-hidden rounded-md border border-border bg-white"
        style={{ width: KARTEN_BREITE, height: KARTEN_BREITE * 1.414 }}
      >
        {vorlage.fehler ? (
          <p className="p-3 text-sm text-destructive">{vorlage.fehler}</p>
        ) : (
          <iframe
            title={`Vorschau ${vorlage.name}`}
            src={`/vorlagen/${vorlage.slug}/vorschau`}
            loading="lazy"
            tabIndex={-1}
            className="pointer-events-none origin-top-left"
            style={{
              width: A4_BREITE,
              height: A4_BREITE * 1.414,
              transform: `scale(${FAKTOR})`,
            }}
          />
        )}
      </div>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold">{vorlage.name}</p>
          <p className="text-xs text-muted-foreground">
            {vorlage.nutzungen} {vorlage.nutzungen === 1 ? "Bewerbung" : "Bewerbungen"}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {vorlage.ist_standard && <Badge variant="secondary">Standard</Badge>}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label={`Aktionen für ${vorlage.name}`}>
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                disabled={vorlage.ist_standard || vorlage.fehler !== null}
                onSelect={onStandard}
              >
                Als Standard setzen
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={onUmbenennen}>Umbenennen</DropdownMenuItem>
              <DropdownMenuItem onSelect={onDuplizieren}>Duplizieren</DropdownMenuItem>
              {sperre ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span>
                      <DropdownMenuItem disabled>Löschen</DropdownMenuItem>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>{sperre}</TooltipContent>
                </Tooltip>
              ) : (
                <DropdownMenuItem variant="destructive" onSelect={onLoeschen}>
                  Löschen
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </Card>
  );
}
```

Falls `DropdownMenuItem` in `components/ui/dropdown-menu.tsx` kein `variant`-Prop hat: `className="text-destructive"` statt `variant="destructive"`.

- [ ] **Step 7: `VorlagenPage.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { NameDialog } from "@/features/vorlagen/NameDialog";
import { VorlageKarte } from "@/features/vorlagen/VorlageKarte";
import { api } from "@/lib/api";
import { useSetHeaderActions } from "@/lib/header-actions";
import type { VorlageOut } from "@/types/api";

type Dialogzustand =
  | { art: "umbenennen" | "duplizieren"; vorlage: VorlageOut }
  | { art: "hochladen"; datei: File }
  | null;

export function VorlagenPage() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dialog, setDialog] = useState<Dialogzustand>(null);

  const listeQuery = useQuery({ queryKey: ["vorlagen"], queryFn: api.vorlagen.liste });
  const neuLaden = () => queryClient.invalidateQueries({ queryKey: ["vorlagen"] });
  const fehler = (aktion: string) => (error: Error) =>
    toast.error(`${aktion} fehlgeschlagen: ${error.message}`);

  const hochladen = useMutation({
    mutationFn: ({ datei, name }: { datei: File; name: string }) =>
      api.vorlagen.hochladen(datei, name),
    onSuccess: (ergebnis) => {
      toast.success(`Vorlage „${ergebnis.slug}“ importiert.`);
      for (const w of ergebnis.warnungen) toast.warning(w);
      neuLaden();
    },
    onError: fehler("Upload"),
  });
  const aendern = useMutation({
    mutationFn: ({ slug, ...aenderung }: { slug: string; name?: string; standard?: boolean }) =>
      api.vorlagen.aendern(slug, aenderung),
    onSuccess: neuLaden,
    onError: fehler("Ändern"),
  });
  const kopieren = useMutation({
    mutationFn: ({ slug, name }: { slug: string; name: string }) =>
      api.vorlagen.kopieren(slug, name),
    onSuccess: neuLaden,
    onError: fehler("Duplizieren"),
  });
  const loeschen = useMutation({
    mutationFn: api.vorlagen.loeschen,
    onSuccess: neuLaden,
    onError: fehler("Löschen"),
  });

  const headerActions = useSetHeaderActions(
    <>
      <Button disabled={hochladen.isPending} onClick={() => inputRef.current?.click()}>
        <Upload />
        {hochladen.isPending ? "lädt hoch…" : "ZIP hochladen"}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept=".zip,application/zip"
        className="hidden"
        onChange={(event) => {
          const datei = event.target.files?.[0];
          if (datei) setDialog({ art: "hochladen", datei });
          event.target.value = "";
        }}
      />
    </>,
  );

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
      {headerActions}
      <div>
        <h2 className="text-lg font-semibold">Vorlagen</h2>
        <p className="text-sm text-muted-foreground">
          Eine ZIP enthält <code>index.html</code> mit <code>data-slot</code>-Blöcken, optional{" "}
          <code>styles.css</code> und <code>assets/</code>. Foto und Unterschrift über{" "}
          <code>eigen/portrait.jpg</code> bzw. <code>eigen/signature.png</code> einbinden.
        </p>
      </div>
      {listeQuery.isLoading ? (
        <Skeleton className="h-80 w-64" />
      ) : (
        <div className="flex flex-wrap gap-4">
          {listeQuery.data?.map((vorlage) => (
            <VorlageKarte
              key={vorlage.slug}
              vorlage={vorlage}
              onStandard={() => aendern.mutate({ slug: vorlage.slug, standard: true })}
              onUmbenennen={() => setDialog({ art: "umbenennen", vorlage })}
              onDuplizieren={() => setDialog({ art: "duplizieren", vorlage })}
              onLoeschen={() => {
                if (window.confirm(`Vorlage „${vorlage.name}“ löschen?`))
                  loeschen.mutate(vorlage.slug);
              }}
            />
          ))}
        </div>
      )}
      <NameDialog
        offen={dialog !== null}
        titel={
          dialog?.art === "umbenennen"
            ? "Vorlage umbenennen"
            : dialog?.art === "duplizieren"
              ? "Vorlage duplizieren"
              : "Vorlage hochladen"
        }
        vorgabe={
          dialog?.art === "hochladen"
            ? dialog.datei.name.replace(/\.zip$/i, "")
            : dialog?.art === "duplizieren"
              ? `${dialog.vorlage.name} (Kopie)`
              : (dialog?.vorlage.name ?? "")
        }
        bestaetigen={dialog?.art === "hochladen" ? "Hochladen" : "Speichern"}
        onSchliessen={() => setDialog(null)}
        onBestaetigen={(name) => {
          if (dialog?.art === "umbenennen") aendern.mutate({ slug: dialog.vorlage.slug, name });
          if (dialog?.art === "duplizieren") kopieren.mutate({ slug: dialog.vorlage.slug, name });
          if (dialog?.art === "hochladen") hochladen.mutate({ datei: dialog.datei, name });
          setDialog(null);
        }}
      />
    </div>
  );
}
```

Falls `toast.warning` in der eingesetzten `sonner`-Version fehlt: `toast(w)`.

- [ ] **Step 8: Route und Navigation**

`main.tsx`: `import { VorlagenPage } from "@/features/vorlagen/VorlagenPage";` und `<Route path="vorlagen" element={<VorlagenPage />} />` neben `profil`.

`App.tsx`: `import { LayoutTemplate, UserRound } from "lucide-react";` und vor dem Profil-Button:

```tsx
          <Button variant="outline" size="icon" asChild>
            <Link to="/vorlagen" aria-label="Vorlagen" title="Vorlagen">
              <LayoutTemplate />
            </Link>
          </Button>
```

- [ ] **Step 9: Dropdown in `BewerbungPage.tsx`**

Imports ergänzen: `useQueryClient` aus `@tanstack/react-query`; `Select, SelectContent, SelectItem, SelectTrigger, SelectValue` aus `@/components/ui/select`.

Nach `exportTask`:

```tsx
  const queryClient = useQueryClient();
  const vorlagenQuery = useQuery({ queryKey: ["vorlagen"], queryFn: api.vorlagen.liste });
  const [wechselTaskId, setWechselTaskId] = useState<string | null>(null);

  const wechselMutation = useMutation({
    mutationFn: async (vorlage: string) => {
      await alleGespeichert();
      return api.applications.vorlageWechseln(id, vorlage);
    },
    onSuccess: (ref) => setWechselTaskId(ref.task_id),
    onError: (error) => toast.error(`Vorlagenwechsel fehlgeschlagen: ${error.message}`),
  });

  const wechselTask = useTaskErgebnis(wechselTaskId, {
    onFertig: () => {
      toast.success("Vorlage gewechselt.");
      setWechselTaskId(null);
      queryClient.invalidateQueries({ queryKey: ["applications", id] });
      queryClient.invalidateQueries({ queryKey: ["vorlagen"] });
      setPreviewKey((k) => k + 1);
    },
    onFehler: (task) => {
      toast.error(`Vorlagenwechsel fehlgeschlagen: ${task.meldung}`);
      setWechselTaskId(null);
    },
  });

  const wechselLaeuft = wechselMutation.isPending || wechselTask?.status === "läuft";
```

Die Überschrift `<h2 …>{stelle.title} — {stelle.company}</h2>` ersetzen durch:

```tsx
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">
          {stelle.title} — {stelle.company}
        </h2>
        <Select
          value={application.vorlage ?? undefined}
          disabled={wechselLaeuft || !vorlagenQuery.data}
          onValueChange={(vorlage) => wechselMutation.mutate(vorlage)}
        >
          <SelectTrigger className="w-56" aria-label="Vorlage">
            <SelectValue placeholder={wechselLaeuft ? "wird gewechselt…" : "Vorlage wählen"} />
          </SelectTrigger>
          <SelectContent>
            {vorlagenQuery.data?.map((v) => (
              <SelectItem key={v.slug} value={v.slug} disabled={v.fehler !== null}>
                {v.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
```

Hinweis: Hooks (`useQueryClient`, `useQuery`, `useMutation`, `useTaskErgebnis`) müssen vor den frühen `return`s (`isLoading`, `!detailQuery.data`) stehen — also direkt hinter `exportTask` einfügen, nicht hinter `const { application, stelle } = …`. `SlotCard`s werden per `key={name}` gerendert; nach dem Wechsel neu geladene Slots erscheinen automatisch.

- [ ] **Step 10: Profil und Proxy**

`ProfilPage.tsx`: `src={`/template-assets/assets/${dateiname}?v=${version}`}` → `src={`/eigen/${dateiname}?v=${version}`}`.

`vite.config.ts` Proxy:

```ts
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/applications': 'http://127.0.0.1:8765',
      '/vorlagen': 'http://127.0.0.1:8765',
      '/vorlagen-assets': 'http://127.0.0.1:8765',
      '/eigen': 'http://127.0.0.1:8765',
    },
```

Achtung: `/vorlagen` als Proxy-Präfix würde auch die SPA-Route `/vorlagen` an FastAPI schicken. Deshalb Präfix enger fassen: `'^/vorlagen/[^/]+/vorschau'` als Regex-Key (Vite unterstützt Keys mit `^`):

```ts
      '^/vorlagen/[^/]+/vorschau': 'http://127.0.0.1:8765',
```

statt `'/vorlagen'`.

- [ ] **Step 11: Typecheck, Tests, Build**

Run: `cd frontend && npm test -- --run && npm run build`
Expected: Vitest PASS, `tsc`/Vite-Build ohne Fehler, `frontend/dist/` aktualisiert.

- [ ] **Step 12: Im Browser prüfen**

Run: `uv run jobs serve --no-browser` und mit Playwright/Browser:
1. `/vorlagen`: Karte „Bewerbung“ mit Standard-Badge und skalierter Vorschau (Portrait sichtbar → `eigen/` funktioniert).
2. ZIP (z. B. `templates/beispiel` gezippt: `cd templates/beispiel && zip -r /tmp/claude-1000/beispiel.zip .`) hochladen → neue Karte.
3. Duplizieren, Umbenennen, als Standard setzen, Löschen (gesperrt bei Standard/Nutzung mit Tooltip).
4. Bewerbung öffnen → Dropdown → andere Vorlage → Toast „Vorlage gewechselt“, Vorschau zeigt neues Layout, manuell geänderter Slot bleibt.
5. Profil: Portrait wird angezeigt, Upload aktualisiert Bild in Vorschau.
6. Mobile Breite (390 px): Vorlagen-Seite ohne horizontales Scrollen, Dropdown bedienbar.

- [ ] **Step 13: Commit**

```bash
git add frontend
git commit -m "feat(frontend): Vorlagen-Seite und Vorlagenwahl in der Bewerbung

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```

---

### Task 10: Aufräumen und Doku

**Files:**
- Modify: `.env.example`, `README.md`, `CLAUDE.md`, `.gitignore`
- Delete: `templates/beispiel.html`, `templates/assets/fonts/*` (Repo-Kopie; Fonts leben jetzt in `templates/beispiel/assets/fonts/` bzw. per Migration in `data/vorlagen/bewerbung/assets/`), `templates/styles.css` (nur wenn Step 1 zeigt, dass sie nichts mehr referenziert)
- Create: `docs/releases/2026-09-23.md` ergänzen (oder neue datierte Datei, falls der Release schon draußen ist)

- [ ] **Step 1: Verweise prüfen**

Run: `grep -rn "TEMPLATE_PATH\|template-assets\|templates/beispiel.html\|templates/assets\|templates/styles.css" --include=*.py --include=*.ts --include=*.tsx --include=*.md --include=*.example . | grep -v node_modules | grep -v docs/superpowers`
Expected: nur Treffer in `vorlagen.py::_migriere_altvorlage` (liest `templates_dir/styles.css` und `templates_dir/assets` — die müssen für Bestandsinstallationen **bleiben**, solange dort eine `bewerbung.html` liegt) und in Doku, die in diesem Task angepasst wird.

Entscheidung: `templates/styles.css` und `templates/assets/fonts/` sind im Repo getrackt und werden von der Migration einer Bestandsinstallation gebraucht (`templates/bewerbung.html` ist gitignored und lokal). Daher **nicht** löschen, solange es Bestandsinstallationen gibt; nur `templates/beispiel.html` (keine Referenz mehr) entfernen. In der Release-Note vermerken, dass `templates/bewerbung.html`, `templates/styles.css`, `templates/assets/` nach erfolgreicher Migration lokal gelöscht werden können.

```bash
git rm templates/beispiel.html
```

- [ ] **Step 2: `.env.example`** — `TEMPLATE_PATH=…` (falls vorhanden) entfernen, ergänzen:

```
# Bewerbungsvorlagen (je Vorlage ein Ordner) und persönliche Dateien
# (Portrait, Unterschrift). Default: data/vorlagen, data/eigen.
VORLAGEN_DIR=
EIGEN_DIR=
```

- [ ] **Step 3: README** — Zeile „Vorlage & Slots“ (`README.md:31`) ersetzen durch:

```
| Vorlagen | mehrere HTML-Vorlagen mit `data-slot`-Markierungen (`data/vorlagen/<name>/`), per ZIP hochladen, duplizieren, umbenennen; Standardvorlage und Wechsel pro Bewerbung — Textblöcke per LLM aus Profil + Stellenanzeige, einzeln nachbearbeitbar |
```

und einen kurzen Abschnitt „Vorlagen“ mit den CLI-Befehlen aus Task 8 und dem ZIP-Aufbau (index.html, styles.css, assets/, `eigen/portrait.jpg`, `eigen/signature.png`, keine Skripte).

- [ ] **Step 4: `CLAUDE.md`** (Projekt) — im Abschnitt „Pipeline-Fluss“ `generate (LLM füllt data-slot-Blöcke in einer HTML-Vorlage …)` ergänzen um: „Vorlagen liegen je Ordner unter `data/vorlagen/<slug>/` (`vorlagen.py`), jede Bewerbung merkt sich ihren Slug; `vorlagen.migriere` läuft bei jedem Start (CLI und `serve`). Tests müssen `vorlagen_dir`/`eigen_dir`/`templates_dir` auf `tmp_path` setzen (Helfer `tests/vorlagen_hilfe.py`).“

- [ ] **Step 5: Release Notes** — in `docs/releases/2026-09-23.md` unter „Neu“:

```markdown
- **Mehrere Vorlagen**: Vorlagen liegen je Ordner unter `data/vorlagen/`. Neue Seite „Vorlagen“ (Symbol im Header) und CLI `jobs vorlagen …`: ZIP hochladen, duplizieren, umbenennen, löschen, Standard setzen. Jede Bewerbung merkt sich ihre Vorlage; Wechsel per Dropdown bzw. `jobs vorlage-wechseln` — vorhandene (auch manuell bearbeitete) Texte bleiben, nur fehlende Blöcke schreibt das LLM.
```

unter „Behoben“:

```markdown
- Alte Bewerbungen wurden mit der jeweils aktuellen globalen Vorlage gerendert statt mit ihrer eigenen.
```

unter „Hinweise“:

```markdown
- Beim ersten Start wird `templates/bewerbung.html` (+ `styles.css`, `assets/`) nach `data/vorlagen/bewerbung/` übernommen, Portrait und Unterschrift nach `data/eigen/` kopiert. Danach können die alten Dateien unter `templates/` lokal gelöscht werden. `TEMPLATE_PATH` entfällt.
- Neue Umgebungsvariablen `VORLAGEN_DIR`, `EIGEN_DIR` (Docker: als Volume einbinden).
```

- [ ] **Step 6: Gesamte Suite**

Run: `uv run pytest -q && (cd frontend && npm test -- --run)`
Expected: alles PASS

- [ ] **Step 7: Commit**

```bash
git add -A .env.example README.md CLAUDE.md docs/releases templates
git commit -m "docs: mehrere Vorlagen dokumentieren, Altlasten entfernen

Claude-Session: https://claude.ai/code/session_01JgLrjTCZJcHbmHjMWeEqQJ"
```
