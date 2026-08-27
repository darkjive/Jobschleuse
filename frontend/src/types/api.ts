// Spiegelt src/bewerbungs_pipeline/web/schemas.py — Feldnamen und
// Optionalität müssen zur Pydantic-Seite passen, sonst driften API und
// Frontend auseinander, ohne dass TypeScript das bemerkt.

export type Status = "new" | "selected" | "rejected";

export interface JobOut {
  id: number;
  title: string;
  company: string;
  location: string;
  url: string;
  source: string;
  status: Status;
  source_ref: string | null;
  posted_at: string | null;
  description_md: string;
  job_kind: string | null;
  employer_kind: string | null;
  source_partner: string | null;
  external_host: string | null;
  homeoffice: string | null;
  salary: string | null;
  contract: string | null;
  worktime: string | null;
  distance_km: number | null;
  start_date: string | null;
  changed_at: string | null;
  street: string | null;
  plz: string | null;
  education: string | null;
  gone_at: string | null;
  scraped_at: string;
  application_id: number | null;
}

export interface SlotOut {
  value: string;
  source: "llm" | "manuell";
  updated_at: string;
}

export interface ApplicationOut {
  id: number;
  job_id: number;
  template_path: string;
  created_at: string;
  updated_at: string;
  slots: Record<string, SlotOut>;
}

export interface ApplicationDetail {
  application: ApplicationOut;
  stelle: JobOut;
}

export interface TaskOut {
  id: string;
  beschreibung: string;
  status: "läuft" | "fertig" | "fehler";
  meldung: string;
  ergebnis: unknown;
}

export interface TaskRef {
  task_id: string;
}

export type SortSpalte = "id" | "frische" | "distance_km" | "company" | "title";
export type SortOrder = "asc" | "desc";

export interface JobsQuery {
  status?: string;
  q?: string;
  ort?: string;
  verschwunden?: boolean;
  sort?: SortSpalte;
  order?: SortOrder;
  limit?: number;
}

export interface FetchRequest {
  was: string;
  wo: string;
  umkreis?: number;
  seit?: number | null;
  ohne_zeitarbeit?: boolean;
  nur_arbeit?: boolean;
  quelle?: "arbeitsagentur" | "indeed";
}
