import type { Layout, LayoutChangedMeta } from "react-resizable-panels";

/** Merkt sich das Verhältnis eines ResizablePanelGroup-Layouts in
 * localStorage, geschlüsselt nach Panel-`id` — pro Screen ein eigener Key. */
export function usePersistedLayout(key: string) {
  const defaultLayout = ((): Layout | undefined => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as Layout) : undefined;
    } catch {
      return undefined;
    }
  })();

  function onLayoutChanged(layout: Layout, meta: LayoutChangedMeta) {
    if (!meta.isUserInteraction) return;
    try {
      localStorage.setItem(key, JSON.stringify(layout));
    } catch {
      // localStorage kann fehlschlagen (privates Fenster, voll) — das
      // Layout bleibt dann für diese Sitzung einfach unpersistiert.
    }
  }

  return { defaultLayout, onLayoutChanged };
}
