/** Anzeigenamen und Reihenfolge der `data-slot`-Blöcke. Unbekannte Slots
 * (neue Vorlagen) landen hinten, Name aus dem Schlüssel abgeleitet. */
const SLOTS: [name: string, label: string][] = [
  ["anschreiben_text", "Anschreiben"],
  ["einstieg", "Einstieg"],
  ["motivation", "Motivation"],
  ["adressat", "Adressat"],
  ["stellentitel", "Stellentitel"],
  ["rolle", "Rolle"],
  ["titel", "Titel"],
  ["tagline", "Tagline"],
  ["firma", "Firma"],
  ["ort", "Ort"],
  ["datum", "Datum"],
  ["monat_jahr", "Monat/Jahr"],
];

const LABEL = new Map(SLOTS);
const RANG = new Map(SLOTS.map(([name], index) => [name, index]));

export function slotLabel(name: string): string {
  const label = LABEL.get(name);
  if (label) return label;
  const text = name.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function slotSortierung(a: string, b: string): number {
  return (RANG.get(a) ?? SLOTS.length) - (RANG.get(b) ?? SLOTS.length) || a.localeCompare(b);
}
