import { describe, expect, it } from "vite-plus/test";
import type { Trip } from "@/api/types";
import { checkpointsGeoJson, segmentsGeoJson, tripBounds, trucksGeoJson } from "./geojson";

const trip = {
  departure: "2026-10-14T00:30:00Z",
  timeline_start: "2026-10-14T00:00:00Z",
  routes: [
    {
      id: "A",
      path: {
        coordinates: [
          [-100, 40],
          [-98, 41],
        ],
        seconds: [0, 7200],
      },
      segments: [
        {
          level: "high",
          start_mile: 0,
          end_mile: 10,
          coordinates: [
            [-100, 40],
            [-98, 41],
          ],
        },
      ],
      checkpoints: [{ mile: 0, lon: -100, lat: 40, level: "low" }],
    },
  ],
} as unknown as Trip;

describe("map geojson", () => {
  it("tags segments with route and level", () => {
    expect(segmentsGeoJson(trip).features[0].properties).toEqual({ route: "A", level: "high" });
  });
  it("indexes checkpoints for hover lookup", () => {
    expect(checkpointsGeoJson(trip).features[0].properties).toMatchObject({
      route: "A",
      index: 0,
      level: "low",
    });
  });
  it("places trucks relative to departure, not timeline start", () => {
    const start = Date.parse(trip.timeline_start);
    expect(trucksGeoJson(trip, start, 0).features[0].geometry.coordinates).toEqual([-100, 40]);
    expect(trucksGeoJson(trip, start, 1.5).features[0].geometry.coordinates).toEqual([-99, 40.5]);
  });
  it("bounds all route paths", () => {
    expect(tripBounds(trip)).toEqual([
      [-100, 40],
      [-98, 41],
    ]);
  });
});
