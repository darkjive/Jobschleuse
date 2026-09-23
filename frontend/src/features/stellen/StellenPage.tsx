import { useQuery } from "@tanstack/react-query";
import { SlidersHorizontal, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { FilterSidebar, type FilterState } from "@/features/stellen/FilterSidebar";
import { StellenDetail } from "@/features/stellen/StellenDetail";
import { StatusTabs } from "@/features/stellen/StatusTabs";
import { StellenTable } from "@/features/stellen/StellenTable";
import { SucheForm } from "@/features/stellen/SucheForm";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { usePersistedLayout } from "@/hooks/usePersistedLayout";
import { useSetHeaderActions } from "@/lib/header-actions";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { JobOut, SortOrder, SortSpalte } from "@/types/api";

export function StellenPage() {
  const [params, setParams] = useSearchParams();
  // Mobil: Suche und Filter eingeklappt, damit die Liste sofort sichtbar ist.
  // Nur per CSS versteckt, damit eine laufende Suche (Task-Polling) weiterläuft.
  const [sucheOffen, setSucheOffen] = useState(false);
  const [filterOffen, setFilterOffen] = useState(false);

  const filter: FilterState = {
    // "alle" steht explizit in der URL — ein fehlender Parameter heißt "neu".
    status: params.get("status") === "alle" ? "" : (params.get("status") ?? "new"),
    q: params.get("q") ?? "",
    ort: params.get("ort") ?? "",
    verschwunden: params.get("verschwunden") === "1",
  };
  const sort = (params.get("sort") as SortSpalte) || "id";
  const order = (params.get("order") as SortOrder) || "desc";
  const stelleId = params.get("stelle") ? Number(params.get("stelle")) : null;
  const aktiveFilter = [filter.q, filter.ort, filter.verschwunden].filter(Boolean).length;

  const headerActions = useSetHeaderActions(
    <>
      <div className="flex w-full gap-2 md:hidden">
        <Button
          variant={sucheOffen ? "secondary" : "outline"}
          className="flex-1"
          aria-expanded={sucheOffen}
          onClick={() => setSucheOffen((offen) => !offen)}
        >
          <Search /> Neue Suche
        </Button>
        <Button
          variant={filterOffen ? "secondary" : "outline"}
          className="flex-1"
          aria-expanded={filterOffen}
          onClick={() => setFilterOffen((offen) => !offen)}
        >
          <SlidersHorizontal /> Filter{aktiveFilter > 0 && ` (${aktiveFilter})`}
        </Button>
      </div>
      <div className={cn("w-full md:block", !sucheOffen && "hidden")}>
        <SucheForm />
      </div>
    </>,
  );

  function patchParams(patch: Record<string, string | null>) {
    setParams(
      (bisher) => {
        const naechste = new URLSearchParams(bisher);
        for (const [key, value] of Object.entries(patch)) {
          if (value === null || value === "") naechste.delete(key);
          else naechste.set(key, value);
        }
        return naechste;
      },
      { replace: true },
    );
  }

  const jobsQuery = useQuery({
    queryKey: ["jobs", filter, sort, order],
    queryFn: () =>
      api.jobs.liste({
        status: filter.status || undefined,
        q: filter.q || undefined,
        ort: filter.ort || undefined,
        verschwunden: filter.verschwunden,
        sort,
        order,
      }),
  });

  const detailQuery = useQuery({
    queryKey: ["jobs", "detail", stelleId],
    queryFn: () => api.jobs.detail(stelleId as number),
    enabled: stelleId !== null,
  });

  const anzahlQuery = useQuery({
    queryKey: ["jobs", "anzahl", filter.q, filter.ort, filter.verschwunden],
    queryFn: () =>
      api.jobs.anzahl({
        q: filter.q || undefined,
        ort: filter.ort || undefined,
        verschwunden: filter.verschwunden,
      }),
  });

  const stellen = useMemo(() => jobsQuery.data ?? [], [jobsQuery.data]);
  const { defaultLayout, onLayoutChanged } = usePersistedLayout("stellen-split");
  const isMobile = useMediaQuery("(max-width: 767px)");

  function onSelectRow(job: JobOut) {
    patchParams({ stelle: String(job.id) });
  }

  function onSortChange(nextSort: SortSpalte, nextOrder: SortOrder) {
    patchParams({ sort: nextSort, order: nextOrder });
  }

  return (
    <div className="flex h-full flex-col gap-4 md:flex-row">
      {headerActions}
      <div className={cn("shrink-0 md:block", !filterOffen && "hidden")}>
        <FilterSidebar
          value={filter}
          onChange={(next) =>
            patchParams({
              q: next.q,
              ort: next.ort,
              verschwunden: next.verschwunden ? "1" : null,
            })
          }
        />
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <StatusTabs
          value={filter.status}
          anzahl={anzahlQuery.data}
          onChange={(status) => patchParams({ status: status || "alle", stelle: null })}
        />
        {/* Ab md: Liste und Detail nebeneinander, verschiebbar. Darunter:
            nur die Liste, Detail als Sheet von unten. Per JS statt CSS
            umgeschaltet, damit die Liste nur einmal im DOM steht. */}
        {isMobile ? (
          <div>
            <StellenTable
              stellen={stellen}
              isLoading={jobsQuery.isLoading}
              sort={sort}
              order={order}
              onSortChange={onSortChange}
              selectedId={stelleId}
              onSelectRow={onSelectRow}
              variante="karten"
            />
            <Sheet
              open={stelleId !== null}
              onOpenChange={(offen) => {
                if (!offen) patchParams({ stelle: null });
              }}
            >
              {/* data-[side=bottom]: nötig, sonst gewinnt h-auto aus sheet.tsx. */}
              <SheetContent side="bottom" className="data-[side=bottom]:h-[85vh]">
                <SheetHeader className="sr-only">
                  <SheetTitle>Stellendetail</SheetTitle>
                </SheetHeader>
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <StellenDetail stelle={detailQuery.data} isLoading={detailQuery.isFetching} />
                </div>
              </SheetContent>
            </Sheet>
          </div>
        ) : (
          <div className="min-h-0 flex-1">
            <ResizablePanelGroup
              orientation="horizontal"
              defaultLayout={defaultLayout}
              onLayoutChanged={onLayoutChanged}
            >
              <ResizablePanel id="liste" defaultSize={60} minSize={35}>
                <div className="h-full overflow-y-auto pr-2">
                  <StellenTable
                    stellen={stellen}
                    isLoading={jobsQuery.isLoading}
                    sort={sort}
                    order={order}
                    onSortChange={onSortChange}
                    selectedId={stelleId}
                    onSelectRow={onSelectRow}
                    variante="tabelle"
                  />
                </div>
              </ResizablePanel>
              <ResizableHandle withHandle />
              <ResizablePanel id="detail" defaultSize={40} minSize={25}>
                <div className="h-full overflow-y-auto rounded-md border border-border">
                  <StellenDetail stelle={detailQuery.data} isLoading={detailQuery.isFetching} />
                </div>
              </ResizablePanel>
            </ResizablePanelGroup>
          </div>
        )}
      </div>
    </div>
  );
}
