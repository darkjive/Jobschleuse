# Bewerbungs-Pipeline: Stellen finden → Vorlage füllen

**Datum:** 2026-07-08 (Rev. 3 — nach Verifikation: API-Status korrigiert,
JobSpy für Phase 3, Dedupe-Fix)
**Status:** Entwurf, wartet auf Review

## Ziel

Stellen automatisch finden, in einer Shortlist sammeln, und pro ausgewählter
Stelle die bestehende Bewerbungsvorlage (Claude-Design-HTML, z. B.
`ac-motoren/index.html`) mit stellen- und firmenspezifischem Text füllen.
Die Pipeline kümmert sich **nur um Text**: gescrapte Inhalte lesen, per LLM
personalisieren, in die Vorlage einsetzen.

## Werkzeugwahl

- **Arbeitsagentur-API** (Bundesagentur für Arbeit): Quelle Nr. 1. Die REST-API
  hinter der offiziellen Jobbörse — kostenlos, ohne Registrierung, strukturierte
  Daten, kein Scraping nötig. Nur `httpx`. **Ehrlicherweise:** nicht offiziell
  für Dritte angeboten; Doku kommt vom Community-Projekt bundesAPI
  (github.com/bundesAPI/jobsuche-api). Seit Jahren stabil, aber ohne Garantie.
  Basis: `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service`,
  Header `X-API-KEY: jobboerse-jobsuche`, Suche via `/pc/v6/jobs` (v4 als
  Fallback prüfen), Details via `/pc/v4/jobdetails/{base64(refnr)}`.
- **Crawl4AI** (Python, Playwright-basiert): für Portale und
  Firmen-Karriereseiten. Liefert Seiten als LLM-fertiges Markdown mit
  Undetected-Browser-Support. Vorteil: **keine CSS-Selektoren pro Quelle** —
  das LLM extrahiert die Felder aus dem Markdown.
- **Scrapling**: Fallback-Fetcher für hart geschützte Seiten
  (Cloudflare Turnstile, TLS-Fingerprinting), nur einbauen wenn Crawl4AI
  an einer wichtigen Quelle scheitert (YAGNI).
- **MarkItDown** (Microsoft): optionales Add-on, falls Stellenanzeigen nur
  als PDF vorliegen — konvertiert sie zu Markdown fürs LLM. Erst einbauen,
  wenn der Fall real auftritt.
- **Scrapy entfällt.** Es hat keine Anti-Bot-Fähigkeiten (plain HTTP, sofort
  erkennbar) und seine Stärken (Crawl-Infrastruktur, Selektoren-Pipelines)
  braucht dieser Workflow nicht. Der Klon unter `/home/a/Dev/scrapy` kann weg.

**Geprüft und verworfen:** Firecrawl (Bezahl-SaaS, macht dasselbe wie
Crawl4AI), Crawlee (Node-Stack, kein Mehrwert), curl-impersonate (steckt
bereits in Scrapling via curl_cffi), AutoScraper (unmaintained seit 2022,
durch LLM-Extraktion obsolet), Playwright direkt (ist bereits die Engine
von Crawl4AI), Puppeteer/Selenium (älter, kein Vorteil), PySpider (tot),
Nutch/StormCrawler/Heritrix/Colly/Katana (Suchmaschinen-/Recon-Infrastruktur,
Overkill), ScrapeGraphAI/LLM Scraper (duplizieren unsere LLM-Extraktion),
fastCRW (jung, kein Vorteil bei diesem Umfang), Maxun/browserless/
chromedp/Rod (Skalierungs-/Go-Infra, Overkill für Solo-Betrieb).

**Rechtlicher Hinweis:** Crawl4AI/Scrapling lösen das technische Blocking,
nicht die ToS. Indeed/StepStone verbieten Scraping vertraglich — nutzbar,
aber auf eigenes Risiko und jederzeit brüchig. Deshalb letzte Phase.

