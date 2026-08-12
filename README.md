# Bewerbungs-Pipeline

Stellen finden → Shortlist → Bewerbungsvorlage per LLM füllen.
Spec: `docs/specs/2026-07-08-bewerbungs-pipeline-design.md`.

## Setup

    uv sync
    cp .env.example .env        # LLM_BASE_URL, LLM_API_KEY, LLM_MODEL eintragen
    cp profile.yaml.example profile.yaml   # persönliche Daten eintragen

## Vorlagen

`templates/` enthält:

- `beispiel.html` – Demo-Vorlage (Minimal-Beispiel, Default).
- `beispiel-org.html` – Demo-Vorlage mit organisationsspezifischen Slots.
- `bewerbung.html` – Eigene Bewerbungsvorlage (mit `assets/` und `styles.css`).
- `styles.css` – Geteilte Styles für `bewerbung.html`.
- `assets/` – Bilder, Fonts etc. für `bewerbung.html`.

## Eigene Vorlage anschließen

1. HTML-Datei nach `templates/<name>.html` kopieren.
2. Jeden Textblock, der pro Bewerbung wechseln soll, mit
   `data-slot="name"` markieren (eindeutige Namen). Alles ohne `data-slot`
   bleibt unverändert.
3. `TEMPLATE_PATH=templates/<name>.html` in `.env` setzen.
   Ohne eigenen Schritt läuft alles mit der Demo-Vorlage
   (`TEMPLATE_PATH=templates/beispiel.html`).

## Benutzung

    uv run jobs fetch --was "Mechatroniker" --wo "Frankfurt" --umkreis 50
    uv run jobs list --status new
    uv run jobs pick 3
    uv run jobs generate 3      # → out/<firma>/index.html

## Weboberfläche

    uv run jobs serve            # → http://127.0.0.1:8765

Stellen sichten und auswählen, Bewerbung erzeugen, einzelne Textblöcke
nachbearbeiten oder neu erzeugen lassen, Vorschau ansehen, exportieren.
Läuft ausschließlich lokal, ohne Login.

Das CLI bleibt unverändert nutzbar.

