import { Badge } from "@/components/ui/badge";
import { employerWarnung, formatAlter } from "@/lib/format";
import type { JobOut } from "@/types/api";

/** Kompakte Kennzeichen für Tabellenzeile/Mobil-Karte — Reihenfolge fest:
 * Herkunft, Warnzeichen, Pluspunkte, Eckdaten (wie _stellenliste.html). */
export function JobBadges({ stelle }: { stelle: JobOut }) {
  const quelle = stelle.source_partner || stelle.external_host;
  const warnung = employerWarnung(stelle.employer_kind);
  const ausbildung = stelle.job_kind && stelle.job_kind !== "ARBEIT";
  const frische = formatAlter(stelle.changed_at ?? stelle.posted_at);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {stelle.gone_at && <Badge variant="destructive">nicht mehr verfügbar</Badge>}
      {quelle && <Badge variant="secondary">{quelle}</Badge>}
      {warnung && <Badge variant="destructive">{warnung}</Badge>}
      {ausbildung && <Badge variant="destructive">Ausbildung</Badge>}
      {stelle.homeoffice && <Badge variant="outline">Homeoffice</Badge>}
      {stelle.salary && <Badge variant="outline">{stelle.salary}</Badge>}
      {stelle.contract && <Badge variant="outline">{stelle.contract}</Badge>}
      {stelle.distance_km != null && <Badge variant="outline">{stelle.distance_km} km</Badge>}
      {frische && <Badge variant="outline">{frische}</Badge>}
    </div>
  );
}
