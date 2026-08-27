import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useDebouncedCallback } from "@/hooks/useDebouncedCallback";
import { useTask } from "@/hooks/useTask";
import { api } from "@/lib/api";
import type { SlotOut } from "@/types/api";

interface Props {
  appId: number;
  name: string;
  daten: SlotOut;
  onGeaendert: () => void;
}

export function SlotCard({ appId, name, daten, onGeaendert }: Props) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(daten.value);
  const [status, setStatus] = useState<"speichert" | "gespeichert" | null>(null);
  const [regenTaskId, setRegenTaskId] = useState<string | null>(null);

  useEffect(() => setValue(daten.value), [daten.value]);

  const saveMutation = useMutation({
    mutationFn: (wert: string) => api.applications.slotSpeichern(appId, name, wert),
    onMutate: () => setStatus("speichert"),
    onSuccess: () => {
      setStatus("gespeichert");
      queryClient.invalidateQueries({ queryKey: ["applications", appId] });
      onGeaendert();
    },
    onError: (error) => {
      setStatus(null);
      toast.error(`Speichern fehlgeschlagen: ${error.message}`);
    },
  });

  const debouncedSave = useDebouncedCallback((wert: string) => saveMutation.mutate(wert), 800);

  const regenMutation = useMutation({
    mutationFn: () => api.applications.slotRegenerieren(appId, name),
    onSuccess: (ref) => setRegenTaskId(ref.task_id),
    onError: (error) => toast.error(`Neu erzeugen fehlgeschlagen: ${error.message}`),
  });

  const { data: task } = useTask(regenTaskId);

  useEffect(() => {
    if (!task) return;
    if (task.status === "fertig") {
      queryClient.invalidateQueries({ queryKey: ["applications", appId] });
      onGeaendert();
      setRegenTaskId(null);
      toast.success(`Block „${name}“ neu erzeugt.`);
    } else if (task.status === "fehler") {
      toast.error(`Neu erzeugen fehlgeschlagen: ${task.meldung}`);
      setRegenTaskId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task, queryClient, appId, name]);

  const regeneriertLaeuft = regenMutation.isPending || task?.status === "läuft";

  return (
    <Card className="gap-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <Label className="font-mono text-sm">{name}</Label>
        <div className="flex items-center gap-2">
          <Badge variant={daten.source === "llm" ? "secondary" : "outline"}>
            {daten.source === "llm" ? "vom Modell" : "von Hand"}
          </Badge>
          <Button
            size="sm"
            variant="outline"
            disabled={regeneriertLaeuft}
            onClick={() => regenMutation.mutate()}
          >
            {regeneriertLaeuft ? "wird erzeugt…" : "Neu erzeugen"}
          </Button>
        </div>
      </div>
      <Textarea
        value={value}
        rows={4}
        onChange={(event) => {
          setValue(event.target.value);
          debouncedSave(event.target.value);
        }}
      />
      <span className="h-4 text-xs text-muted-foreground">
        {status === "speichert" ? "speichert …" : status === "gespeichert" ? "gespeichert" : ""}
      </span>
    </Card>
  );
}
