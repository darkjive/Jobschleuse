import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { slotLabel } from "@/features/bewerbung/slots";
import { merkeSpeichern } from "@/features/bewerbung/speichern";
import { useDebouncedCallback } from "@/hooks/useDebouncedCallback";
import { useTaskErgebnis } from "@/hooks/useTaskErgebnis";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
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

  // Eingabe, die der Server noch nicht bestätigt hat. Solange es sie gibt,
  // darf ein Refetch das Feld nicht zurücksetzen — sonst überschreibt der
  // gerade gespeicherte, ältere Stand das, was inzwischen getippt wurde.
  const ungespeichertRef = useRef<string | null>(null);

  useEffect(() => {
    if (ungespeichertRef.current === null) setValue(daten.value);
  }, [daten.value]);

  const saveMutation = useMutation({
    mutationFn: (wert: string) => api.applications.slotSpeichern(appId, name, wert),
    onMutate: () => setStatus("speichert"),
    onSuccess: (_ergebnis, wert) => {
      if (ungespeichertRef.current === wert) ungespeichertRef.current = null;
      setStatus("gespeichert");
      queryClient.invalidateQueries({ queryKey: ["applications", appId] });
      onGeaendert();
    },
    onError: (error) => {
      setStatus(null);
      toast.error(`Speichern fehlgeschlagen: ${error.message}`);
    },
  });

  const debouncedSave = useDebouncedCallback(
    (wert: string) => merkeSpeichern(saveMutation.mutateAsync(wert)),
    800,
  );
  const { flush } = debouncedSave;

  // Seite verlassen, bevor die Verzögerung abläuft: trotzdem speichern.
  useEffect(() => flush, [flush]);

  const regenMutation = useMutation({
    mutationFn: () => api.applications.slotRegenerieren(appId, name),
    onSuccess: (ref) => setRegenTaskId(ref.task_id),
    onError: (error) => toast.error(`Neu erzeugen fehlgeschlagen: ${error.message}`),
  });

  const task = useTaskErgebnis(regenTaskId, {
    onFertig: () => {
      queryClient.invalidateQueries({ queryKey: ["applications", appId] });
      onGeaendert();
      setRegenTaskId(null);
      toast.success(`Block „${name}“ neu erzeugt.`);
    },
    onFehler: (task) => {
      toast.error(`Neu erzeugen fehlgeschlagen: ${task.meldung}`);
      setRegenTaskId(null);
    },
  });

  const regeneriertLaeuft = regenMutation.isPending || task?.status === "läuft";
  // Fließtext-Blöcke brauchen Platz, Einzeiler (Firma, Datum …) nicht.
  const lang = name.endsWith("_text") || daten.value.length > 120;

  return (
    <Card className="shrink-0 gap-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={`slot-${name}`}>{slotLabel(name)}</Label>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {status === "speichert" ? "speichert …" : status === "gespeichert" ? "gespeichert" : ""}
          </span>
          <Badge variant={daten.source === "llm" ? "secondary" : "outline"}>
            {daten.source === "llm" ? "vom Modell" : "von Hand"}
          </Badge>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant="ghost"
                disabled={regeneriertLaeuft}
                aria-label={`${slotLabel(name)} neu erzeugen`}
                onClick={() => regenMutation.mutate()}
              >
                <RefreshCw className={cn(regeneriertLaeuft && "animate-spin")} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Neu erzeugen</TooltipContent>
          </Tooltip>
        </div>
      </div>
      <Textarea
        id={`slot-${name}`}
        value={value}
        rows={lang ? 12 : 2}
        className={cn("text-base md:text-base", lang ? "min-h-64" : "min-h-0")}
        onChange={(event) => {
          setValue(event.target.value);
          ungespeichertRef.current = event.target.value;
          debouncedSave(event.target.value);
        }}
        onBlur={flush}
      />
    </Card>
  );
}
