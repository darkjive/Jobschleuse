# Bewerbungs-Pipeline

Stellen finden → Shortlist → Bewerbungsvorlage per LLM füllen.
Spec: `docs/specs/2026-07-08-bewerbungs-pipeline-design.md`.

## Setup

    uv sync
    cp .env.example .env        # LLM_BASE_URL, LLM_API_KEY, LLM_MODEL eintragen
    cp profile.yaml.example profile.yaml   # persönliche Daten eintragen

## Eigene Vorlage anschließen

1. Claude-Design-HTML kopieren, z. B.:
   `cp /home/a/Dev/ac-motoren/index.html templates/vorlage.html`
2. In der Kopie jeden Textblock, der pro Bewerbung wechseln soll, mit
   `data-slot="name"` markieren (eindeutige Namen). Alles ohne `data-slot`
   bleibt unverändert.
3. `TEMPLATE_PATH=templates/vorlage.html` in `.env` setzen.
   Ohne eigenen Schritt läuft alles mit der Demo-Vorlage `templates/beispiel.html`
   (`TEMPLATE_PATH=templates/beispiel.html`).

## Benutzung

    uv run jobs fetch --was "Mechatroniker" --wo "Frankfurt" --umkreis 50
    uv run jobs list --status new
    uv run jobs pick 3
    uv run jobs generate 3      # → out/<firma>/index.html

Mit `CBKS_INBOX=/home/a/Dev/cbks/data/inbox` in `.env` landet jede fertige
Bewerbung zusätzlich als Kopie in der CBKS-Inbox.
