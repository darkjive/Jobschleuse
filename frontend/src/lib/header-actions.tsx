import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

const SlotContext = createContext<HTMLDivElement | null>(null);
const SetSlotContext = createContext<((node: HTMLDivElement | null) => void) | null>(null);

/** Muss den gesamten Layout-Baum umschließen (Header UND `<Outlet/>`) —
 * nur dann sehen Routen denselben Context-Wert wie `HeaderActionsOutlet`
 * im Header. Ersatz für Jinjas `{% block kopfaktionen %}`. */
export function HeaderActionsProvider({ children }: { children: ReactNode }) {
  const [node, setNode] = useState<HTMLDivElement | null>(null);
  return (
    <SlotContext.Provider value={node}>
      <SetSlotContext.Provider value={setNode}>{children}</SetSlotContext.Provider>
    </SlotContext.Provider>
  );
}

/** Rendert im Header den Zielort für Seiten-spezifische Kopf-Aktionen. */
export function HeaderActionsOutlet(props: React.HTMLAttributes<HTMLDivElement>) {
  const setNode = useContext(SetSlotContext);
  return <div ref={setNode ?? undefined} {...props} />;
}

/** Portalt `content` in den `HeaderActionsOutlet` — der Rückgabewert muss
 * irgendwo im JSX der aufrufenden Seite gerendert werden (Portale erscheinen
 * unabhängig von ihrer Stelle im Baum am Zielknoten). */
export function useSetHeaderActions(content: ReactNode): ReactNode {
  const slot = useContext(SlotContext);
  return slot ? createPortal(content, slot) : null;
}
