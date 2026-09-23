import { Button } from "@/components/ui/button";
import { STATUS_LABEL } from "@/lib/format";
import type { Status } from "@/types/api";

const REITER: { wert: string; label: string }[] = [
  { wert: "new", label: STATUS_LABEL.new },
  { wert: "selected", label: STATUS_LABEL.selected },
  { wert: "rejected", label: STATUS_LABEL.rejected },
  { wert: "", label: "alle" },
];

interface Props {
  value: string;
  anzahl: Record<Status, number> | undefined;
  onChange: (status: string) => void;
}

export function StatusTabs({ value, anzahl, onChange }: Props) {
  function zahl(wert: string): number | undefined {
    if (!anzahl) return undefined;
    if (wert === "") return anzahl.new + anzahl.selected + anzahl.rejected;
    return anzahl[wert as Status];
  }

  return (
    <div role="tablist" aria-label="Status" className="flex flex-wrap gap-1">
      {REITER.map(({ wert, label }) => (
        <Button
          key={wert || "alle"}
          role="tab"
          aria-selected={value === wert}
          size="sm"
          variant={value === wert ? "secondary" : "ghost"}
          onClick={() => onChange(wert)}
        >
          {label}
          {zahl(wert) !== undefined && (
            <span className="text-xs text-muted-foreground tabular-nums">{zahl(wert)}</span>
          )}
        </Button>
      ))}
    </div>
  );
}
