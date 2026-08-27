import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useTask } from "@/hooks/useTask";
import { api } from "@/lib/api";

const schema = z.object({
  quelle: z.enum(["arbeitsagentur", "indeed"]),
  was: z.string().min(1, "Pflichtfeld"),
  wo: z.string().min(1, "Pflichtfeld"),
  umkreis: z.number().min(0).max(200),
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

  const { data: task } = useTask(taskId);

  useEffect(() => {
    if (!task) return;
    if (task.status === "fertig") {
      toast.success(typeof task.ergebnis === "string" ? task.ergebnis : "Suche abgeschlossen.");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setTaskId(null);
    } else if (task.status === "fehler") {
      toast.error(`Suche fehlgeschlagen: ${task.meldung}`);
      setTaskId(null);
    }
  }, [task, queryClient]);

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
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-wrap items-end gap-2">
      <Controller
        control={control}
        name="quelle"
        render={({ field }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger className="w-40" aria-label="Quelle">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="arbeitsagentur">Arbeitsagentur</SelectItem>
              <SelectItem value="indeed">Indeed</SelectItem>
            </SelectContent>
          </Select>
        )}
      />
      <div className="flex flex-col gap-1">
        <Input
          {...register("was")}
          placeholder="Was, z. B. Frontend Entwickler"
          aria-label="Wonach suchen"
          className="w-56"
        />
        {errors.was && <p className="text-xs text-destructive">{errors.was.message}</p>}
      </div>
      <div className="flex flex-col gap-1">
        <Input
          {...register("wo")}
          placeholder="Wo, z. B. Darmstadt"
          aria-label="Wo suchen"
          className="w-44"
        />
        {errors.wo && <p className="text-xs text-destructive">{errors.wo.message}</p>}
      </div>
      <Input
        {...register("umkreis", { valueAsNumber: true })}
        type="number"
        min={0}
        max={200}
        aria-label="Umkreis in km"
        className="w-24"
      />
      <Controller
        control={control}
        name="seit"
        render={({ field }) => (
          <Select
            value={field.value || "egal"}
            onValueChange={(wert) => field.onChange(wert === "egal" ? "" : wert)}
          >
            <SelectTrigger className="w-44" aria-label="Veröffentlicht seit">
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
      <Button type="submit" disabled={laeuft}>
        {laeuft ? "Suche läuft…" : "Stellen suchen"}
      </Button>
    </form>
  );
}
