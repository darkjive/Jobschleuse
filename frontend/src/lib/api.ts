import type {
  ApplicationDetail,
  FetchRequest,
  JobListItem,
  JobOut,
  JobsQuery,
  SlotOut,
  Status,
  TaskOut,
  TaskRef,
} from "@/types/api";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function wirfBeiFehler(antwort: Response): Promise<void> {
  if (antwort.ok) return;
  const body = await antwort.json().catch(() => null);
  const detail = body?.detail;
  const meldung =
    typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((d) => d.msg).join(", ")
        : antwort.statusText;
  throw new ApiError(antwort.status, meldung);
}

async function anfrage<T>(pfad: string, init?: RequestInit): Promise<T> {
  const antwort = await fetch(pfad, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  await wirfBeiFehler(antwort);
  return antwort.json() as Promise<T>;
}

async function hochladen<T>(pfad: string, datei: File): Promise<T> {
  const formular = new FormData();
  formular.append("datei", datei);
  const antwort = await fetch(pfad, { method: "POST", body: formular });
  await wirfBeiFehler(antwort);
  return antwort.json() as Promise<T>;
}

function query(params: object): string {
  const suche = new URLSearchParams();
  const eintraege = Object.entries(params) as [
    string,
    string | number | boolean | undefined,
  ][];
  for (const [key, value] of eintraege) {
    if (value !== undefined && value !== "") suche.set(key, String(value));
  }
  const text = suche.toString();
  return text ? `?${text}` : "";
}

export const api = {
  jobs: {
    liste: (params: JobsQuery = {}) =>
      anfrage<JobListItem[]>(`/api/jobs${query(params)}`),
    anzahl: (params: Pick<JobsQuery, "q" | "ort" | "verschwunden"> = {}) =>
      anfrage<Record<Status, number>>(`/api/jobs/anzahl${query(params)}`),
    detail: (id: number) => anfrage<JobOut>(`/api/jobs/${id}`),
    statusSetzen: (id: number, status: Status) =>
      anfrage<JobOut>(`/api/jobs/${id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      }),
    statusBulk: (ids: number[], status: Status) =>
      anfrage<{ aktualisiert: number }>(`/api/jobs/status`, {
        method: "POST",
        body: JSON.stringify({ ids, status }),
      }),
    suchen: (body: FetchRequest) =>
      anfrage<TaskRef>(`/api/jobs/fetch`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
  tasks: {
    status: (id: string) => anfrage<TaskOut>(`/api/tasks/${id}`),
  },
  applications: {
    erzeugen: (jobId: number) =>
      anfrage<TaskRef>(`/api/applications`, {
        method: "POST",
        body: JSON.stringify({ job_id: jobId }),
      }),
    detail: (id: number) => anfrage<ApplicationDetail>(`/api/applications/${id}`),
    slotLesen: (appId: number, slot: string) =>
      anfrage<SlotOut>(`/api/applications/${appId}/slots/${slot}`),
    slotSpeichern: (appId: number, slot: string, value: string) =>
      anfrage<SlotOut>(`/api/applications/${appId}/slots/${slot}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    slotRegenerieren: (appId: number, slot: string) =>
      anfrage<TaskRef>(`/api/applications/${appId}/slots/${slot}/regenerate`, {
        method: "POST",
      }),
    exportieren: (appId: number) =>
      anfrage<TaskRef>(`/api/applications/${appId}/export`, { method: "POST" }),
  },
  profile: {
    assetHochladen: (art: "portrait" | "signature", datei: File) =>
      hochladen<{ pfad: string }>(`/api/profile/${art}`, datei),
  },
};
