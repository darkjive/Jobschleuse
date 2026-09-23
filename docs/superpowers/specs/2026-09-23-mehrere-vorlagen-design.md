# Mehrere Vorlagen — Design

Datum: 2026-09-23 · Status: Entwurf zur Abnahme · Teilprojekt 1 von 3

## Kontext & Ziel

Heute gibt es genau eine Bewerbungsvorlage, global über `TEMPLATE_PATH`
(`templates/bewerbung.html` + `templates/styles.css` + `templates/assets/`).
Langfristiges Ziel: Nutzer kippen Beispiel-Bewerbungen (PDF, DOCX, LaTeX) ein
und die App übernimmt das Layout automatisch. Das zerfällt in drei
Teilprojekte:

1. **Mehrere Vorlagen** (dieses Dokument): verwalten, pro Bewerbung wählen,
   fertige HTML-Vorlagen als ZIP hochladen.
2. **Import-Konverter**: PDF/DOCX/LaTeX → PDF → Layout-Extraktion (PyMuPDF)
   → HTML/CSS; Text-LLM ordnet Textblöcke Slots zu; Korrektur-UI. Erzeugt
   eine Vorlage im Format dieses Dokuments.
3. **LLM-Einstellungen in der Web-UI** statt `.env` (Endpoint, Key, Modell,
   Verbindungstest).

Rahmenbedingungen (vom User festgelegt):

- **Eine Instanz pro User** (lokal oder Docker). Keine Accounts, keine
  Mandantentrennung. Einzelbetrieb-Annahmen (SQLite, In-Memory-Tasks) bleiben.
- Die App soll von **anderen Personen** betrieben werden können → keine
  persönlichen Daten im Repo, Uploads werden validiert.
- Vorlagenwechsel bei bestehenden Bewerbungen ist möglich, ohne manuelle
  Änderungen zu verlieren.

Nebenbefund, der hier mitbehoben wird: `applications.template_path` wird
gespeichert, aber `render()`, `export()` und `regenerate_slot()` nutzen immer
`cfg.template_path` — ein Wechsel der globalen Vorlage rendert alte
Bewerbungen still mit der neuen.

## Ablage

### Vorlagen

Nutzervorlagen liegen in `data/vorlagen/<slug>/` (unter `data/`, damit
gitignored):

```
data/vorlagen/<slug>/
  vorlage.yaml   # name, erstellt (ISO-Datum), herkunft
  index.html     # enthält data-slot-Markierungen
  styles.css     # optional
  assets/        # optional: Fonts, Deko-Grafiken
```

- `slug`: aus dem Namen erzeugt (bestehendes `slugify`), bei Kollision
  Suffix `-2`, `-3`, … Der Slug ist **unveränderlich** — Bewerbungen
  verweisen darauf. Umbenennen ändert nur `name` in `vorlage.yaml`.
- `herkunft`: `mitgeliefert` | `migriert` | `zip` | `kopie` (TP 2 ergänzt
  `import`).
- Die Vorlage verweist relativ auf `styles.css` und `assets/…` — wie heute.

### Mitgelieferte Beispielvorlage

Das Repo liefert `templates/beispiel/` im selben Format, aufgebaut aus dem
Layout von `bewerbung.html`/`styles.css`, aber mit neutralen Platzhalterdaten
(Max Mustermann, Musterstraße …). Die Fonts aus `templates/assets/fonts/`
ziehen in `templates/beispiel/assets/fonts/`.

Ist `data/vorlagen/` beim Start leer (und gibt es nichts zu migrieren), wird
`templates/beispiel/` nach `data/vorlagen/beispiel/` kopiert und Standard.

`templates/beispiel.html` ist danach nirgends mehr referenziert (war nur
Default von `TEMPLATE_PATH`) und wird entfernt.
`templates/beispiel-org.html` ist offenbar ein versehentlich eingecheckter,
unverwandter Seitenexport — wird im Rahmen dieses Projekts nicht angefasst,
nur gemeldet.

### Persönliche Dateien

Portrait und Unterschrift gehören dem Nutzer, nicht einer Vorlage:

- Ablage: `data/eigen/portrait.jpg`, `data/eigen/signature.png`.
- Vorlagen referenzieren sie unter dem festen relativen Pfad
  `eigen/portrait.jpg` bzw. `eigen/signature.png`.
- Vorschau: `eigen/` wird unterhalb jedes Vorlagen-Mounts ausgeliefert
  (Details unter Web).
