import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { TaskOut } from "@/types/api";

/** Solange ein Task läuft, alle 1000ms neu abfragen — sonst nicht mehr. */
export function taskRefetchIntervalMs(task: TaskOut | undefined): number | false {
  if (!task || task.status === "läuft") return 1000;
  return false;
}

export function useTask(taskId: string | null) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api.tasks.status(taskId as string),
    enabled: taskId !== null,
    refetchInterval: (query) => taskRefetchIntervalMs(query.state.data),
  });
}
