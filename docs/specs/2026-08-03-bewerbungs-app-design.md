# Bewerbungs-App: lokale Weboberfläche für die Pipeline

**Datum:** 2026-08-03
**Status:** Entwurf, wartet auf Review
**Vorgänger:** `2026-07-08-bewerbungs-pipeline-design.md`

## Ziel

Der gesamte Weg von der Stellenanzeige bis zur fertigen, redigierten Bewerbung
soll ohne Terminal möglich sein: Stellen sichten, auswählen, Bewerbung
generieren, einzelne Textblöcke nachbearbeiten oder neu erzeugen lassen,
Ergebnis exportieren.

Diese Etappe deckt **Sichten/Auswählen** und **Generieren/Redigieren** ab.
Export-Paket (PDF, Anhänge, Mailtext) und Bewerbungs-Tracking sind Etappe 3
und 4 und ausdrücklich nicht Teil dieser Spec.

**Revision gegenüber der Vorgänger-Spec:** Dort stand „Kein Web-UI — das CLI
reicht" als Nicht-Ziel. Das wird hiermit bewusst aufgehoben. Das CLI bleibt
vollständig erhalten und funktionsfähig.

## Randbedingungen

- **Einzelbetrieb, ausschließlich lokal.** Bindung an `127.0.0.1`, kein Login,
  keine Benutzerverwaltung, keine Cloud. Die App liest `profile.yaml` und
  schreibt in `jobs.db` — sie hat im Netz nichts verloren.
- **Versand bleibt manuell.** Die App bereitet vor, sie verschickt nicht.
- **LLM läuft lokal** (Ollama, OpenAI-kompatibler Endpoint). Ein Lauf dauert
  realistisch 30–60 Sekunden; die Oberfläche muss das aushalten, ohne zu
  blockieren.
- **Bestehende Module bleiben unverändert:** `db`, `slots`, `llm`, `models`,
  `sources`. Die App ist eine zusätzliche Schicht, kein Rewrite.

## Technikwahl

**FastAPI + server-gerendertes HTML (Jinja2) + HTMX.**

Alles bleibt Python, `uv` bleibt die einzige Toolchain, es gibt keinen
Build-Step und kein Node. HTMX deckt genau die anfallenden Interaktionen ab —
Liste filtern, Zeile auswählen, Slot neu generieren, Textblock speichern:
lauter kleine Teil-Updates statt globalem Frontend-State. Die Design-Tokens
kommen als reines CSS herein, ohne dass ein Framework dazwischenfunkt. Die
lange LLM-Laufzeit wird per Polling auf einen Task-Status gelöst.

**Geprüft und verworfen:**

- *FastAPI + React/Vite-SPA:* zweite Sprache, Build-Step, Node im Projekt,
  jede Ansicht doppelt (Endpoint + Komponente). Für vier Screens im
  Einzelbetrieb schlecht investiert.
- *NiceGUI / Streamlit / Reflex:* am wenigsten Code, aber jedes bringt sein
  eigenes Aussehen mit und wehrt sich gegen fremde Design-Tokens — direkter
  Widerspruch zur Design-Entscheidung unten. Streamlit kann die generierte
  HTML-Bewerbung zudem nicht sinnvoll einbetten.

**Grenze des Ansatzes:** Für sehr reichhaltige Editier-Interaktionen
(Drag&Drop, komplexe Undo-Historie) wird HTMX eng. Das steht hier nicht an;
falls es später ansteht, ist die Grenze der Auslöser für eine Neubewertung.

## Design

Basis sind die **Design-Tokens des Vault-Wikis** (`/home/a/Dev/vault/
src/styles/global.css`): Grundton `#0d1017`, warmes Gold `#d4a574` als Akzent,
Textfarbe `#e6e1d8`, Satoshi als Schrift, JetBrains Mono für Monospace, dazu
die definierten Radien, Schatten und die Z-Index-Skala.

- Tokens werden als `web/static/tokens.css` **kopiert**, nicht importiert —
  der Vault ist ein eigenes Repo. Herkunftskommentar im Dateikopf.
- Satoshi liegt im Vault unter `vendor/fonts/Satoshi-Variable.woff2` und
  `Satoshi-VariableItalic.woff2` und wird mitkopiert. Keine externe
  Font-Abhängigkeit zur Laufzeit.