- Export: `data/eigen/` wird nach `out/<firma>/eigen/` kopiert.
- Der Profil-Upload (`routes/api_profile.py`) schreibt nach `data/eigen/`
  statt in den Vorlagen-Ordner.

## Datenmodell

- Tabelle `applications`: neue Spalte `vorlage TEXT` (Slug). `template_path`
  bleibt als Altspalte stehen (SQLite-`DROP COLUMN` vermeiden), wird aber
  nicht mehr gelesen oder geschrieben.
- Neue Tabelle `einstellungen (schluessel TEXT PRIMARY KEY, wert TEXT NOT
  NULL)`. Schlüssel `standard_vorlage`. TP 3 nutzt dieselbe Tabelle.
- `application_slots` bleibt unverändert. Slots, die die aktive Vorlage nicht
  (mehr) enthält, bleiben als Zeilen erhalten und werden beim Lesen
  ausgefiltert (siehe Vorlagenwechsel).

## Migration (einmalig, idempotent, beim Start)

Läuft in `db.py`-Schemaschritten bzw. einem `vorlagen.migriere(cfg, conn)`,
das `serve` und jeder CLI-Befehl vor der Arbeit aufrufen:

1. Spalte `vorlage` und Tabelle `einstellungen` anlegen, falls fehlend.
2. Existiert `templates/bewerbung.html` und noch kein
   `data/vorlagen/bewerbung/`:
   - `bewerbung.html` → `data/vorlagen/bewerbung/index.html`,
     `templates/styles.css` → `…/styles.css`,
     `templates/assets/` → `…/assets/` (ohne portrait/signature),
     `vorlage.yaml` mit `herkunft: migriert`.
   - `templates/assets/portrait.jpg` und `signature.png` → `data/eigen/`
     (kopieren, nicht verschieben — die Originale sind gitignored und
     bleiben als Rückfallebene liegen).
   - In der neuen `index.html`: `assets/portrait.jpg` →
     `eigen/portrait.jpg`, `assets/signature.png` → `eigen/signature.png`.
   - `standard_vorlage = 'bewerbung'`.
3. Alle `applications` mit `vorlage IS NULL` → `vorlage = standard_vorlage`.
4. Ist danach `data/vorlagen/` leer: Beispielvorlage kopieren (siehe oben).

Zweiter Lauf ändert nichts (Test).

## Konfiguration

- `TEMPLATE_PATH` und `Config.template_path` entfallen.
- Neu: `Config.vorlagen_dir` (Default `data/vorlagen`), `Config.eigen_dir`
  (Default `data/eigen`), per Env überschreibbar (`VORLAGEN_DIR`,
  `EIGEN_DIR`) — wichtig für Tests und Docker-Volumes.
- `.env.example` und README werden angepasst.

## Modul `vorlagen.py`

Gemeinsame Logik für CLI und Web. Fehler als `VorlagenError`.

| Funktion | Verhalten |
|---|---|
| `liste(cfg, conn)` | alle Vorlagen: slug, name, herkunft, erstellt, slots, ist_standard, nutzungen (Anzahl Bewerbungen) |
| `lade(cfg, slug)` | `(html, slots)`; validiert mit `extract_slots`; Fehler bei fehlender Vorlage, kaputtem HTML oder null Slots |
| `ordner(cfg, slug)` | Pfad; prüft, dass slug nur `[a-z0-9-]` enthält (kein Traversal über die API) |
| `standard(conn)` / `setze_standard(cfg, conn, slug)` | lesen/setzen; Setzen prüft, dass die Vorlage existiert |
| `importiere_zip(cfg, datei, name)` | siehe ZIP-Validierung; gibt slug + Warnungen zurück |
| `dupliziere(cfg, slug, name)` | Ordnerkopie, neues `vorlage.yaml` (`herkunft: kopie`) |
| `umbenennen(cfg, slug, name)` | nur `vorlage.yaml` |
| `loesche(cfg, conn, slug)` | verweigert bei Nutzungen > 0 („wird von 3 Bewerbungen genutzt“) und wenn Standard |
| `migriere(cfg, conn)` | siehe Migration |

`applications.py`:

- `_template_slots(cfg)` wird durch `vorlagen.lade(cfg, slug)` ersetzt.
- `create(conn, job_id, cfg, client, vorlage=None)`: `None` → Standard.
- `render`, `export`, `regenerate_slot` nutzen `application["vorlage"]`.
- `export` kopiert `styles.css`/`assets/` aus dem Vorlagen-Ordner und
  `data/eigen/` nach `out/<firma>/eigen/`.
