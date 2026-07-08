# Bewerbungs-Pipeline: Scrapy → Audit-Generator

**Datum:** 2026-07-08
**Status:** Entwurf, wartet auf Review

## Ziel

Stellen automatisch finden, in einer Shortlist sammeln, und pro ausgewählter
Stelle eine individuelle Bewerbung generieren — im Stil des bestehenden
AC-Motoren-Dokuments: ein **Website- und Sichtbarkeits-Audit** der Zielfirma
(Kennwerte, Performance, Security-Header, KI-Sichtbarkeit, Handlungsempfehlungen),
kein klassisches Anschreiben.

## Ist-Zustand

- `/home/a/Dev/ac-motoren/index.html` — mit Claude Design erstelltes Audit
  (214 KB, self-contained HTML). Abschnitte: Kennwerte im Überblick,
  Ausgangslage, Auffindbarkeit & strukturierte Daten, KI-Sichtbarkeit (S/A/T),
  Performance, Security-Header, Internationale Konsistenz, Social-Media-Präsenz,
  Handlungsempfehlungen, Zusammenfassung. Dient als **Struktur- und Stilvorlage**.
- `/home/a/Dev/scrapy` — Scrapy 2.17.0, geklont und lauffähig eingerichtet
  (venv, Python 3.13, `pip install -e .`). Dient als Referenz zum Nachschlagen.
  Die Pipeline selbst nutzt Scrapy als normale Dependency, nicht den Klon.

## Kernentscheidung

Das Audit ist **Inhalt, kein Formular**. Reines Platzhalter-Ersetzen reicht
nicht — die Pipeline muss pro Firma echte Messdaten erheben und Claude
schreibt daraus das Audit neu, mit der AC-Motoren-HTML als Vorlage.

**Eiserne Regel:** Es werden nur gemessene Werte verwendet. Fehlt ein Wert,
wird der Abschnitt gekürzt oder als „nicht erhoben" markiert. Claude darf
keine Kennzahlen erfinden — eine Bewerbung mit erfundenen Messwerten wäre
schlimmer als keine.

## Architektur — drei Stufen

```
Spiders → SQLite (Shortlist) → CLI-Auswahl → Messung → Claude → Audit-HTML
```

### Stufe 1: Finden (Scrapy-Projekt `jobs/`)

Eigenes Scrapy-Projekt mit einem Spider pro Quelle:

| Spider | Quelle | Phase | Anmerkung |
|---|---|---|---|
| `arbeitsagentur` | Jobsuche-API der Bundesagentur für Arbeit | 1 | Offizielle, kostenlose REST-API, JSON statt HTML-Parsing. Stabilste Quelle. |
| `career_pages` | Firmen-Karriereseiten | 3 | Generischer Spider, Firmen + CSS-Selektoren in einer YAML-Datei konfiguriert. |
| `indeed`, `stepstone` | Portale | 4 | **ToS-Verstoß, aktives Bot-Blocking (Cloudflare).** Best effort mit scrapy-playwright, kann jederzeit brechen. Bewusst letzte Phase. |

**Item-Schema** (`JobItem`):

```python
title: str
company: str
company_website: str | None   # Kern-Input für das Audit
location: str
url: str                      # Link zur Anzeige
source: str                   # "arbeitsagentur" | "career:<name>" | ...
posted_at: date | None
contact_name: str | None
contact_email: str | None
description_text: str         # Klartext der Anzeige
scraped_at: datetime
```

**Speicherung:** SQLite-Datei `jobs.db`, eine Tabelle `jobs` mit
Status-Spalte (`new` / `selected` / `generated` / `rejected`).
Dedupe über Hash aus `(company, title)` in einer Scrapy-Item-Pipeline.

### Stufe 2: Shortlist (CLI)

Kleines CLI, kein UI:

```
jobs crawl [spider]      # Spider laufen lassen
jobs list [--new]        # Stellen tabellarisch anzeigen
jobs pick <id>           # Stelle auswählen (status=selected)
jobs reject <id>         # aussortieren
jobs generate <id>       # Stufe 3 für diese Stelle starten
```

### Stufe 3: Generieren (pro ausgewählter Stelle)

**3a — Messung** der Firmen-Website (eigenes Modul `audit/collect.py`):

- HTTP-Response- und Security-Header (HSTS, CSP, X-Frame-Options, …)
- `robots.txt`, Sitemap vorhanden/erreichbar
- Meta-Tags, Open Graph, JSON-LD / strukturierte Daten der Startseite
- PageSpeed Insights API (kostenlos, API-Key): Performance-Scores mobil/desktop
- Social-Media-Links auf der Website
- Ergebnis: `data.json` mit allen Rohwerten; nicht Messbares explizit `null`

**3b — Claude-Generierung** (`audit/generate.py`):

- Input: `data.json`, Stellenanzeige (Klartext), AC-Motoren-HTML als Vorlage
- Modell: `claude-sonnet-5` über die Anthropic API
- Auftrag: gleiche Struktur und gleicher Stil wie die Vorlage, Inhalte
  ausschließlich aus den Messdaten; fehlende Daten → Abschnitt weglassen
- Validierung der Ausgabe: HTML parsebar, Firmenname enthalten, keine
  Platzhalter-Reste. Bei Fehlschlag genau ein Retry, dann Abbruch mit Log.

**Output:** `out/<firma-slug>/index.html` + `out/<firma-slug>/data.json`

## Fehlerbehandlung

- **Spider:** Scrapy-Defaults (Retry, Timeout). Eine kaputte Quelle stoppt
  die anderen nicht — jeder Spider läuft unabhängig.
- **Messung:** Jeder Messschritt ist unabhängig; Ausfall eines Schritts
  liefert `null` statt Abbruch.
- **Generierung:** Validierung wie oben; `data.json` bleibt erhalten, sodass
  ein erneuter Lauf keine Messung wiederholen muss.

## Technik

- Python 3.13, `uv`, ein Projekt `/home/a/Dev/bewerbungs-pipeline`
- Dependencies: `scrapy`, `anthropic`, `httpx`; später `scrapy-playwright` (Phase 4)
- Secrets in `.env`: `ANTHROPIC_API_KEY`, `PAGESPEED_API_KEY` — nie im Code
- Tests: Unit-Tests für Parser und Messmodule mit gespeicherten
  HTML-/JSON-Fixtures (kein Netz in Tests)

## Phasenplan

1. **Arbeitsagentur-Spider + SQLite + CLI-Shortlist** — Ende-zu-Ende von
   Suche bis Auswahl, ohne Generierung
2. **Messung + Claude-Generator** — erste komplette Bewerbung aus der Pipeline
3. **Karriereseiten-Spider** — YAML-konfigurierte Firmenliste
4. **Indeed/StepStone** — optional, mit bekanntem Risiko

## Nicht-Ziele (YAGNI)

- Kein automatischer Versand von Bewerbungen
- Keine Generierung ohne manuelle Auswahl (Kosten, Fehlgriffe)
- Kein Web-UI — das CLI reicht
- Kein Scheduler in Phase 1 (Crawl wird manuell gestartet; Cron später bei Bedarf)
