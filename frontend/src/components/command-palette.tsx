import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { api } from "@/lib/api";

/** Strg/Cmd+K — Stelle per Titel/Firma finden und direkt öffnen. */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [suchtext, setSuchtext] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((offen) => !offen);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const { data: treffer } = useQuery({
    queryKey: ["jobs", "palette", suchtext],
    queryFn: () => api.jobs.liste({ q: suchtext, limit: 20 }),
    enabled: open,
  });

  function auswaehlen(jobId: number) {
    setOpen(false);
    setSuchtext("");
    navigate(`/?stelle=${jobId}`);
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="Stellen durchsuchen"
      description="Nach Titel oder Firma suchen und direkt öffnen"
    >
      <Command shouldFilter={false}>
        <CommandInput
          placeholder="Stelle nach Titel oder Firma suchen…"
          value={suchtext}
          onValueChange={setSuchtext}
        />
        <CommandList>
          <CommandEmpty>Keine Treffer.</CommandEmpty>
          <CommandGroup heading="Stellen">
            {treffer?.map((job) => (
              <CommandItem key={job.id} value={String(job.id)} onSelect={() => auswaehlen(job.id)}>
                {job.title} — {job.company}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
