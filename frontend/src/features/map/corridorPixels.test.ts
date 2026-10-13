import { describe, expect, it } from "vite-plus/test";
import type { Corridor } from "@/api/types";
import { corridorPixels } from "./corridorPixels";

const corridor: Corridor = {
  start: "2026-10-14T00:00:00Z",
  bounds: [0, 0, 2, 1],
  cols: 2,
  rows: 1,
  scores: [
    [-1, 0.5],
    [-1, 3.5],
  ],
};

describe("corridorPixels", () => {
  it("leaves masked cells transparent", () => {
    expect(corridorPixels(corridor, 0)[3]).toBe(0);
  });
  it("colors by the level band and strengthens alpha with risk", () => {
    const low = corridorPixels(corridor, 0);
    const severe = corridorPixels(corridor, 1);
    expect([...low.slice(4, 7)]).toEqual([0x5e, 0x9c, 0x76]);
    expect([...severe.slice(4, 7)]).toEqual([0xc8, 0x23, 0x2c]);
    expect(severe[7]).toBeGreaterThan(low[7]);
  });
  it("blends frames for fractional hours", () => {
    expect([...corridorPixels(corridor, 0.5).slice(4, 7)]).toEqual([0xea, 0x7a, 0x1f]); // score 2.0 → high
  });
});
