import { useEffect, useState } from "react";

/** Für Radix-Portale (Sheet/Dialog) reicht CSS wie `md:hidden` nicht —
 * ihr Inhalt rendert in einen Portal an document.body und ignoriert damit
 * die display:none-Regel des Wrapper-Elements. Hier braucht es eine echte
 * JS-Prüfung, um z. B. `open` gar nicht erst auf true zu setzen. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