- `get`/`_row_to_application` liefert `vorlage` und filtert `slots` auf die
  Slots der aktiven Vorlage.
- Neu `wechsle_vorlage(conn, app_id, slug, cfg, client)`:
  1. Vorlage laden (validiert).
  2. `vorlage` der Bewerbung setzen.
  3. Für jeden Slot der neuen Vorlage ohne vorhandene Zeile: Wert per
     `generate_slot_texts` erzeugen (Aufruf nur mit den fehlenden Slots und
     deren Beispieltexten aus der neuen Vorlage; keine Signaturänderung) und mit `source = 'llm'` einfügen.
  4. Vorhandene Zeilen — egal ob `llm` oder `manuell` — bleiben unverändert.
  Schlägt Schritt 3 fehl, wird nichts committet (Transaktion), die Bewerbung
  behält ihre alte Vorlage.

## ZIP-Validierung (`importiere_zip`)

Uploads sind fremde Dateien, die im Vorschau-iframe und im Export-Chromium
laufen. Regeln:

- Max. 10 MB komprimiert, max. 30 MB entpackt, max. 200 Einträge.
- Einträge mit absoluten Pfaden, `..`-Segmenten oder Symlink-Attribut → Abbruch.
- Erlaubte Endungen: `.html`, `.htm`, `.css`, `.png`, `.jpg`, `.jpeg`, `.gif`,
  `.svg`, `.webp`, `.woff`, `.woff2`, `.ttf`, `.otf`. Andere Dateien →
  Abbruch mit Liste. (`__MACOSX/` und `.DS_Store` werden stillschweigend
  ignoriert.)
- `index.html` im Wurzelverzeichnis oder in genau einem gemeinsamen
  Unterordner (der dann als Wurzel gilt). Fehlt sie oder gibt es mehrere
  Kandidaten → Abbruch.
- HTML: kein `<script>`, keine `on*`-Attribute, keine `javascript:`-URLs
  (auch nicht in SVGs). Prüfung per `html.parser` (wie `slots.py`), kein Regex.
- Mindestens ein `data-slot` (via `extract_slots`).
- Relative Verweise ins Leere → **Warnung**, kein Abbruch (Wiederverwendung
  von `_pruefe_verweise`, umgebaut zu einer Funktion, die die Liste
  zurückgibt). Verweise auf `eigen/…` gelten als vorhanden.
- Entpacken in einen Temp-Ordner unter `data/vorlagen/.tmp-*`, erst nach
  erfolgreicher Prüfung per `rename` an den Zielort.

Name: Parameter, sonst ZIP-Dateiname ohne Endung.

## Web

### API (`routes/api_vorlagen.py`)

```
GET    /api/vorlagen                       Liste (Felder wie vorlagen.liste)
POST   /api/vorlagen                       multipart: datei (ZIP), name?  → {slug, warnungen}
POST   /api/vorlagen/{slug}/kopie          {name}                        → {slug}
PATCH  /api/vorlagen/{slug}                {name?, standard?: true}
DELETE /api/vorlagen/{slug}                409 bei Nutzung/Standard
POST   /api/applications/{id}/vorlage      {vorlage}                     → {task_id}
POST   /api/jobs/{id}/application          bestehend; optional {vorlage}
```

Fehler → 404 (unbekannt), 409 (in Benutzung/Standard), 422 (Validierung,
mit Meldung). Der Vorlagenwechsel läuft als Background-Task über `tasks.py`
(LLM-Aufruf), Status-Polling wie bei der Generierung.

### Serverseitige Vorschauen

- `GET /vorlagen/{slug}/vorschau`: `index.html` unverändert (Beispieltexte
  der Vorlage = Slotinhalte), mit `<base href="/vorlagen-assets/{slug}/">`.
- `GET /applications/{id}/preview`: wie heute, aber mit der Vorlage der
  Bewerbung und demselben `<base>`-Mechanismus.
- Statische Auslieferung: `/vorlagen-assets/{slug}/…` aus
  `data/vorlagen/{slug}/`; darunter `…/eigen/…` aus `data/eigen/`
  (eigene kleine Route, damit relative `eigen/`-Verweise in jeder Vorlage
  funktionieren). Der bisherige Mount `/template-assets` entfällt.
