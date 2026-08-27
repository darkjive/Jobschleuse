# Jobschleuse-Weboberfläche: Umbau auf React + shadcn/ui

**Datum:** 2026-08-27
**Status:** Entwurf, wartet auf Review
**Vorgänger:** `2026-08-03-bewerbungs-app-design.md` (führte FastAPI + HTMX ein)

## Anlass

Die Weboberfläche läuft seit `2026-08-03` auf FastAPI + Jinja2 + HTMX
(7 Templates, ~270 Zeilen, 305 Zeilen `app.css`). Ziel dieses Umbaus: die
Präsentationsschicht durch React + shadcn/ui ersetzen — inklusive vier
UX-Erweiterungen, die der HTMX-Ansatz nicht wirtschaftlich hergibt
(sortierbare Tabelle mit Bulk-Aktionen, Command-Palette, verschiebbare
Splitter, ein aufgewerteter Bewerbungs-Editor mit Auto-Save).

Das kehrt eine bestehende Architekturentscheidung um: `CLAUDE.md` hält aktuell
fest „Kein npm/Node, kein separates JS-Frontend". Dieser Umbau ersetzt das
bewusst — beide Dateien werden am Ende des Umbaus aktualisiert.

## Entscheidungen aus dem Brainstorming

1. **Voller React-Umbau**, nicht nur eine shadcn-Optik über Jinja. FastAPI
   wird reine JSON-API, HTMX entfällt vollständig.
2. **Build wird committed, ein Prozess.** `uv run jobs serve` bleibt der
   einzige Startbefehl (auch vom Handy). Vite baut nach
   `web/static/app/`, FastAPI liefert das statisch aus. Kein Node zur
   Laufzeit. Zum Entwickeln zusätzlich `npm run dev` (Vite-Dev-Server mit
   Proxy auf FastAPI, HMR).
3. **Port + UX-Überarbeitung** (größter geprüfter Umfang): gleiche
   Kernfunktionalität, plus vier neue Fähigkeiten (siehe unten).
4. **Alle vier Erweiterungen:** Data-Table mit Sortierung & Bulk-Aktionen,
   Command-Palette (Strg+K), verschiebbarer Splitter, aufgewerteter
   Bewerbungs-Editor.
5. **Farbwelt bleibt, Light-Mode kommt dazu.** Der Sand-Akzent (`#d4a574`)
   und Satoshi bleiben Identität; eine helle Variante wird ergänzt.
6. **Migration schichtweise:** API → Frontend → Abriss der alten Schicht.
   Zu jedem Zeitpunkt ein benutzbares Tool.

## Architektur & Auslieferung

```
bewerbungs-pipeline/
  frontend/                          neu — Vite + React + TypeScript
    src/
      components/ui/                 shadcn-Register (eigener Code, keine Dependency)
      features/stellen/               Data-Table, Filter, Detail, Command-Palette
      features/bewerbung/             Slot-Editor, Vorschau, Resizable-Splitter
      lib/api.ts                      typisierter Client gegen /api, TanStack-Query-Hooks
      lib/theme.ts                    next-themes-Setup
      styles/theme.css                Jobschleuse-Tokens als Tailwind-@theme
    components.json                   shadcn-Konfiguration (Stil: New York)
    package.json / vite.config.ts
  src/bewerbungs_pipeline/web/
    static/app/                       Vite-Build-Ziel, committed (dist)
    static/fonts/                     bleibt unverändert, Satoshi wird weiter von hier geladen
    templates/, static/{app.css,tokens.css,htmx.min.js}   entfallen in Phase 3
```

FastAPI registriert Reihenfolge-kritisch: zuerst `/api/*`, `/applications/{id}/preview`
und `/template-assets` als eigene Routen, danach erst den SPA-Fallback
(`StaticFiles(html=True)` mit `NotFoundError`-Abfangen auf `index.html`) —
sonst verschluckt der Fallback die echten Endpunkte. Dieses Layout
beschreibt den Endzustand nach Phase 3; in Phase 2 hängt die React-App
zusätzlich unter `/app`, ohne dass `/` schon umgeschaltet wird (siehe
Migrationsphasen unten).

`node_modules/` wird ignoriert, `static/app/` bewusst **nicht** — das
gebaute Bundle liegt im Repo, damit ein Klon ohne `npm install` startet.
Das erzeugt Diff-Rauschen bei UI-Commits; das ist der bewusst akzeptierte
Preis für „ein Startbefehl, kein Node zur Laufzeit".

## API-Schnitt

