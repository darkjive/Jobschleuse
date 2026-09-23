import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useCallback, useRef, useState } from "react";
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
import { STATUS_LABEL } from "@/lib/format";
import type { JobListItem, SortOrder, SortSpalte } from "@/types/api";

const SORTIERBAR: { spalte: SortSpalte; label: string }[] = [
  { spalte: "frische", label: "Frische" },
  { spalte: "distance_km", label: "Entfernung" },
  { spalte: "company", label: "Firma" },
  { spalte: "title", label: "Titel" },
];

interface Props {
  stellen: JobListItem[];
  isLoading: boolean;
  sort: SortSpalte;
  order: SortOrder;
  onSortChange: (sort: SortSpalte, order: SortOrder) => void;
  selectedId: number | null;
  onSelectRow: (job: JobListItem) => void;
  /** Tabelle ab md, Kartenliste darunter — nur eine wird gerendert. */
  variante: "tabelle" | "karten";
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
  variante,
}: Props) {
  const [angehakt, setAngehakt] = useState<Set<number>>(new Set());
  // Nur, was gerade sichtbar ist: nach einem Reiter- oder Filterwechsel darf
  // die Sammelaktion keine Stellen treffen, die nicht mehr in der Liste stehen.
  const ausgewaehlt = new Set(stellen.filter((s) => angehakt.has(s.id)).map((s) => s.id));
  const queryClient = useQueryClient();
  const [toolbarHoehe, setToolbarHoehe] = useState(0);
  const observerRef = useRef<ResizeObserver | null>(null);

  // Ref-Callback statt Effekt: die Toolbar erscheint erst nach dem Laden
  // (vorher Skeleton), ein Mount-Effekt fände sie nie.
  const toolbarRef = useCallback((el: HTMLDivElement | null) => {
    observerRef.current?.disconnect();
    observerRef.current = null;
    if (!el) return;
    // Border-Box, nicht contentRect: Padding und Rahmen gehören zur Höhe,
    // sonst schiebt sich der Tabellenkopf um genau diese Pixel darunter.
    const observer = new ResizeObserver(() => setToolbarHoehe(el.offsetHeight));
    observer.observe(el);
    observerRef.current = observer;
  }, []);

  const bulkMutation = useMutation({
    mutationFn: ({ status }: { status: "selected" | "rejected" }) =>
      api.jobs.statusBulk([...ausgewaehlt], status),
    onSuccess: (ergebnis) => {
      toast.success(`${ergebnis.aktualisiert} Stellen aktualisiert.`);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setAngehakt(new Set());
    },
    onError: (error) => toast.error(`Bulk-Aktion fehlgeschlagen: ${error.message}`),
  });

  function toggleRow(id: number, checked: boolean) {
    // Von der sichtbaren Auswahl aus, damit ausgeblendete Häkchen nicht
    // beim Zurückwechseln wieder auftauchen.
    const kopie = new Set(ausgewaehlt);
    if (checked) kopie.add(id);
    else kopie.delete(id);
    setAngehakt(kopie);
  }

  function toggleAlle(checked: boolean) {
    setAngehakt(checked ? new Set(stellen.map((s) => s.id)) : new Set());
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
      <div
        ref={toolbarRef}
        className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-2 border-b border-border bg-background py-2"
      >
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
      ) : variante === "tabelle" ? (
        <div className="overflow-x-auto rounded-md border border-border">
          <Table>
            <TableHeader
              className="sticky z-10 bg-background"
              style={{ top: toolbarHoehe }}
            >
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
                  <TableCell className="whitespace-normal wrap-anywhere">
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
                      {STATUS_LABEL[stelle.status] ?? stelle.status}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
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
                {STATUS_LABEL[stelle.status] ?? stelle.status}
              </Badge>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
