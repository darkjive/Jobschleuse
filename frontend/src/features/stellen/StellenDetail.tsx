import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MousePointerClick } from "lucide-react";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useTask } from "@/hooks/useTask";
import { formatHomeoffice } from "@/lib/format";
import { api } from "@/lib/api";
import type { JobOut } from "@/types/api";

const ANBIETER_LABEL: Record<string, string> = {
  zeitarbeit: "Zeitarbeit",
  vermittler: "private Arbeitsvermittlung",
};

function Fakt({ label, wert }: { label: string; wert: string | number | null | undefined }) {
  if (wert === null || wert === undefined || wert === "") return null;
  return (
    <div className="contents">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{wert}</dd>
    </div>
  );
}

interface Props {
  stelle: JobOut | undefined;
  isLoading: boolean;
}

export function StellenDetail({ stelle, isLoading }: Props) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // Job-ID mitführen: die Komponente bleibt beim Wechsel der Stelle
  // gemountet, der Lauf gehört aber zu der Stelle, für die er gestartet wurde.
  const [erzeugen, setErzeugen] = useState<{ taskId: string; jobId: number } | null>(null);

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "selected" | "rejected" }) =>
      api.jobs.statusSetzen(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
    onError: (error) => toast.error(`Status konnte nicht gesetzt werden: ${error.message}`),
  });

  const erzeugenMutation = useMutation({
    mutationFn: (jobId: number) => api.applications.erzeugen(jobId),
    onSuccess: (ref, jobId) => setErzeugen({ taskId: ref.task_id, jobId }),
    onError: (error) => toast.error(`Bewerbung konnte nicht gestartet werden: ${error.message}`),
  });

  const { data: task } = useTask(erzeugen?.taskId ?? null);

  useEffect(() => {
    if (!task) return;
    if (task.status === "fertig") {
      toast.success("Bewerbung erzeugt.");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setErzeugen(null);
    } else if (task.status === "fehler") {
      toast.error(`Bewerbung fehlgeschlagen: ${task.meldung}`);
      setErzeugen(null);
    }
  }, [task, queryClient]);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!stelle) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
        <MousePointerClick className="size-8 opacity-50" />
        <p>Wähle links eine Stelle aus.</p>
        <p className="text-xs">
          <kbd className="rounded border border-border px-1.5 py-0.5 font-sans">Strg</kbd>{" "}
          <kbd className="rounded border border-border px-1.5 py-0.5 font-sans">K</kbd> durchsucht
          alle Stellen.
        </p>
      </div>
    );
  }

  const erzeugtLaeuft =
    (erzeugenMutation.isPending && erzeugenMutation.variables === stelle.id) ||
    (erzeugen?.jobId === stelle.id && task?.status !== "fertig" && task?.status !== "fehler");

  return (
    <article className="flex flex-col gap-4 p-4">
      <div>
        {/* pr-8: Platz für den Schließen-Knopf im mobilen Sheet */}
        <h2 className="pr-8 text-lg font-semibold">{stelle.title}</h2>
        <p className="text-sm text-muted-foreground">
          {stelle.company} · {stelle.location}
        </p>
      </div>

      {stelle.gone_at && (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          Diese Anzeige ist bei der Quelle nicht mehr vorhanden. Sie wurde am{" "}
          {stelle.gone_at.slice(0, 10)} als nicht mehr verfügbar erkannt.
        </p>
      )}

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        <Fakt label="Quelle" wert={stelle.source_partner || stelle.external_host} />
        <Fakt
          label="Anbieter"
          wert={
            stelle.employer_kind
              ? (ANBIETER_LABEL[stelle.employer_kind] ?? "Arbeitgeber direkt")
              : null
          }
        />
        <Fakt
          label="Adresse"
          wert={
            stelle.street || stelle.plz
              ? `${stelle.street ?? ""}${stelle.street && stelle.plz ? ", " : ""}${stelle.plz ?? ""} ${stelle.location}`
              : null
          }
        />
        <Fakt label="Vergütung" wert={stelle.salary} />
        <Fakt label="Arbeitszeit" wert={stelle.worktime} />
        <Fakt label="Vertrag" wert={stelle.contract} />
        <Fakt label="Homeoffice" wert={formatHomeoffice(stelle.homeoffice)} />
        <Fakt label="Eintritt" wert={stelle.start_date} />
        <Fakt label="Abschluss" wert={stelle.education} />
        <Fakt label="Entfernung" wert={stelle.distance_km != null ? `${stelle.distance_km} km` : null} />
      </dl>

      <p>
        <a
          href={stelle.url}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-primary underline underline-offset-4"
        >
          Anzeige bei der Quelle
        </a>
      </p>

      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => statusMutation.mutate({ id: stelle.id, status: "selected" })}
        >
          Auswählen
        </Button>
        <Button
          variant="outline"
          onClick={() => statusMutation.mutate({ id: stelle.id, status: "rejected" })}
        >
          Aussortieren
        </Button>
        {stelle.application_id ? (
          <Button onClick={() => navigate(`/bewerbung/${stelle.application_id}`)}>
            Bewerbung öffnen
          </Button>
        ) : (
          stelle.status === "selected" && (
            <Button disabled={erzeugtLaeuft} onClick={() => erzeugenMutation.mutate(stelle.id)}>
              {erzeugtLaeuft ? "Wird erzeugt…" : "Bewerbung erstellen"}
            </Button>
          )
        )}
      </div>

      {/* Kein eigenes Scrollen — der umgebende Detailbereich scrollt bereits. */}
      <div className="border-t border-border pt-4 text-sm leading-relaxed wrap-anywhere [&_a]:text-primary [&_a]:underline [&_h1]:mt-4 [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-semibold [&_li]:mb-1 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:mb-3 [&_strong]:font-semibold [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-5">
        <Markdown>{stelle.description_md}</Markdown>
      </div>
    </article>
  );
}
