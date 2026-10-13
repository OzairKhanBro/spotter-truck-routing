import { describe, expect, it } from "vite-plus/test";
import type { Trip } from "@/api/types";
import { logbookRows } from "./logbook";

const T0 = Date.parse("2026-10-14T00:00:00Z");
const cp = (h: number, level: string) => ({
  eta: new Date(T0 + h * 3_600_000).toISOString(),
  level,
});
const trip = {
  routes: [{ id: "A", checkpoints: [cp(0, "low"), cp(1.5, "high"), cp(3, "low")] }],
} as unknown as Trip;

describe("logbookRows", () => {
  it("has 48 hourly cells per route, empty after arrival", () => {
    const [row] = logbookRows(trip, T0);
    expect(row.cells).toHaveLength(48);
    expect(row.cells.slice(0, 4)).toEqual(["low", "high", "high", "low"]);
    expect(row.cells[4]).toBeNull();
  });
});
