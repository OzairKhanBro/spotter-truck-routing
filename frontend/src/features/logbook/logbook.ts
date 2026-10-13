import type { Trip } from "@/api/types";
import type { Level } from "@/lib/risk";
import { TIMELINE_HOURS, levelDuring } from "@/lib/timeline";

/** One row per route: the worst level the truck meets in each timeline hour, null when parked. */
export function logbookRows(
  trip: Trip,
  startMs: number,
): { id: string; cells: (Level | null)[] }[] {
  return trip.routes.map((r) => ({
    id: r.id,
    cells: Array.from({ length: TIMELINE_HOURS }, (_, h) => levelDuring(r, startMs, h)),
  }));
}
