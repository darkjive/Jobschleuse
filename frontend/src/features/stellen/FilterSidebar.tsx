import { useEffect, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDebouncedCallback } from "@/hooks/useDebouncedCallback";

export interface FilterState {
  status: string;
  q: string;
  ort: string;
  verschwunden: boolean;
}

interface Props {
  value: FilterState;
  onChange: (next: FilterState) => void;
}

/** Text-Filter (Suche, Ort) laufen debounced — Status/Checkbox sofort,
 * wie im bisherigen HTMX-Formular (`hx-trigger="submit, change delay:300ms"`). */
export function FilterSidebar({ value, onChange }: Props) {
  const [q, setQ] = useState(value.q);
  const [ort, setOrt] = useState(value.ort);
  const debouncedChange = useDebouncedCallback(onChange, 300);

  useEffect(() => setQ(value.q), [value.q]);
  useEffect(() => setOrt(value.ort), [value.ort]);

  return (
    <aside className="flex w-56 shrink-0 flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="filter-status">Status</Label>
        <Select
          value={value.status || "alle"}
          onValueChange={(status) => onChange({ ...value, status: status === "alle" ? "" : status })}
        >
          <SelectTrigger id="filter-status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="alle">alle</SelectItem>
            <SelectItem value="new">neu</SelectItem>
            <SelectItem value="selected">ausgewählt</SelectItem>
            <SelectItem value="rejected">aussortiert</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="filter-q">Suche</Label>
        <Input
          id="filter-q"
          placeholder="Titel oder Firma"
          value={q}
          onChange={(event) => {
            setQ(event.target.value);
            debouncedChange({ ...value, q: event.target.value });
          }}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="filter-ort">Ort</Label>
        <Input
          id="filter-ort"
          placeholder="z. B. Darmstadt"
          value={ort}
          onChange={(event) => {
            setOrt(event.target.value);
            debouncedChange({ ...value, ort: event.target.value });
          }}
        />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={value.verschwunden}
          onCheckedChange={(checked) => onChange({ ...value, verschwunden: checked === true })}
        />
        auch verschwundene zeigen
      </label>
    </aside>
  );
}
