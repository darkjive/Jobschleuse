import { useEffect, useRef } from "react";

/** Verzögert Aufrufe um `delayMs` — nur der letzte Aufruf innerhalb des
 * Fensters feuert tatsächlich. Für Auto-Save beim Tippen. */
export function useDebouncedCallback<Args extends unknown[]>(
  callback: (...args: Args) => void,
  delayMs: number,
): (...args: Args) => void {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  return (...args: Args) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => callbackRef.current(...args), delayMs);
  };
}
