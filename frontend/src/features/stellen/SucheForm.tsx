import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useTaskErgebnis } from "@/hooks/useTaskErgebnis";
import { api } from "@/lib/api";

const schema = z.object({
  quelle: z.enum(["arbeitsagentur", "indeed"]),
  was: z.string().min(1, "Pflichtfeld"),
  wo: z.string().min(1, "Pflichtfeld"),
  // Leeres Feld liefert per valueAsNumber NaN — ohne eigene Meldung bliebe
  // der Klick auf „Stellen suchen“ kommentarlos wirkungslos.
  umkreis: z.number({ error: "0–200 km" }).min(0, "0–200 km").max(200, "0–200 km"),
  seit: z.string(),
  ohne_zeitarbeit: z.boolean(),
  nur_arbeit: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

const DEFAULTS: FormValues = {
  quelle: "arbeitsagentur",
  was: "",
  wo: "",
  umkreis: 50,
  seit: "",
  ohne_zeitarbeit: false,
  nur_arbeit: false,
};

export function SucheForm() {
  const queryClient = useQueryClient();
  const [taskId, setTaskId] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    control,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: DEFAULTS,
  });

  const mutation = useMutation({
    mutationFn: api.jobs.suchen,
    onSuccess: (ref) => setTaskId(ref.task_id),
    onError: (error) => toast.error(`Suche konnte nicht gestartet werden: ${error.message}`),
  });

  const task = useTaskErgebnis(taskId, {
    onFertig: (task) => {
      toast.success(typeof task.ergebnis === "string" ? task.ergebnis : "Suche abgeschlossen.");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setTaskId(null);
    },
    onFehler: (task) => {
      toast.error(`Suche fehlgeschlagen: ${task.meldung}`);
      setTaskId(null);
    },
  });

  function onSubmit(values: FormValues) {
    mutation.mutate({
      was: values.was,
      wo: values.wo,
      umkreis: values.umkreis,
      seit: values.seit ? Number(values.seit) : null,
      ohne_zeitarbeit: values.ohne_zeitarbeit,
      nur_arbeit: values.nur_arbeit,
      quelle: values.quelle,
    });
  }

  const quelle = watch("quelle");
  const laeuft = mutation.isPending || task?.status === "läuft";

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex w-full flex-col gap-2">
      <div className="flex flex-col gap-2 md:flex-row md:items-start">
        <Controller
          control={control}
          name="quelle"
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger className="w-full md:w-40" aria-label="Quelle">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="arbeitsagentur">Arbeitsagentur</SelectItem>
                <SelectItem value="indeed">Indeed</SelectItem>
              </SelectContent>
            </Select>
          )}
        />
        <div className="flex flex-col gap-1 md:flex-1">
          <Input
            {...register("was")}
            placeholder="Was, z. B. Frontend Entwickler"
            aria-label="Wonach suchen"
          />
          {errors.was && <p className="text-xs text-destructive">{errors.was.message}</p>}
        </div>
        <div className="flex flex-col gap-1 md:w-48">
          <Input
            {...register("wo")}
            placeholder="Wo, z. B. Darmstadt"
            aria-label="Wo suchen"
          />
          {errors.wo && <p className="text-xs text-destructive">{errors.wo.message}</p>}
        </div>
        <div className="flex flex-col gap-1 md:w-24">
          <InputGroup>
            <InputGroupInput
              {...register("umkreis", { valueAsNumber: true })}
              type="number"
              min={0}
              max={200}
              aria-label="Umkreis in km"
            />
            <InputGroupAddon align="inline-end">km</InputGroupAddon>
          </InputGroup>
          {errors.umkreis && (
            <p className="text-xs text-destructive">{errors.umkreis.message}</p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Controller
          control={control}
          name="seit"
          render={({ field }) => (
            <Select
              value={field.value || "egal"}
              onValueChange={(wert) => field.onChange(wert === "egal" ? "" : wert)}
            >
              <SelectTrigger className="w-40" aria-label="Veröffentlicht seit">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="egal">Alter egal</SelectItem>
                <SelectItem value="7">letzte 7 Tage</SelectItem>
                <SelectItem value="14">letzte 14 Tage</SelectItem>
                <SelectItem value="30">letzte 30 Tage</SelectItem>
              </SelectContent>
            </Select>
          )}
        />
        {quelle === "arbeitsagentur" && (
          <>
            <label className="flex items-center gap-2 text-sm">
              <Controller
                control={control}
                name="ohne_zeitarbeit"
                render={({ field }) => (
                  <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                )}
              />
              ohne Zeitarbeit
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Controller
                control={control}
                name="nur_arbeit"
                render={({ field }) => (
                  <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                )}
              />
              keine Ausbildung
            </label>
          </>
        )}
        <Button type="submit" disabled={laeuft} className="w-full md:ml-auto md:w-auto">
          {laeuft ? "Suche läuft…" : "Stellen suchen"}
        </Button>
      </div>
    </form>
  );
}
