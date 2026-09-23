import { useCallback, useEffect, useRef } from "react";

export type DebouncedCallback<Args extends unknown[]> = ((...args: Args) => void) & {
  /** Führt einen ausstehenden Aufruf sofort aus — z. B. vor einem Export
   * oder beim Verlassen der Seite, damit die letzte Eingabe nicht verfällt. */
  flush: () => void;
};

/** Verzögert Aufrufe um `delayMs` — nur der letzte Aufruf innerhalb des
 * Fensters feuert tatsächlich. Für Auto-Save beim Tippen. */
export function useDebouncedCallback<Args extends unknown[]>(
  callback: (...args: Args) => void,
  delayMs: number,
): DebouncedCallback<Args> {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Bleibt beim Unmount erhalten, damit ein späteres flush() ihn nachholen kann.
  const pendingRef = useRef<Args | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  // Stabile Identität: taugt als Effekt-Abhängigkeit und als Cleanup.
  const flush = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    const args = pendingRef.current;
    pendingRef.current = null;
    if (args) callbackRef.current(...args);
  }, []);

  const debounced = (...args: Args) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    pendingRef.current = args;
    timerRef.current = setTimeout(flush, delayMs);
  };
  debounced.flush = flush;
  return debounced;
}
