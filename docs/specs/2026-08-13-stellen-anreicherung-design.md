# Stellen-Anreicherung: mehr Fakten je Treffer, keine toten Anzeigen

**Datum:** 2026-08-13
**Status:** Entwurf, wartet auf Review
**Vorgänger:** `2026-08-03-bewerbungs-app-design.md`

## Anlass

Zwei Beobachtungen aus dem laufenden Betrieb:

1. Eine Stelle in der Liste (ID 557, „Full-Stack-Entwickler (m/w/d) –
   Schwerpunkt KI & Cloud", Consularis GmbH) war beim Anklicken bereits
   offline.
2. Die Listenansicht zeigt zu wenig, um Treffer ohne Klick zu beurteilen.
   Insbesondere fehlt, **woher** eine Anzeige stammt.

### Befund zu (1): Die Quelle liefert sauber, der Bestand altert

Alle 529 gespeicherten Stellen wurden gegen den Detail-Endpoint der
Bundesagentur geprüft:

| gescraped am | tot (HTTP 404) |
|---|---|
| 2026-07-08 | 220 / 461 |
| 2026-07-09 | 21 / 37 |
| 2026-08-03 | 8 / 25 |
| 2026-08-13 (Abfragetag) | 0 / 6 |

Frisch geholte Stellen sind ausnahmslos live; nach zehn Tagen sind rund 30 %
verschwunden, nach fünf Wochen fast die Hälfte. Die API liefert also keine
toten Einträge aus — die lokale Datenbank veraltet. Stelle 557 wurde am
03.08. geholt und ist seitdem offline gegangen.

Anzeigen mit `externeURL` (Weiterleitung auf Fremdportale) sterben schneller:
74 von 95 tot gegenüber 175 von 434 bei Anzeigen ohne.

Der Detail-Endpoint ist ein belastbarer Verfügbarkeitstest: HTTP 404 bedeutet
zuverlässig „nicht mehr vorhanden". Und er ist billig — 60 Abrufe mit 16
Threads brauchen 0,4 Sekunden, ein Rate-Limit war nicht feststellbar.

### Befund zu (2): Die Quelle gibt deutlich mehr her als genutzt

Erhoben an einer Stichprobe von 40 Stellen.

**Bereits in der Trefferliste enthalten, bisher verworfen:**
`stellenangebotsart` · `gehaltsspanneVon`/`gehaltsspanneBis`/`festgehalt` ·
`verguetungsangabe`/`artDerVerguetung` · `homeofficemoeglich`/`homeofficetyp` ·
`vertragsdauer`/`befristungInMonaten` · die fünf `arbeitszeit*`-Merkmale ·
`entfernung` · `aenderungsdatum` · `eintrittszeitraum.von` · `externeURL` ·
`stellenlokationen[].adresse.plz`

**Nur im Detail-Abruf, dort aber die wertvollsten Angaben:**

| Feld | Belegt | Bedeutung |
|---|---|---|
| `allianzpartnerName` | 40/40 | Herkunft der Anzeige („arbeitsagentur.de", „XING GmbH & Co. KG") |
| `istArbeitnehmerUeberlassung` | 22/40 | Zeitarbeit |
| `istPrivateArbeitsvermittlung` | 25/40 | private Arbeitsvermittlung statt Arbeitgeber |
| `stellenlokationen[].adresse` | 40/40 | Straße und Hausnummer (in der Trefferliste nicht enthalten) |
| `geforderterBildungsabschluss` | 5/40 | geforderter Abschluss |
| `arbeitgeberKundennummerHash` | 37/40 | erkennt denselben Arbeitgeber über mehrere Anzeigen |
| `istBetreut` | 40/40 | von der Agentur betreut |

### Befund zu (3): Die Suche kann serverseitig filtern

Die `pc/v6/jobs`-Schnittstelle akzeptiert weitere Parameter; alle wurden
gegen die Live-API geprüft. Beispiel „Frontend Entwickler" / Frankfurt /
50 km: 33 Treffer gesamt, mit `veroeffentlichtseit=7` noch 6.

`veroeffentlichtseit` (Tage) · `zeitarbeit` · `angebotsart` · `arbeitszeit` ·
`pav` · `homeoffice` · `befristung` · `schulbildung` · `branche` ·
`berufsfeld`

`veroeffentlichtseit` ist der direkteste Hebel gegen tote Stellen: was frisch
veröffentlicht ist, verschwindet kaum.

## Ziel

Nach dieser Etappe gilt:

- Eine Stelle in der Liste ist entweder verfügbar oder sichtbar als „nicht
  mehr verfügbar" markiert — kein Klick mehr ins Leere.
- Die Listenzeile beantwortet ohne Klick: Woher kommt die Anzeige? Steckt ein
  Vermittler oder Zeitarbeit dahinter? Homeoffice? Gehalt? Wie weit weg? Wie
  frisch?
- Die Suche kann bereits an der Quelle einengen, statt hinterher zu filtern.

## Nicht-Ziele

- Keine weitere Stellenquelle. Nur `arbeitsagentur`.
- Keine automatische Bewertung oder Sortierung nach Passung. Nur Fakten
  anzeigen, entscheiden tut der Mensch.
- Keine Historie: `gone_at` hält den Zeitpunkt fest, aber es wird kein
  Verlauf über Statuswechsel geführt.
- Kein Nachladen von Kontaktdaten oder Arbeitgeber-Websites.

## Randbedingungen

- Das CLI bleibt vollständig funktionsfähig, die Weboberfläche bleibt lokal.
- Bestehende Bewerbungen und Slots bleiben unangetastet; die Migration darf
  keine Zeile aus `applications` oder `application_slots` verlieren.
- Netzfehler dürfen einen Suchlauf nicht abbrechen. Eine Stelle, die wegen
  eines Verbindungsfehlers nicht angereichert werden kann, wird ohne
  Zusatzangaben gespeichert — sie gilt **nicht** als verschwunden. Nur HTTP
  404 markiert.

## Entwurf

### 1 · Datenmodell

`jobs` wächst um folgende Spalten, Schema-Migration auf `user_version = 2`
(alle `ALTER TABLE ... ADD COLUMN`, damit der Bestand erhalten bleibt):

| Spalte | Typ | Herkunft |
|---|---|---|
| `job_kind` | TEXT | `stellenangebotsart` |
| `employer_kind` | TEXT | abgeleitet, siehe unten |
| `source_partner` | TEXT | `allianzpartnerName` |
| `external_host` | TEXT | Hostname aus `externeURL` |
| `homeoffice` | TEXT | `homeofficetyp`, ersatzweise `homeofficemoeglich` |
| `salary` | TEXT | normalisiert, siehe unten |
| `contract` | TEXT | `vertragsdauer` + `befristungInMonaten` |
| `worktime` | TEXT | aus den `arbeitszeit*`-Merkmalen |
| `distance_km` | INTEGER | `entfernung` |
| `start_date` | TEXT | `eintrittszeitraum.von` |
| `changed_at` | TEXT | `aenderungsdatum` |
| `street` | TEXT | `stellenlokationen[0].adresse` |
| `plz` | TEXT | `stellenlokationen[0].adresse.plz` |
| `education` | TEXT | `geforderterBildungsabschluss` |
| `employer_hash` | TEXT | `arbeitgeberKundennummerHash` |
| `gone_at` | TEXT | Zeitpunkt der ersten 404-Feststellung, sonst NULL |

`JobItem` in `models.py` bekommt die gleichen Felder, alle optional mit
Vorgabe `None`, damit bestehende Aufrufe unverändert gültig bleiben.

**`employer_kind`** wird aus zwei Merkmalen abgeleitet:

| `istArbeitnehmerUeberlassung` | `istPrivateArbeitsvermittlung` | Ergebnis |
|---|---|---|
| `true` | beliebig | `zeitarbeit` |
| `false`/fehlt | `true` | `vermittler` |
| `false` | `false` | `arbeitgeber` |
| fehlt | fehlt | `None` |

Beide Merkmale fehlen bei rund 40 % der Anzeigen. In dem Fall bleibt das Feld
leer und es wird **kein** Kennzeichen angezeigt — eine Anzeige ohne Angabe
wird nicht als „Arbeitgeber" ausgegeben.

**`salary`** wird beim Parsen zu einer fertigen Zeichenkette normalisiert,
damit die Anzeige nicht rechnen muss:

- `gehaltsspanneVon` + `gehaltsspanneBis` bei `verguetungsangabe=STUNDENLOHN`
  → `"19,78–26,00 €/h"`
- nur `gehaltsspanneVon` → `"ab 19,78 €/h"`
- `festgehalt` → `"50.000 €/Jahr"`
- `verguetungsangabe=KEINE_ANGABEN` oder nichts belegt → `None`

**`worktime`**: `"Vollzeit"`, `"Teilzeit"` oder `"Vollzeit/Teilzeit"`, aus
`arbeitszeitVollzeit` und den vier Teilzeit-Merkmalen. Alle unbelegt → `None`.

### 2 · `sources/arbeitsagentur.py`

Drei Änderungen:

- **`parse_jobs`** liest die oben genannten Trefferlisten-Felder mit und
  normalisiert `salary`, `worktime`, `contract`, `external_host`.
- **`fetch_details(refnr) -> dict | None`** gibt künftig das vollständige
  Payload zurück und `None` bei HTTP 404, statt eine Ausnahme durchzureichen.
  Andere HTTP-Fehler und Netzfehler werden weiterhin geworfen.
  *Bruch für Aufrufer:* `applications.ensure_description` ruft das heute auf
  und erwartet einen String — die Stelle wird auf
  `payload.get("stellenangebotsBeschreibung")` umgestellt; ein `None`-Ergebnis
  bedeutet dort „Stelle ist weg", worauf mit der Kurzbeschreibung
  weitergearbeitet und `gone_at` gesetzt wird.
- **`enrich(items) -> list[JobItem]`** (neu): reichert die übergebenen
  Stellen über einen `ThreadPoolExecutor` mit 16 Arbeitern an. Ergebnis
  `None` (404) → die Stelle wird verworfen und gar nicht erst gespeichert.
  Netzfehler → Stelle bleibt drin, ohne Zusatzangaben.
  `fetch_jobs` ruft `enrich` am Ende auf.
- **`check_alive(refnrs) -> set[str]`** (neu): liefert parallel die Menge der
  Referenznummern, die 404 melden. Wird von der Frischeprüfung genutzt.
  Netzfehler zählen nicht als 404.

Die Beschreibung fällt beim Anreichern ohnehin ab und wird gleich in
`description_md` gespeichert. Damit greift `ensure_description` beim
Generieren im Regelfall nicht mehr — der Nachladeweg bleibt aber für
Altbestand und Netzfehlerfälle erhalten.

### 3 · Frischeprüfung bei jeder Suche

In `web/routes/jobs.py::suche_ausfuehren` und im entsprechenden CLI-Pfad
läuft nach dem Einfügen ein zweiter Schritt: alle Stellen mit
`gone_at IS NULL` und gesetzter `source_ref` gehen durch `check_alive`;
Treffer bekommen `gone_at = <jetzt>`.

Die Rückmeldung wird zu: `"37 Stellen geholt, 12 neu, 4 nicht mehr
verfügbar."`

Beim Bestand von ~500 offenen Stellen kostet das nach der Messung wenige
Sekunden. Falls der Bestand später deutlich wächst, ist die Prüfung auf die
Stellen mit `status != 'rejected'` einzugrenzen — jetzt noch nicht nötig.

### 4 · Suchformular und Suchparameter

`fetch_jobs` nimmt drei zusätzliche, optionale Parameter entgegen und reicht
sie an die API durch: `veroeffentlicht_seit` (Tage), `zeitarbeit` (bool),
`nur_arbeit` (bool → `angebotsart=1`). Nicht gesetzt heißt: Parameter wird
weggelassen, Verhalten bleibt wie bisher.

Das Suchformular der Weboberfläche bekommt entsprechend: ein Auswahlfeld
„Veröffentlicht seit" (egal / 7 / 14 / 30 Tage), ein Häkchen „Zeitarbeit
ausschließen", ein Häkchen „nur Arbeitsstellen (keine Ausbildung)".
Das CLI bekommt die gleichen Angaben als Optionen `--seit`, `--ohne-zeitarbeit`,
`--nur-arbeit`.

### 5 · Anzeige

**Listenzeile** (`_stellenliste.html`) bekommt unter Titel/Firma/Ort eine
Reihe kompakter Kennzeichen. Reihenfolge fest: erst Herkunft, dann
Warnzeichen, dann Pluspunkte, dann Eckdaten.

```
Full-Stack-Entwickler (m/w/d) — Consularis GmbH · Mannheim
[XING] [Vermittler] [Homeoffice] [unbefristet] [42 km] [vor 3 Tagen]
```

- Herkunft: `source_partner`, ersatzweise `external_host`. Immer sichtbar.
- Warnzeichen: `Zeitarbeit` / `Vermittler`, farblich abgesetzt. Nur wenn
  `employer_kind` belegt ist.
- `Ausbildung`, wenn `job_kind` nicht `ARBEIT` ist.
- Pluspunkte: Homeoffice, Gehalt — nur wenn belegt.
- Eckdaten: Entfernung, Alter (aus `changed_at`, ersatzweise `posted_at`).

Leere Felder erzeugen kein Kennzeichen; eine dünn belegte Anzeige bleibt
schmal statt eine Reihe von „unbekannt" zu zeigen.

**Nicht mehr verfügbar:** Zeilen mit gesetztem `gone_at` werden ausgegraut
und tragen das Kennzeichen `nicht mehr verfügbar`. Sie sind standardmäßig
ausgeblendet; ein eigenes Häkchen „auch verschwundene zeigen" blendet sie
ein. Bewusst kein zusätzlicher Wert im Statusfilter: Status (neu /
ausgewählt / aussortiert) und Verfügbarkeit sind unabhängig voneinander — eine
ausgewählte Stelle kann verschwinden, und das darf ihren Status nicht
überschreiben. Die Stelle bleibt vollständig erhalten, samt eventuell
erzeugter Bewerbung.

**Detailansicht** (`_stellendetail.html`) zeigt zusätzlich Straße und PLZ,
Eintrittstermin, geforderten Abschluss, Vertragsdauer, Arbeitszeit — als
Faktenliste über der Beschreibung. Ist `gone_at` gesetzt, steht ein deutlicher
Hinweis über der Seite.

### 6 · Altbestand

Die Frischeprüfung aus Abschnitt 3 wird zusätzlich als Befehl
`uv run jobs check` verfügbar gemacht — dieselbe Funktion, nur ohne
vorangehende Suche. Damit lässt sich der Altbestand einmal durchziehen, ohne
auf den nächsten Suchlauf zu warten. Nach heutigem Stand betrifft das 248 der
529 Stellen.

Die neuen Faktenspalten bleiben für den Altbestand leer — rückwirkendes
Anreichern lohnt nicht, weil die Hälfte davon ohnehin verschwunden ist. Neue
Suchen füllen sie.

## Prüfkriterien

1. **Migration:** Bestehende `jobs.db` öffnet sich ohne Fehler, alle 529
   Zeilen und alle Bewerbungen sind danach noch da, `user_version` ist 2.
2. **Anreicherung:** Eine Suche mit bekanntem Treffer liefert eine Stelle mit
   belegtem `source_partner` und — wo die Quelle es hergibt — `employer_kind`,
   `salary`, `homeoffice`.
3. **404 beim Holen:** Eine Stelle, deren Detail-Abruf 404 meldet, landet
   nicht in der Datenbank.
4. **Netzfehler beim Holen:** Wirft der Detail-Abruf einen Verbindungsfehler,
   wird die Stelle trotzdem gespeichert, ohne Zusatzangaben, und **ohne**
   `gone_at`.
5. **Frischeprüfung:** Eine vorhandene Stelle, deren Detail-Abruf 404 meldet,
   trägt nach dem nächsten Suchlauf ein `gone_at` und erscheint nicht mehr in
   der Standardliste. Die Rückmeldung nennt ihre Anzahl.
6. **Kein Falschalarm:** Eine lebende Stelle bekommt bei der Frischeprüfung
   kein `gone_at`.
7. **`employer_kind` bei fehlenden Merkmalen:** Fehlen beide Merkmale, bleibt
   das Feld leer und die Zeile zeigt kein Herkunftsart-Kennzeichen.
8. **Gehaltsformatierung:** Stundenlohnspanne, Festgehalt, offene Spanne und
   „keine Angabe" ergeben die vier oben beschriebenen Ausgaben.
9. **Suchparameter:** Ein Lauf mit `veroeffentlicht_seit=7` liefert
   nachweislich weniger Treffer als derselbe Lauf ohne.
10. **Bestehende Tests:** Die gesamte Testsuite läuft grün. Angepasst werden
    darf einzig, was die geänderte `fetch_details`-Signatur erzwingt
    (`test_arbeitsagentur.py`, `test_applications.py`); alle übrigen Tests
    bleiben unverändert.

Alle Tests gegen die API laufen mit aufgezeichneten Antworten, nicht gegen
das Netz.