- **Das Layout wird neu entworfen**, zugeschnitten auf den Bewerbungs-Workflow.
  Die Layout-Komponenten des Wikis (Sidebar, CommandPalette, Kontext-Spalte)
  werden *nicht* übernommen — eine Bewerbungs-App ist kein Wiki.
- Methodische Leitplanken: die Design-Skills unter `vault/.agents/skills/`
  (`frontend-design`, `high-end-visual-design`, `web-design-guidelines`).

**Nicht betroffen:** Das Design der generierten Bewerbung
(`templates/bewerbung.html` + `styles.css` + `assets/`) bleibt unangetastet.

**Vault-Zugriff:** Nur Design-Dateien (CSS, Fonts, Design-Skills). Persönliche
Vault-Inhalte (`entity/`, `claim/`, `concept/`, `source/`) werden nicht gelesen
— siehe Vault-Ausnahme in `/home/a/Dev/AGENTS.md`.

## Architektur

```
jobs.db ── applications.py ── web/ (FastAPI + HTMX)
   │            │                    │
   │            └── llm.py, slots.py, sources/
   │
   └── cli.py (bleibt unverändert nutzbar)
```

### Umbau von `generate.py`

`generate.py` erledigt heute vier Dinge in einem Durchlauf: LLM aufrufen,
Vorlage füllen, Dateien schreiben, CBKS kopieren, Status setzen. Für
„nachbearbeiten und einzelne Slots neu generieren" muss das getrennt werden.
Neues Modul `applications.py`:

| Funktion | Aufgabe |
|---|---|
| `create(conn, job_id, cfg, client) -> int` | Beschreibung sicherstellen, Slots aus Vorlage lesen, LLM-Texte holen, validieren, `applications` + `application_slots` schreiben, ID zurückgeben |
| `get(conn, app_id)` | Bewerbung samt Slot-Werten laden |
| `set_slot(conn, app_id, slot, value)` | Einen Textblock speichern, `source='manuell'` |
| `regenerate_slot(conn, app_id, slot, cfg, client)` | Genau einen Slot neu erzeugen, `source='llm'` |
| `render(conn, app_id, cfg) -> str` | Vorlage mit aktuellen Slot-Werten füllen, HTML zurückgeben |
| `export(conn, app_id, cfg) -> Path` | `render()` + Dateien nach `out/<firma>/` + Assets + CBKS-Kopie |

Die Hilfsfunktionen `slugify` und `_ensure_description` wandern nach
`applications.py`. `generate.py` **bleibt als dünne Fassade bestehen**:
`generate_application()` ruft `create()` + `export()` und gibt weiterhin das
Ausgabeverzeichnis zurück. Damit bleiben `cli.py` und `tests/test_generate.py`
unverändert lauffähig — das ist der Nachweis, dass der Umbau nichts bricht.

### Modulstruktur

```
src/bewerbungs_pipeline/
  applications.py          # Domänenlogik (aus generate.py herausgelöst)
  tasks.py                 # Hintergrundläufe + Status
  web/
    app.py                 # FastAPI-Instanz, Routing, Startup
    routes/jobs.py         # Liste, Detail, pick/reject, fetch
    routes/applications.py # erzeugen, redigieren, Vorschau, exportieren
    routes/tasks.py        # Fortschritt abfragen
    templates/             # Jinja2 — Seiten und HTMX-Fragmente
    static/tokens.css      # Design-Tokens aus dem Vault
    static/app.css
    static/fonts/
```

**Jinja2 betrifft ausschließlich die App-Oberfläche.** Die Bewerbungsvorlage
bleibt beim `data-slot`-Ansatz mit BeautifulSoup. Die beiden Mechanismen
berühren sich nicht.

### Start

`uv run jobs serve` startet Uvicorn auf `127.0.0.1:8765` und öffnet den
Browser. Optionale Argumente: `--port`, `--no-browser`.

## Datenmodell

Zwei neue Tabellen, angelegt nach dem bestehenden
`CREATE TABLE IF NOT EXISTS`-Muster in `db.connect()`. Kein Alembic, kein
Migrations-Framework.

```sql
CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER NOT NULL REFERENCES jobs(id),
    template_path TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(job_id)
);

CREATE TABLE IF NOT EXISTS application_slots (
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    slot           TEXT NOT NULL,
    value          TEXT NOT NULL,
    source         TEXT NOT NULL,   -- 'llm' | 'manuell'
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (application_id, slot)
);
```

