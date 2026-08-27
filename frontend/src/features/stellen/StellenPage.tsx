import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { FilterSidebar, type FilterState } from "@/features/stellen/FilterSidebar";
import { StellenDetail } from "@/features/stellen/StellenDetail";
import { StellenTable } from "@/features/stellen/StellenTable";
import { SucheForm } from "@/features/stellen/SucheForm";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { usePersistedLayout } from "@/hooks/usePersistedLayout";
import { useSetHeaderActions } from "@/lib/header-actions";
import { api } from "@/lib/api";
import type { JobOut, SortOrder, SortSpalte } from "@/types/api";

export function StellenPage() {
  const headerActions = useSetHeaderActions(<SucheForm />);
  const [params, setParams] = useSearchParams();

  const filter: FilterState = {
    status: params.get("status") ?? "new",
    q: params.get("q") ?? "",
    ort: params.get("ort") ?? "",
    verschwunden: params.get("verschwunden") === "1",
  };
  const sort = (params.get("sort") as SortSpalte) || "id";
  const order = (params.get("order") as SortOrder) || "desc";
  const stelleId = params.get("stelle") ? Number(params.get("stelle")) : null;

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
      <FilterSidebar
        value={filter}
        onChange={(next) =>
          patchParams({
            status: next.status,
            q: next.q,
            ort: next.ort,
            verschwunden: next.verschwunden ? "1" : null,
          })
        }
      />

      <div className="min-w-0 flex-1">
        {/* Ab md: Liste und Detail nebeneinander, verschiebbar. Darunter:
            nur die Liste, Detail als Sheet von unten. */}
        <div className="hidden h-full md:block">
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

        <div className="md:hidden">
          <StellenTable
            stellen={stellen}
            isLoading={jobsQuery.isLoading}
            sort={sort}
            order={order}
            onSortChange={onSortChange}
            selectedId={stelleId}
            onSelectRow={onSelectRow}
          />
          <Sheet
            open={isMobile && stelleId !== null}
            onOpenChange={(offen) => {
              if (!offen) patchParams({ stelle: null });
            }}
          >
            <SheetContent side="bottom" className="h-[85vh]">
              <SheetHeader className="sr-only">
                <SheetTitle>Stellendetail</SheetTitle>
              </SheetHeader>
              <div className="h-full overflow-y-auto">
                <StellenDetail stelle={detailQuery.data} isLoading={detailQuery.isFetching} />
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </div>
  );
}