- Beide Vorschauen senden `Content-Security-Policy: script-src 'none'`
  als zweite Verteidigungslinie.

### Frontend

- Neue Seite **Vorlagen** (Navigation neben Stellen/Profil):
  - Karten mit skalierter iframe-Vorschau (`/vorlagen/{slug}/vorschau`),
    Name, Badge „Standard“, Anzahl Nutzungen.
  - Kartenmenü: Als Standard setzen, Umbenennen, Duplizieren, Löschen
    (deaktiviert mit Tooltip, wenn in Benutzung/Standard).
  - Button „ZIP hochladen“ → Dialog mit Datei + optionalem Namen; zeigt
    Validierungsfehler bzw. Warnungen (fehlende Dateien) an.
- Bewerbungsansicht: Dropdown **Vorlage**. Wechsel startet den Task,
  zeigt Fortschritt (bestehendes `useTask`), danach Neuladen von Slots und
  Vorschau. Slot-Liste zeigt nur Slots der aktiven Vorlage.
- „Bewerbung erzeugen“: nutzt den Standard; kein zusätzlicher Dialog.
- Profilseite: Upload-Pfade zeigen auf `/eigen/…`.
- `frontend/dist/` wird neu gebaut und committed.

## CLI

```
jobs vorlagen list
jobs vorlagen standard <slug>
jobs vorlagen import <datei.zip> [--name NAME]
jobs vorlagen kopie <slug> <name>
jobs vorlagen umbenennen <slug> <name>
jobs vorlagen loeschen <slug>
jobs generate <job-id> [--vorlage SLUG]
jobs vorlage-wechseln <application-id> <slug>
```

Ausgabe und Fehler im Stil der bestehenden Befehle.

## Fehlerbehandlung

- Vorlage einer Bewerbung wurde außerhalb der App gelöscht → Render/Export
  melden „Vorlage ‚x‘ fehlt — andere Vorlage wählen“; Web zeigt das im
  Vorschaubereich statt eines 500ers, Dropdown bleibt bedienbar.
- Vorlage enthält nach Bearbeitung im Dateisystem keine Slots mehr oder
  ist kaputt → `VorlagenError`, in Liste als „fehlerhaft“ markiert statt die
  ganze Liste scheitern zu lassen.
- Standard zeigt auf nicht existierende Vorlage → erste vorhandene Vorlage
  wird Standard, Warnung im Log.

## Tests

Bestehende Tests, die `template_path=` setzen, werden auf
`vorlagen_dir`/`eigen_dir` mit Fixture-Vorlagenordnern umgestellt.

- `test_vorlagen.py`: liste/standard/umbenennen/dupliziere; Löschschutz
  (Nutzung, Standard); ungültiger Slug; kaputte Vorlage in Liste markiert.
- ZIP-Validierung mit erzeugten Fixture-ZIPs: gültig; Unterordner als
  Wurzel; `../`-Pfad; absoluter Pfad; Symlink; `.exe`; `<script>`;
  `onload=`; `javascript:`-Link; SVG mit Script; keine Slots; keine
  `index.html`; zwei `index.html`; zu groß; fehlendes Asset → Warnung.
- Migration: Altzustand (templates/bewerbung.html + assets, Bewerbung mit
  `vorlage NULL`) → Neuzustand; Verweise umgeschrieben; zweiter Lauf
  idempotent; leerer Zustand → Beispielvorlage.
- `wechsle_vorlage`: gemeinsame Slots inkl. `manuell` unverändert, neue
  per Fake-Client erzeugt, alte Zeilen bleiben in der DB und tauchen beim
  Zurückwechseln wieder auf; LLM-Fehler → Rollback.
- Render/Export/Regenerate nutzen die Vorlage der Bewerbung, nicht den
  Standard; Export kopiert `eigen/`.
- API-Tests für alle neuen Endpunkte inkl. 404/409/422; CSP-Header der
  Vorschauen; Traversal über `{slug}` abgewiesen.
- CLI-Smoke-Tests für `vorlagen list/import/standard`.
- Vitest nur für echte Logik (Task-Flow beim Vorlagenwechsel), nicht für
  jede Karte.

## Nicht Teil dieses Projekts

- PDF/DOCX/LaTeX/Screenshot-Import (TP 2).
- LLM-Konfiguration in der UI (TP 3).
- Vorlagen im Browser bearbeiten.
- Chromium-gerenderte Thumbnails.
- Mehrbenutzerbetrieb.