## Architektur — drei Stufen

```
Quellen → jobs.db (SQLite) → CLI-Auswahl → LLM füllt Vorlage → out/<firma>/index.html
```

### Stufe 1: Finden

Ein Modul pro Quelle, alle schreiben dasselbe `JobItem` in SQLite:

| Quelle | Technik | Phase |
|---|---|---|
| Arbeitsagentur | REST-API via httpx, JSON | 1 |
| Firmen-Karriereseiten | Crawl4AI → Markdown → LLM extrahiert Felder | 2 |
| Indeed / LinkedIn / Glassdoor | `python-jobspy` (gepflegte Lib, Indeed via interne API, `country_indeed="germany"`) | 3 |
| StepStone | Crawl4AI wie Karriereseiten, ggf. Scrapling-Fallback (JobSpy kann StepStone nicht) | 3 |

**JobItem:**

```python
title: str
company: str
company_website: str | None
location: str
url: str  # Link zur Anzeige
source: str
posted_at: date | None
contact_name: str | None
contact_email: str | None
description_md: str  # Anzeige als Markdown/Klartext
scraped_at: datetime
```

**Speicherung:** eine SQLite-Datei `jobs.db`, Tabelle `jobs` mit
Status-Spalte (`new` / `selected` / `generated` / `rejected`).
Dedupe beim Insert: primär über `url` bzw. Referenznummer der Quelle
(UNIQUE), sekundär über Hash aus `(company, title, location)` gegen
Duplikate derselben Stelle aus verschiedenen Quellen. Nicht nur
`(company, title)` — sonst kollabieren gleiche Rollen an zwei Standorten.

### Stufe 2: Shortlist (CLI)

```
jobs fetch [quelle]      # Quellen abrufen
jobs list [--new]        # Stellen tabellarisch anzeigen
jobs pick <id>           # auswählen (status=selected)
jobs reject <id>         # aussortieren
jobs generate <id>       # Stufe 3 für diese Stelle
```

### Stufe 3: Vorlage füllen (Slot-Ansatz)

Die Vorlage ist ~214 KB HTML. Das LLM schreibt **nicht** das ganze Dokument
um (teuer, fehleranfällig, Layout-Risiko), sondern nur die variablen Texte:

1. **Einmalig:** In einer Kopie der Vorlage die variablen Textblöcke mit
   `data-slot="firma"`, `data-slot="anrede"`, `data-slot="einstieg"`, …
   markieren. Das definiert, was pro Bewerbung wechselt.
2. **Pro Stelle:** LLM bekommt die Stellenanzeige (`description_md`) und die
   Liste der Slots mit ihren bisherigen Beispieltexten → liefert JSON
   `{slot: neuer_text}`.
3. **Einsetzen:** Python-Script parst die Vorlage, ersetzt die Slot-Inhalte,
   schreibt `out/<firma-slug>/index.html`. Layout bleibt garantiert intakt.

