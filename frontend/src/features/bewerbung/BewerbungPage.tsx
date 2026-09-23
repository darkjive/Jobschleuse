import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
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
import { slotSortierung } from "@/features/bewerbung/slots";
import { alleGespeichert } from "@/features/bewerbung/speichern";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { usePersistedLayout } from "@/hooks/usePersistedLayout";
import { useTaskErgebnis } from "@/hooks/useTaskErgebnis";
import { useSetHeaderActions } from "@/lib/header-actions";
import { api } from "@/lib/api";

export function BewerbungPage() {
  const { appId } = useParams<{ appId: string }>();
  const id = Number(appId);
  const navigate = useNavigate();
  const [previewKey, setPreviewKey] = useState(0);
  const [exportTaskId, setExportTaskId] = useState<string | null>(null);
  const { defaultLayout, onLayoutChanged } = usePersistedLayout("bewerbung-split");
  const isMobile = useMediaQuery("(max-width: 767px)");
  const [mobileTab, setMobileTab] = useState<"inhalte" | "vorschau">("inhalte");

  const detailQuery = useQuery({
    queryKey: ["applications", id],
    queryFn: () => api.applications.detail(id),
    enabled: Number.isFinite(id),
  });

  const exportMutation = useMutation({
    // Der Klick auf „Exportieren“ nimmt dem Textfeld den Fokus, onBlur stößt
    // das Speichern an — darauf warten, sonst fehlt die letzte Eingabe.
    mutationFn: async () => {
      await alleGespeichert();
      return api.applications.exportieren(id);
    },
    onSuccess: (ref) => setExportTaskId(ref.task_id),
    onError: (error) => toast.error(`Export fehlgeschlagen: ${error.message}`),
  });

  const exportTask = useTaskErgebnis(exportTaskId, {
    onFertig: (task) => {
      toast.success(typeof task.ergebnis === "string" ? task.ergebnis : "Export fertig.");
      setExportTaskId(null);
    },
    onFehler: (task) => {
      toast.error(`Export fehlgeschlagen: ${task.meldung}`);
      setExportTaskId(null);
    },
  });

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

  const slotListe = (
    <div className="flex h-full flex-col gap-3 overflow-y-auto pr-2">
      {Object.entries(application.slots)
        .sort(([a], [b]) => slotSortierung(a, b))
        .map(([name, daten]) => (
          <SlotCard
            key={name}
            appId={id}
            name={name}
            daten={daten}
            onGeaendert={() => setPreviewKey((k) => k + 1)}
          />
        ))}
    </div>
  );

  const vorschau = (
    <iframe
      key={previewKey}
      title="Vorschau der Bewerbung"
      src={`/applications/${id}/preview`}
      className="h-full w-full rounded-md border border-border bg-white"
    />
  );

  return (
    <div className="flex h-full flex-col gap-4">
      {headerActions}
      <h2 className="text-lg font-semibold">
        {stelle.title} — {stelle.company}
      </h2>
      {isMobile ? (
        <>
          <div className="flex gap-2">
            <Button
              variant={mobileTab === "inhalte" ? "secondary" : "ghost"}
              onClick={() => setMobileTab("inhalte")}
            >
              Inhalte
            </Button>
            <Button
              variant={mobileTab === "vorschau" ? "secondary" : "ghost"}
              onClick={() => setMobileTab("vorschau")}
            >
              Vorschau
            </Button>
          </div>
          {/* Beide bleiben gemountet, damit ein laufender Auto-Save beim
              Tab-Wechsel nicht verworfen wird. */}
          <div className={mobileTab === "inhalte" ? "min-h-0 flex-1" : "hidden"}>{slotListe}</div>
          <div className={mobileTab === "vorschau" ? "min-h-0 flex-1" : "hidden"}>{vorschau}</div>
        </>
      ) : (
        <ResizablePanelGroup
          orientation="horizontal"
          defaultLayout={defaultLayout}
          onLayoutChanged={onLayoutChanged}
          className="flex-1"
        >
          <ResizablePanel id="editor" defaultSize={50} minSize={30}>
            {slotListe}
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel id="vorschau" defaultSize={50} minSize={30}>
            {vorschau}
          </ResizablePanel>
        </ResizablePanelGroup>
      )}
    </div>
  );
}
