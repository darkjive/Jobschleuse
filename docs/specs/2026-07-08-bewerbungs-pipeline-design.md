# Bewerbungs-Pipeline: Stellen finden → Vorlage füllen

**Datum:** 2026-07-08 (Rev. 2 — Audit-Stufe gestrichen, Crawl4AI statt Scrapy)
**Status:** Entwurf, wartet auf Review

## Ziel

Stellen automatisch finden, in einer Shortlist sammeln, und pro ausgewählter
Stelle die bestehende Bewerbungsvorlage (Claude-Design-HTML, z. B.
`ac-motoren/index.html`) mit stellen- und firmenspezifischem Text füllen.
Die Pipeline kümmert sich **nur um Text**: gescrapte Inhalte lesen, per LLM
personalisieren, in die Vorlage einsetzen.

## Werkzeugwahl

- **Arbeitsagentur-API** (Bundesagentur für Arbeit): Quelle Nr. 1. Offizielle,
  kostenlose REST-API, strukturierte Daten, kein Scraping nötig. Nur `httpx`.
- **Crawl4AI** (Python, Playwright-basiert): für Portale und
  Firmen-Karriereseiten. Liefert Seiten als LLM-fertiges Markdown mit
  Undetected-Browser-Support. Vorteil: **keine CSS-Selektoren pro Quelle** —
  das LLM extrahiert die Felder aus dem Markdown.
- **Scrapling**: Fallback-Fetcher für hart geschützte Seiten
  (Cloudflare Turnstile, TLS-Fingerprinting), nur einbauen wenn Crawl4AI
  an einer wichtigen Quelle scheitert (YAGNI).
- **Scrapy entfällt.** Es hat keine Anti-Bot-Fähigkeiten (plain HTTP, sofort
  erkennbar) und seine Stärken (Crawl-Infrastruktur, Selektoren-Pipelines)
  braucht dieser Workflow nicht. Der Klon unter `/home/a/Dev/scrapy` kann weg.

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
| Indeed / StepStone | wie Karriereseiten, ggf. Scrapling-Fallback | 3 |

**JobItem:**

```python
title: str
company: str
company_website: str | None
location: str
url: str                      # Link zur Anzeige
source: str
posted_at: date | None
contact_name: str | None
contact_email: str | None
description_md: str           # Anzeige als Markdown/Klartext
scraped_at: datetime
```

**Speicherung:** eine SQLite-Datei `jobs.db`, Tabelle `jobs` mit
Status-Spalte (`new` / `selected` / `generated` / `rejected`).
Dedupe über Hash aus `(company, title)` beim Insert.

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

## Fehlerbehandlung

- Quellen unabhängig: eine kaputte Quelle stoppt die anderen nicht.
- LLM-Extraktion (Stufe 1) und -Füllung (Stufe 3) validieren gegen das
  Schema; Rohdaten (`description_md`) bleiben in der DB, sodass ein
  erneuter Lauf nichts neu scrapen muss.

## Technik

- Python 3.13 via `uv` (Versionsverwaltung wie nvm: `uv venv --python 3.13`)
- Projekt: `/home/a/Dev/bewerbungs-pipeline`
- Dependencies: `httpx`, `crawl4ai`, `openai` (Client für jeden
  OpenAI-kompatiblen Endpoint); `scrapling` nur bei Bedarf
- Secrets in `.env`, nie im Code
- Tests: Unit-Tests für Slot-Ersetzung und JobItem-Validierung mit
  Fixtures (kein Netz in Tests)

## Phasenplan

1. **Arbeitsagentur + SQLite + CLI + Slot-Füllung** — kompletter Durchstich
   von Suche bis fertiger Bewerbung mit der legalen, stabilen Quelle
2. **Karriereseiten via Crawl4AI** — Markdown → LLM-Extraktion
3. **Indeed/StepStone** — optional, ToS-Risiko, ggf. Scrapling

## Nicht-Ziele (YAGNI)

- Kein automatischer Versand von Bewerbungen
- Keine Generierung ohne manuelle Auswahl
- Kein Web-UI — das CLI reicht
- Kein Scheduler in Phase 1; Cron später bei Bedarf
