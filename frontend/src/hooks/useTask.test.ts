import { describe, expect, it } from "vitest";
import { taskRefetchIntervalMs } from "@/hooks/useTask";
import type { TaskOut } from "@/types/api";

function task(status: TaskOut["status"]): TaskOut {
  return { id: "1", beschreibung: "Testlauf", status, meldung: "", ergebnis: null };
}

describe("taskRefetchIntervalMs", () => {
  it("pollt weiter, solange kein Task-Objekt vorliegt (noch nicht geladen)", () => {
    expect(taskRefetchIntervalMs(undefined)).toBe(1000);
  });

  it("pollt weiter, während der Task läuft", () => {
    expect(taskRefetchIntervalMs(task("läuft"))).toBe(1000);
  });

  it("stoppt das Polling, sobald der Task fertig ist", () => {
    expect(taskRefetchIntervalMs(task("fertig"))).toBe(false);
  });

  it("stoppt das Polling, sobald der Task einen Fehler meldet", () => {
    expect(taskRefetchIntervalMs(task("fehler"))).toBe(false);
  });
});