Damit sind alle Anforderungen dieser Etappe abgedeckt: Bewerbung später wieder
öffnen und weiterbearbeiten, einzelne Slots neu generieren, sichtbar machen,
welcher Text vom Modell und welcher von Hand stammt, und `render()` beliebig
wiederholen — die Texte stehen in der DB, nicht nur im exportierten HTML.

**Eine Bewerbung pro Stelle** (`UNIQUE(job_id)`). Mehrere Varianten wurden
nicht verlangt; falls sie später kommen, entfällt genau dieser Constraint.

### Job-Status wird bereinigt

`jobs.status` führt heute `new / selected / generated / rejected`. Sobald
`applications` existiert, ist `generated` eine zweite Wahrheit über denselben
Sachverhalt — und zwei Wahrheiten laufen auseinander.

Künftig: `jobs.status ∈ {new, selected, rejected}` — deine Entscheidung über
die Stelle. Ob eine Bewerbung existiert, beantwortet die `applications`-Tabelle.
`db.STATUSES` wird entsprechend reduziert.

*Migration:* Bestehende Zeilen mit `status='generated'` werden auf `'selected'`
gesetzt. Zum Zeitpunkt dieser Spec betrifft das **null Datensätze**.

### Schema-Versionierung

`PRAGMA user_version` wird als Zähler eingeführt. `db.connect()` liest ihn und
führt alle Migrationsschritte mit höherer Nummer der Reihe nach aus, danach
wird der Zähler auf den aktuellen Stand gesetzt. Diese Spec definiert
**Version 1**: die Status-Bereinigung (`generated` → `selected`). Die neuen
Tabellen brauchen den Mechanismus nicht (`IF NOT EXISTS` genügt), spätere
Spaltenänderungen für Etappe 3 und 4 schon. Eine Liste von Schritten plus
Schleife, kein Framework.

## Oberfläche

### Screen 1 — Stellen (`/`)

Drei Spalten: links Filter (Status, Ort, Volltextsuche in Titel und Firma),
Mitte die Stellenliste, rechts die vollständige Anzeige der markierten Stelle.

Aktionen: auswählen, aussortieren, Bewerbung erstellen, neue Suche starten
(`was` / `wo` / `umkreis`).

### Screen 2 — Bewerbung (`/bewerbung/<id>`)

Zwei Spalten. Links die Slot-Felder als einzeln bearbeitbare Textblöcke, jeder
mit Aktion „neu generieren" und einer Markierung, ob der Text vom Modell oder
von Hand stammt. Rechts die fertige Bewerbung als Live-Vorschau im `iframe`,
die nach jedem Speichern neu lädt.

Fußzeile: „Exportieren" → schreibt `out/<firma>/` samt Assets und die
CBKS-Kopie, wie das CLI es heute tut.

**Kein Profil-Screen.** `profile.yaml` bleibt eine Datei, die im Editor
gepflegt wird.

### Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | Stellen-Screen (volle Seite) |
| GET | `/jobs` | Listen-Fragment, Parameter `status`, `q`, `ort` |
| GET | `/jobs/{id}` | Detail-Fragment (Anzeigentext) |
| POST | `/jobs/{id}/pick` | Status `selected`, gibt Zeilen-Fragment zurück |
| POST | `/jobs/{id}/reject` | Status `rejected`, gibt Zeilen-Fragment zurück |
| POST | `/jobs/fetch` | Suche starten → Task-ID |
| POST | `/applications` | Bewerbung für `job_id` erzeugen → Task-ID |
| GET | `/bewerbung/{id}` | Bewerbungs-Screen (volle Seite) |
| PUT | `/applications/{id}/slots/{slot}` | Text speichern → Fragment |
| POST | `/applications/{id}/slots/{slot}/regenerate` | Slot neu erzeugen → Task-ID |
| GET | `/applications/{id}/preview` | Gerendertes HTML für den `iframe` |
| POST | `/applications/{id}/export` | Nach `out/` schreiben |
| GET | `/tasks/{task_id}` | Fortschritts-Fragment (HTMX-Polling) |

### Vorschau-Auslieferung

