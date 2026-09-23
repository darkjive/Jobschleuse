/** ISO-Zeitstempel → 'heute' / 'vor 3 Tagen' / 'vor 5 Wochen'.
 * Entspricht der bisherigen `_alter`-Filterfunktion aus web/app.py. */
export function formatAlter(wert: string | null): string | null {
  if (!wert) return null;
  const zeitpunkt = new Date(wert);
  if (Number.isNaN(zeitpunkt.getTime())) return null;
  const tage = Math.floor((Date.now() - zeitpunkt.getTime()) / 86_400_000);
  if (tage <= 0) return "heute";
  if (tage === 1) return "gestern";
  if (tage < 14) return `vor ${tage} Tagen`;
  return `vor ${Math.floor(tage / 7)} Wochen`;
}

const EMPLOYER_LABEL: Record<string, string> = {
  zeitarbeit: "Zeitarbeit",
  vermittler: "Vermittler",
};

export function employerWarnung(employerKind: string | null): string | null {
  return employerKind ? (EMPLOYER_LABEL[employerKind] ?? null) : null;
}

/** Vollständige Anbieter-Bezeichnung fürs Detail — anders als die kurze
 * Warn-Badge oben (dort bleibt "arbeitgeber" ohne Badge, hier heißt es
 * ausgeschrieben "Arbeitgeber direkt"). */
const ANBIETER_LABEL: Record<string, string> = {
  zeitarbeit: "Zeitarbeit",
  vermittler: "private Arbeitsvermittlung",
};

export function formatAnbieter(employerKind: string | null): string | null {
  return employerKind ? (ANBIETER_LABEL[employerKind] ?? "Arbeitgeber direkt") : null;
}

/** Rohwerte der Quellen (API-Konstanten, ASCII-Umschreibungen) → Anzeige. */
const HOMEOFFICE_LABEL: Record<string, string> = {
  moeglich: "möglich",
  NACH_VEREINBARUNG: "nach Vereinbarung",
  ANGABE_IN_PROZENT: "anteilig",
};

export function formatHomeoffice(wert: string | null): string | null {
  return wert ? (HOMEOFFICE_LABEL[wert] ?? wert) : null;
}

export const STATUS_LABEL: Record<string, string> = {
  new: "neu",
  selected: "ausgewählt",
  rejected: "aussortiert",
};