Alle 14 bestehenden HTML-Endpunkte werden zu JSON unter `/api/*`, mit
Pydantic-Response-Modellen (neu: `web/schemas.py`). Die Business-Logik
(`applications.py`, `db.py`, `tasks.py`) wird unverändert wiederverwendet —
nur die Route-Schicht ändert sich.

| Bisher (HTML) | Neu (JSON) | Änderung |
|---|---|---|
| `GET /jobs` | `GET /api/jobs` | + `sort`, `order` Parameter (Whitelist: `frische`, `distance_km`, `company`, `title`); + `limit` für die Command-Palette |
| `GET /jobs/{id}` | `GET /api/jobs/{id}` | unverändert in der Sache — Response enthält weiterhin die verknüpfte Bewerbungs-Id (falls vorhanden), damit das Frontend zwischen „Bewerbung erstellen" und „Bewerbung öffnen" unterscheiden kann |
| `POST /jobs/{id}/pick` | `POST /api/jobs/{id}/status` | Body `{status}`, ersetzt `pick`+`reject` einzeln |
| — | `POST /api/jobs/status` | **neu**: Bulk, Body `{ids: [...], status}`, eine Transaktion |
| `POST /jobs/fetch` | `POST /api/jobs/fetch` | liefert `{task_id}` statt Fragment |
| `GET /tasks/{id}` | `GET /api/tasks/{id}` | liefert `{status, meldung, ergebnis}`; `ziel`/`ziel_element`/`ziel_swap` samt Validierungs-Regex in `routes/tasks.py` entfallen ersatzlos — das Frontend pollt selbst und aktualisiert seinen eigenen State |
| `POST /applications` | `POST /api/applications` | liefert `{task_id}` |
| `GET /bewerbung/{id}` | `GET /api/applications/{id}` | inkl. zugehöriger `stelle` |
| `GET/PUT /applications/{id}/slots/{slot}` | `GET/PUT /api/applications/{id}/slots/{slot}` | unverändert in der Sache |
| `POST .../regenerate` | `POST /api/applications/{id}/slots/{slot}/regenerate` | liefert `{task_id}` |
| `POST /applications/{id}/export` | `POST /api/applications/{id}/export` | liefert `{task_id}` |
| `GET /applications/{id}/preview` | **bleibt** `GET /applications/{id}/preview` | unverändert — gerenderte Bewerbung fürs iframe, kein API-Konsument |

