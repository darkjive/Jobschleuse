import { useEffect, useRef } from "react";
import { useTask } from "@/hooks/useTask";
import type { TaskOut } from "@/types/api";

interface Handlers {
  onFertig?: (task: TaskOut) => void;
  onFehler?: (task: TaskOut) => void;
}

/** Pollt einen Hintergrund-Task (Suche, Bewerbung erzeugen, Export, Slot neu
 * erzeugen laufen alle darüber) und ruft `onFertig`/`onFehler` auf, sobald er
 * das jeweilige Ergebnis erreicht. Der Aufrufer setzt `taskId` üblicherweise
 * darin auf `null` zurück, das beendet das Polling. */
export function useTaskErgebnis(taskId: string | null, handlers: Handlers): TaskOut | undefined {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;
  const { data: task } = useTask(taskId);

  useEffect(() => {
    if (!task) return;
    if (task.status === "fertig") handlersRef.current.onFertig?.(task);
    else if (task.status === "fehler") handlersRef.current.onFehler?.(task);
  }, [task]);

  return task;
}
