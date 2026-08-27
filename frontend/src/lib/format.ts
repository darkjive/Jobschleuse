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