Die `_alter`-Filterfunktion (ISO-Zeitstempel → „vor 3 Tagen") wandert ins
Frontend (`Intl.RelativeTimeFormat`); die API liefert rohe ISO-Strings.

`db.suche_jobs` bekommt `sort`/`order` mit fester Spalten-Whitelist (kein
String-Interpolieren von Nutzereingaben in SQL).

## Frontend-Stack

- **Vite + React + TypeScript**, `shadcn` CLI (Stil „New York").
- **TanStack Query** für Server-State und Task-Polling — löst das
  `_fortschritt.html`-Nachladeschema ab: ein `useTask(id)`-Hook pollt via
  `refetchInterval`, bis `status !== "läuft"`.
- **TanStack Table** + shadcn `Table` für die Stellenliste: Sortierung
  (Frische, Entfernung, Firma, Titel), Spaltenwahl, Checkbox-Mehrfachauswahl
  mit Bulk-Leiste („N ausgewählt → Auswählen/Aussortieren"). Auf schmalen
  Bildschirmen klappt die Tabelle zu Karten um (eigene Kartenansicht,
  gespeist aus denselben Daten — keine zweite Abfrage).
- **shadcn `Command`** (cmdk) für die Palette: Stellen per Titel/Firma
  finden und öffnen, Status setzen, Suche starten, zum Bewerbungs-Screen
  springen. Nutzt `GET /api/jobs?q=&limit=20`.
- **shadcn `Resizable`** (react-resizable-panels) zwischen Stellenliste und
  Detail sowie im Bewerbungs-Screen zwischen Slot-Editor und Vorschau-iframe.
  Verhältnis pro Screen in `localStorage`.
- **React Router**: `/` (Stellen) und `/bewerbung/:id`.
- **react-hook-form + zod** für Suchformular und Slot-Editor-Validierung.
- Filter-/Sortierzustand liegt in URL-Suchparametern (`?status=new&sort=…`),
  damit Links wie bisher teilbar bleiben.
- **Bewerbungs-Editor:** Slots als einklappbare `Card`s, Auto-Save debounced
  (800 ms) über das bestehende `PUT`, sichtbarer Speicherstatus
  („gespeichert" / „speichert …"), „Neu erzeugen" bleibt expliziter Klick
  (kostet einen LLM-Call). Die Vorschau lädt gezielt neu (iframe-Reload),
  sobald ein Slot-Save oder eine Regenerierung abgeschlossen ist — ersetzt
  den `hx-on::after-swap`-Bubbling-Trick aus `bewerbung.html`.
- **Sonner** für Toasts (Suche gestartet/fertig, Export fertig, Fehler) —
  ersetzt die `#fortschritt`/`#exportmeldung`-Divs.
- **Skeleton** für Ladezustände (Stellenliste, Detail) statt „Liste wird
  geladen …".

## Theme

Tailwind v4, CSS-first (`@theme` in `styles/theme.css`). Bestehende
Dark-Werte wandern 1:1 auf shadcn-Tokennamen:

| Jobschleuse (`tokens.css`) | shadcn-Token |
|---|---|
| `--bg` `#0d1017` | `--background` |
| `--text` `#e6e1d8` | `--foreground` |
| `--bg-elevated` `#161b22` | `--card` |
| `--accent` `#d4a574` | `--primary` |
| `--text-dim` `#9a948a` | `--muted-foreground` |
| `--border` / `--border-strong` | `--border` / `--ring` |

Satoshi Variable bleibt als `--font-sans`, geladen aus
`web/static/fonts/` (unverändert). Für Light schlägt diese Spec eine
wärmere, keine reinweiße Variante vor (heller Warmgrau-Hintergrund, Akzent
leicht abgedunkelt für AA-Kontrast auf Hell) — endgültige Werte werden beim
Bauen im Browser abgeglichen, nicht blind aus der Spec übernommen.
Umschaltung über `next-themes`, Persistenz in `localStorage`, Default folgt
`prefers-color-scheme`.

## Migrationsphasen

**Phase 1 — API-Schicht.** Alle `/api/*`-Endpunkte + `web/schemas.py`
entstehen neben den bestehenden HTML-Routen. Bestehende 733 Zeilen
Web-Tests werden auf JSON-Assertions umgeschrieben (gleiche Fälle, gleiche
Fixtures). *Fertig, wenn:* alle Tests grün, HTML-UI unter `/` weiterhin
unverändert benutzbar.

**Phase 2 — Frontend.** React-App entsteht unter `frontend/`, erreichbar
unter `/app` (FastAPI mountet `static/app/` zusätzlich zur bestehenden
Jinja-Route). Gegen die in Phase 1 bewiesene API gebaut, keine Mocks.
*Fertig, wenn:* kompletter Pfad Suche → Filtern/Sortieren →
Auswählen/Bulk → Bewerbung erzeugen → Slot bearbeiten → Export einmal live
im Browser durchgespielt ist, inklusive aller vier neuen Features.

**Phase 3 — Abriss.** `/` liefert jetzt die React-App aus. Danach löschen:
`templates/`, `static/{app.css,tokens.css,htmx.min.js}`, die alten
HTML-Routen in `routes/jobs.py` / `routes/applications.py` / `routes/tasks.py`,
der `ziel`/`ziel_element`/`ziel_swap`-Code. README-Abschnitt „Weboberfläche"
und `CLAUDE.md` (Abschnitt „Web") werden auf den neuen Stack aktualisiert;
`AGENTS.md`/`CLAUDE.md` (global) verlieren keine Gültigkeit, da sie
projektübergreifend sind.

## Teststrategie

- **Backend:** bestehende `tests/test_web_*.py` (733 Zeilen) werden
  umgeschrieben, nicht neu geschrieben — gleiche Fälle, `response.json()`
  statt HTML-String-Prüfung. Kein Verlust an Abdeckung.
- **Frontend:** Vitest + React Testing Library für die Logik mit echtem
  Fehlerpotenzial: Debounce des Auto-Save, Sortier-/Filterlogik der
  Data-Table, der Task-Polling-Hook (Zustandsübergänge läuft→fertig→fehler).
  Keine flächendeckenden Snapshot- oder E2E-Tests — die Kombination aus
  TypeScript, TanStack Query und den o. g. gezielten Tests deckt das
  Nötige ab.
- **Manuell:** vor Abschluss jeder Phase der komplette Pfad Suche → Auswahl
  → Generieren → Export einmal live im Browser (Playwright-MCP oder
  händisch), wie in `CLAUDE.md` (global) für UI-Änderungen gefordert.

## Offene, bewusst nicht vorentschiedene Punkte

- Exakte Light-Mode-Farbwerte (siehe Theme-Abschnitt) — werden beim Bauen
  im Browser abgeglichen.
- Ob die Kartenansicht der Data-Table auf Mobile eigene Spalten-Priorität
  bekommt oder alle Spalten zeigt — Detailentscheidung der Implementierung.
