import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useTask } from "@/hooks/useTask";
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
  const [erzeugenTaskId, setErzeugenTaskId] = useState<string | null>(null);

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "selected" | "rejected" }) =>
      api.jobs.statusSetzen(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
    onError: (error) => toast.error(`Status konnte nicht gesetzt werden: ${error.message}`),
  });

  const erzeugenMutation = useMutation({
    mutationFn: (jobId: number) => api.applications.erzeugen(jobId),
    onSuccess: (ref) => setErzeugenTaskId(ref.task_id),
    onError: (error) => toast.error(`Bewerbung konnte nicht gestartet werden: ${error.message}`),
  });

  const { data: task } = useTask(erzeugenTaskId);

  useEffect(() => {
    if (!task) return;
    if (task.status === "fertig") {
      toast.success("Bewerbung erzeugt.");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setErzeugenTaskId(null);
    } else if (task.status === "fehler") {
      toast.error(`Bewerbung fehlgeschlagen: ${task.meldung}`);
      setErzeugenTaskId(null);
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
      <p className="p-4 text-sm text-muted-foreground">Wähle links eine Stelle aus.</p>
    );
  }

  const erzeugtLaeuft = erzeugenMutation.isPending || task?.status === "läuft";

  return (
    <article className="flex flex-col gap-4 p-4">
      <div>
        <h2 className="text-lg font-semibold">{stelle.title}</h2>
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
        <Fakt label="Homeoffice" wert={stelle.homeoffice} />
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

      <pre className="max-h-96 overflow-y-auto rounded-md border border-border bg-muted p-3 text-sm whitespace-pre-wrap">
        {stelle.description_md}
      </pre>
    </article>
  );
}
