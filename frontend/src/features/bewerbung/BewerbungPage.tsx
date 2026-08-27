import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Skeleton } from "@/components/ui/skeleton";
import { SlotCard } from "@/features/bewerbung/SlotCard";
import { usePersistedLayout } from "@/hooks/usePersistedLayout";
import { useTask } from "@/hooks/useTask";
import { useSetHeaderActions } from "@/lib/header-actions";
import { api } from "@/lib/api";

export function BewerbungPage() {
  const { appId } = useParams<{ appId: string }>();
  const id = Number(appId);
  const navigate = useNavigate();
  const [previewKey, setPreviewKey] = useState(0);
  const [exportTaskId, setExportTaskId] = useState<string | null>(null);
  const { defaultLayout, onLayoutChanged } = usePersistedLayout("bewerbung-split");

  const detailQuery = useQuery({
    queryKey: ["applications", id],
    queryFn: () => api.applications.detail(id),
    enabled: Number.isFinite(id),
  });

  const exportMutation = useMutation({
    mutationFn: () => api.applications.exportieren(id),
    onSuccess: (ref) => setExportTaskId(ref.task_id),
    onError: (error) => toast.error(`Export fehlgeschlagen: ${error.message}`),
  });

  const { data: exportTask } = useTask(exportTaskId);

  useEffect(() => {
    if (!exportTask) return;
    if (exportTask.status === "fertig") {
      toast.success(
        typeof exportTask.ergebnis === "string" ? exportTask.ergebnis : "Export fertig.",
      );
      setExportTaskId(null);
    } else if (exportTask.status === "fehler") {
      toast.error(`Export fehlgeschlagen: ${exportTask.meldung}`);
      setExportTaskId(null);
    }
  }, [exportTask]);

  const exportLaeuft = exportMutation.isPending || exportTask?.status === "läuft";

  const headerActions = useSetHeaderActions(
    <>
      <Button variant="outline" onClick={() => navigate("/")}>
        Zurück zu den Stellen
      </Button>
      <Button disabled={exportLaeuft} onClick={() => exportMutation.mutate()}>
        {exportLaeuft ? "Exportiert…" : "Exportieren"}
      </Button>
    </>,
  );

  if (detailQuery.isLoading) {
    return (
      <div className="flex flex-col gap-3">
        {headerActions}
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!detailQuery.data) {
    return (
      <>
        {headerActions}
        <p className="text-sm text-muted-foreground">Bewerbung nicht gefunden.</p>
      </>
    );
  }

  const { application, stelle } = detailQuery.data;

  return (
    <div className="flex h-full flex-col gap-4">
      {headerActions}
      <h2 className="text-lg font-semibold">
        {stelle.title} — {stelle.company}
      </h2>
      <ResizablePanelGroup
        orientation="horizontal"
        defaultLayout={defaultLayout}
        onLayoutChanged={onLayoutChanged}
        className="flex-1"
      >
        <ResizablePanel id="editor" defaultSize={50} minSize={30}>
          <div className="flex h-full flex-col gap-3 overflow-y-auto pr-2">
            {Object.entries(application.slots).map(([name, daten]) => (
              <SlotCard
                key={name}
                appId={id}
                name={name}
                daten={daten}
                onGeaendert={() => setPreviewKey((k) => k + 1)}
              />
            ))}
          </div>
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="vorschau" defaultSize={50} minSize={30}>
          <iframe
            key={previewKey}
            title="Vorschau der Bewerbung"
            src={`/applications/${id}/preview`}
            className="h-full w-full rounded-md border border-border bg-white"
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