`/applications/{id}/preview` liefert das mit den aktuellen Slot-Werten
gefüllte HTML aus. Damit `styles.css` und `assets/` der Vorlage im `iframe`
auflösen, wird das Verzeichnis der Vorlage unter `/template-assets` als
`StaticFiles` gemountet und beim Ausliefern werden die relativen Pfade der
Vorlage darauf umgeschrieben. Die exportierte Datei in `out/` bleibt davon
unberührt — dort liegen die Assets wie bisher als Kopie daneben.

## Nebenläufigkeit

Alles, was das LLM oder die Arbeitsagentur anfasst, läuft in einem
`ThreadPoolExecutor` mit zwei Arbeitern. `tasks.py` hält je Task
`{id, status, meldung, ergebnis}` im Speicher; HTMX pollt `/tasks/{id}` im
Sekundentakt und ersetzt den Fortschrittsbalken durch das Ergebnis.

Kein Celery, kein Redis, keine Queue-Datenbank.

**Bewusster Preis:** Tasks überleben keinen Neustart der App. Wird während
eines Generierungslaufs neu gestartet, ist der Lauf verloren und muss neu
angestoßen werden. Für einen einzelnen Nutzer ist das die richtige Abwägung;
persistente Queues wären Infrastruktur ohne Gegenwert.

## Fehlerbehandlung

Jede Fehlerquelle endet in einer deutschen Meldung in der Oberfläche, nie in
einem Traceback — dasselbe Muster wie in Commit `f92bb39`.

| Fall | Verhalten |
|---|---|
| LLM nicht erreichbar / Timeout | Task gilt als fehlgeschlagen, Meldung im UI. **Bereits gespeicherte Slot-Texte bleiben unangetastet.** |
| Vorlage ohne `data-slot` / fehlerhaft | Meldung mit konkretem Slot-Problem statt Traceback |
| Arbeitsagentur nicht erreichbar | Suche schlägt fehl, bestehende Liste bleibt stehen |
| `profile.yaml` fehlt | Meldung mit Verweis auf `profile.yaml.example` |
| Slot-Validierung schlägt fehl | Ein Retry, dann Abbruch mit Log — Regel aus der Vorgänger-Spec |

Die eiserne Regel bleibt in Kraft: Das Modell formuliert nur aus Anzeige und
Vorlagentexten, es erfindet keine Fakten über die Firma. Die Validierung (alle
Slots vorhanden, keiner leer, Firmenname kommt vor) wandert unverändert nach
`applications.create`.

## Tests

- Die sechs bestehenden Test-Module laufen unverändert weiter. Sie sind
  gleichzeitig der Nachweis, dass das CLI den Umbau von `generate.py`
  unbeschadet übersteht.
- Neu: Unit-Tests für `applications.py` mit Fake-LLM-Client — das Muster steht
  bereits in `test_generate.py` und `test_llm.py`.
- Neu: Route-Tests über FastAPIs `TestClient`, gegen eine temporäre DB.
- Kein Netz und kein echtes Modell in Tests.
- **Keine Browser-E2E-Tests.** Für eine Ein-Nutzer-App übersteigt der
  Unterhaltsaufwand den Nutzen.

## Technik

- Neue Dependencies: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`.
  HTMX wird als einzelne Datei unter `web/static/` abgelegt, nicht per CDN
  geladen — die App muss offline laufen.
- Bestehende Dependencies unverändert.
- Python 3.13 via `uv`.

## Nicht-Ziele dieser Etappe

- PDF-Export, Anhänge-Paket, Mailtext (Etappe 3)
- Bewerbungs-Tracking: beworben am, Antwort, Absage, Nachfassen (Etappe 4)
- Automatischer Versand von Bewerbungen
- Mehrere Bewerbungsvarianten pro Stelle
- Profil- oder Vorlagen-Editor in der Oberfläche
- Benutzerverwaltung, Login, Mehrbenutzerbetrieb, Erreichbarkeit im Netz
- Persistente Task-Queue

## Etappenplan

| Etappe | Inhalt | Status |
|---|---|---|
| 1+2 | App-Gerüst, Sichten/Auswählen, Generieren/Redigieren | diese Spec |
| 3 | Export & Versand-Vorbereitung: PDF, Anhänge, Mailtext | später |
| 4 | Bewerbungs-Tracking | später |
