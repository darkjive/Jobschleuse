/** Laufende Slot-Speicherungen — der Export wartet auf sie, sonst druckt er
 * den Stand von vor der letzten Eingabe. */
const offen = new Set<Promise<unknown>>();

export function merkeSpeichern(promise: Promise<unknown>): void {
  offen.add(promise);
  promise.finally(() => offen.delete(promise)).catch(() => {});
}

export async function alleGespeichert(): Promise<void> {
  await Promise.allSettled([...offen]);
}