**LLM konfigurierbar** über OpenAI-kompatiblen Endpoint (`.env`:
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`) — funktioniert mit GLM wie mit
Claude. **Eiserne Regel:** Das LLM formuliert nur aus Anzeige + Vorlagentexten;
Fakten über die Firma, die nirgends stehen, werden nicht erfunden.

**Validierung:** Ausgabe-JSON enthält alle Slots, kein Slot leer,
Firmenname kommt vor. Bei Fehlschlag genau ein Retry, dann Abbruch mit Log.

## CBKS-Integration

CBKS (`/home/a/Dev/cbks`, SQLite + FAISS + Inbox-Ingestion) ist die
persönliche Wissensbasis. Grundsatz: **Integration statt Verschmelzung** —
CBKS hält Wissen, die Pipeline hält ihren Betriebszustand.

1. **Profil lesen:** Bewerberdaten (Name, Adresse, Kontakt) kommen aus einer
   Profil-Schnittstelle. Phase 1: `profile.yaml`. Später, wenn die CBKS-API
   (dort Phase 3) steht: CBKS-Adapter mit denselben Feldern. Persönliche
   Daten werden nie in Pipeline-Code oder Vorlagen hardcodiert — das hält
   den Generator auch für andere Nutzer verwendbar, ohne dass jetzt
   Multi-User-Features gebaut werden.
2. **Archiv schreiben:** Nach `generate` werden Bewerbung + Stellenanzeige
   in die CBKS-Inbox gelegt (Dateiablage, keine API nötig). CBKS ingestiert
   sie wie jedes andere Dokument; die Bewerbungshistorie wird Teil des
   Wissensgraphen.
3. **`jobs.db` bleibt bei der Pipeline:** Workflow-Status ist Betriebszustand,
   kein Wissen. Keine Kopplung an CBKS-Schema oder -Reifegrad.

Arbeitsverträge, Gehaltsabrechnungen etc. gehören direkt in CBKS und sind
kein Thema dieser Pipeline.

## Fehlerbehandlung

- Quellen unabhängig: eine kaputte Quelle stoppt die anderen nicht.
- LLM-Extraktion (Stufe 1) und -Füllung (Stufe 3) validieren gegen das
  Schema; Rohdaten (`description_md`) bleiben in der DB, sodass ein
  erneuter Lauf nichts neu scrapen muss.

## Technik

- Python 3.13 via `uv` (Versionsverwaltung wie nvm: `uv venv --python 3.13`)
- Projekt: `/home/a/Dev/bewerbungs-pipeline`
- Dependencies: `httpx`, `pydantic` (JobItem-/Slot-Validierung), `openai`
  (Client für jeden OpenAI-kompatiblen Endpoint), `beautifulsoup4` + `lxml`
  (Slot-Ersetzung in der Vorlage); ab Phase 2 `crawl4ai`; ab Phase 3
  `python-jobspy`; `scrapling` nur bei Bedarf
- Secrets in `.env`, nie im Code
- Tests: Unit-Tests für Slot-Ersetzung und JobItem-Validierung mit
  Fixtures (kein Netz in Tests)

## Phasenplan

1. **Arbeitsagentur + SQLite + CLI + Slot-Füllung** — kompletter Durchstich
   von Suche bis fertiger Bewerbung mit der legalen, stabilen Quelle
2. **Karriereseiten via Crawl4AI** — Markdown → LLM-Extraktion
3. **Portale** — Indeed/LinkedIn/Glassdoor via `python-jobspy` (gepflegte
   Lib statt Eigenbau), StepStone via Crawl4AI. Optional, ToS-Risiko.

**Abgrenzung zu existierenden Lösungen (geprüft 2026-07-08):** AIHawk, das
bekannteste Auto-Apply-Tool, ist seit Mai 2026 archiviert (Team auf
proprietäres Produkt geschwenkt) und verfolgt ohnehin das Gegenteil dieses
Ansatzes (Massenbewerbung statt kuratierter Shortlist mit eigener Vorlage).
JobSpy löst nur das Scraping und wird als Phase-3-Dependency übernommen.
Eine fertige Lösung für deutsche Quellen + eigene Design-Vorlage +
CBKS-Anbindung existiert nicht.

## Nicht-Ziele (YAGNI)

- Kein automatischer Versand von Bewerbungen. Falls später gewünscht
  (Bewerbungsformulare automatisch ausfüllen), wäre Browser Use der
  Kandidat — bewusst nicht jetzt.
- Keine Generierung ohne manuelle Auswahl
- Kein Web-UI — das CLI reicht
- Keine Multi-User-/SaaS-Features. Die Profil-Schnittstelle (keine
  persönlichen Daten im Code) ist die einzige Vorbereitung auf eine
  spätere Nutzung durch andere — mehr erst bei echtem Bedarf.
- Kein Scheduler in Phase 1; Cron später bei Bedarf
