# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Befehle

- Package-Manager ist **uv** (kein pip/poetry). Setup: `uv sync`, dann `.env` aus `.env.example` und `profile.yaml` aus `profile.yaml.example` befüllen.
- Python `>=3.13`, src-layout (`src/bewerbungs_pipeline/`), Entry-Point `jobs` (`[project.scripts]` in `pyproject.toml`).
- Alles läuft über `uv run jobs <subcommand>` — kein Makefile/justfile.
- Tests: `uv run pytest`. `pyproject.toml` setzt `filterwarnings = ["error"]` mit einer expliziten Ausnahme für eine starlette/httpx-Deprecation — jede neue, nicht whitelistete Warnung lässt Tests fehlschlagen.
- Kein Linter/Formatter konfiguriert (kein ruff/black/flake8-Setup).

## Pipeline-Fluss (CLI ist der primäre Weg, Web baut nur drauf auf)

`fetch` (Suche + Anreicherung + Frischeprüfung) → `check` (gleicht Bestand gegen die Arbeitsagentur-API ab, markiert verschwundene Anzeigen statt sie zu löschen — läuft auch automatisch bei jedem `fetch` mit) → `list`/`pick`/`reject` (Statuspflege) → `generate` (LLM füllt `data-slot`-Blöcke in einer HTML-Vorlage anhand `profile.yaml` + Stellendetails) → PDF-Export via lokalem Chromium (Playwright braucht einen bereits installierten Browser: chromium/google-chrome/brave, sonst Abbruch mit Fehlermeldung).

Storage ist reines SQLite (`data/jobs.db`, gitignored), kein ORM — Schema direkt in `db.py`.

## Web

`uv run jobs serve` startet FastAPI + HTMX + Jinja2 (Default-Port 8765, `--port`, `--no-browser`). Kein npm/Node, kein separates JS-Frontend. Web nutzt dieselbe Business-Logik wie die CLI (`applications.py`, `db.py`), keine Duplikation. Background-Tasks (`tasks.py`) halten Status bewusst nur im Speicher (ThreadPoolExecutor, max. 2 Worker) — überlebt keinen App-Neustart, ist Absicht (Einzelbetrieb).

## Gotchas

- `CBKS_INBOX` (Env-Var) verweist auf ein externes Schwister-Repo (`/home/a/Dev/cbks`) — in `config.py` als optionaler Pfad verankert, aktuell aber nirgends aktiv genutzt.
- LLM-Output (`llm.py`) wird aktiv gegen `profile.yaml` validiert (keine erfundenen Angaben, keine Technologien außerhalb des Profils, erzwungenes Antwortschema) — nicht blind übernehmen, wenn an der Generierung gearbeitet wird.
- Git-Workflow: Commits gehen direkt auf `master`, keine Feature-Branches/PRs.

## Doku

Design-Specs und Implementierungspläne liegen datiert unter `docs/specs/` und `docs/plans/`.
