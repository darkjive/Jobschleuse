import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { JobBadges } from "@/features/stellen/JobBadges";
import { api } from "@/lib/api";
import type { JobOut, SortOrder, SortSpalte } from "@/types/api";

const SORTIERBAR: { spalte: SortSpalte; label: string }[] = [
  { spalte: "frische", label: "Frische" },
  { spalte: "distance_km", label: "Entfernung" },
  { spalte: "company", label: "Firma" },
  { spalte: "title", label: "Titel" },
];

interface Props {
  stellen: JobOut[];
  isLoading: boolean;
  sort: SortSpalte;
  order: SortOrder;
  onSortChange: (sort: SortSpalte, order: SortOrder) => void;
  selectedId: number | null;
  onSelectRow: (job: JobOut) => void;
}

function SortToolbar({
  sort,
  order,
  onSortChange,
}: Pick<Props, "sort" | "order" | "onSortChange">) {
  return (
    <div className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
      <span>Sortieren:</span>
      {SORTIERBAR.map(({ spalte, label }) => {
        const aktiv = sort === spalte;
        const Icon = aktiv ? (order === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
        return (
          <Button
            key={spalte}
            variant={aktiv ? "secondary" : "ghost"}
            size="sm"
            className="h-7 gap-1 px-2"
            onClick={() => onSortChange(spalte, aktiv && order === "asc" ? "desc" : "asc")}
          >
            {label}
            <Icon className="size-3.5 opacity-70" />
          </Button>
        );
      })}
    </div>
  );
}

export function StellenTable({
  stellen,
  isLoading,
  sort,
  order,
  onSortChange,
  selectedId,
  onSelectRow,
}: Props) {
  const [ausgewaehlt, setAusgewaehlt] = useState<Set<number>>(new Set());
  const queryClient = useQueryClient();

  const bulkMutation = useMutation({
    mutationFn: ({ status }: { status: "selected" | "rejected" }) =>
      api.jobs.statusBulk([...ausgewaehlt], status),
    onSuccess: (ergebnis) => {
      toast.success(`${ergebnis.aktualisiert} Stellen aktualisiert.`);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setAusgewaehlt(new Set());
    },
    onError: (error) => toast.error(`Bulk-Aktion fehlgeschlagen: ${error.message}`),
  });

  function toggleRow(id: number, checked: boolean) {
    setAusgewaehlt((bisher) => {
      const kopie = new Set(bisher);
      if (checked) kopie.add(id);
      else kopie.delete(id);
      return kopie;
    });
  }

  function toggleAlle(checked: boolean) {
    setAusgewaehlt(checked ? new Set(stellen.map((s) => s.id)) : new Set());
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {[0, 1, 2, 3, 4, 5].map((platzhalter) => (
          <Skeleton key={platzhalter} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SortToolbar sort={sort} order={order} onSortChange={onSortChange} />
        {ausgewaehlt.size > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <span>{ausgewaehlt.size} ausgewählt</span>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => bulkMutation.mutate({ status: "selected" })}
              disabled={bulkMutation.isPending}
            >
              Auswählen
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => bulkMutation.mutate({ status: "rejected" })}
              disabled={bulkMutation.isPending}
            >
              Aussortieren
            </Button>
          </div>
        )}
      </div>

      {stellen.length === 0 ? (
        <p className="text-sm text-muted-foreground">Keine Stellen gefunden.</p>
      ) : (
        <>
          {/* Ab md: echte Tabelle. Darunter: Kartenliste — gleiche Daten,
              ohne horizontales Scrollen auf schmalen Bildschirmen. */}
          <div className="hidden overflow-x-auto rounded-md border border-border md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={stellen.length > 0 && ausgewaehlt.size === stellen.length}
                      onCheckedChange={(checked) => toggleAlle(checked === true)}
                      aria-label="Alle auswählen"
                    />
                  </TableHead>
                  <TableHead>Stelle</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {stellen.map((stelle) => (
                  <TableRow
                    key={stelle.id}
                    data-state={selectedId === stelle.id ? "selected" : undefined}
                    className="cursor-pointer"
                    onClick={() => onSelectRow(stelle)}
                  >
                    <TableCell>
                      <Checkbox
                        checked={ausgewaehlt.has(stelle.id)}
                        onCheckedChange={(checked) => toggleRow(stelle.id, checked === true)}
                        onClick={(event) => event.stopPropagation()}
                        aria-label="Zeile auswählen"
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-1 py-1">
                        <span className="font-medium">{stelle.title}</span>
                        <span className="text-sm text-muted-foreground">
                          {stelle.company} · {stelle.location}
                        </span>
                        <JobBadges stelle={stelle} />
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={stelle.status === "selected" ? "default" : "secondary"}>
                        {stelle.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex flex-col gap-2 md:hidden">
            {stellen.map((stelle) => (
              <Card
                key={stelle.id}
                data-state={selectedId === stelle.id ? "selected" : undefined}
                className="cursor-pointer gap-2 p-3 data-[state=selected]:border-primary"
                onClick={() => onSelectRow(stelle)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex flex-col gap-1">
                    <span className="font-medium">{stelle.title}</span>
                    <span className="text-sm text-muted-foreground">
                      {stelle.company} · {stelle.location}
                    </span>
                  </div>
                  <Checkbox
                    checked={ausgewaehlt.has(stelle.id)}
                    onCheckedChange={(checked) => toggleRow(stelle.id, checked === true)}
                    onClick={(event) => event.stopPropagation()}
                    aria-label="Zeile auswählen"
                  />
                </div>
                <JobBadges stelle={stelle} />
                <Badge
                  variant={stelle.status === "selected" ? "default" : "secondary"}
                  className="w-fit"
                >
                  {stelle.status}
                </Badge>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
