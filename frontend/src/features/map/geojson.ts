import type { FeatureCollection, LineString, Point } from "geojson";
import type { LonLat, Trip } from "@/api/types";
import { HOUR_MS, positionAt } from "@/lib/timeline";

export function segmentsGeoJson(trip: Trip): FeatureCollection<LineString> {
  return {
    type: "FeatureCollection",
    features: trip.routes.flatMap((r) =>
      r.segments.map((s) => ({
        type: "Feature" as const,
        properties: { route: r.id, level: s.level },
        geometry: { type: "LineString" as const, coordinates: s.coordinates },
      })),
    ),
  };
}

export function checkpointsGeoJson(trip: Trip): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: trip.routes.flatMap((r) =>
      r.checkpoints.map((c, index) => ({
        type: "Feature" as const,
        properties: { route: r.id, index, level: c.level },
        geometry: { type: "Point" as const, coordinates: [c.lon, c.lat] },
      })),
    ),
  };
}

export function trucksGeoJson(trip: Trip, startMs: number, hour: number): FeatureCollection<Point> {
  const sinceDeparture = (startMs + hour * HOUR_MS - Date.parse(trip.departure)) / 1000;
  return {
    type: "FeatureCollection",
    features: trip.routes.map((r) => {
      const { coord, arrived } = positionAt(r.path, sinceDeparture);
      return {
        type: "Feature" as const,
        properties: { route: r.id, arrived },
        geometry: { type: "Point" as const, coordinates: coord },
      };
    }),
  };
}

export function tripBounds(trip: Trip): [LonLat, LonLat] {
  let [w, s, e, n] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const r of trip.routes)
    for (const [lon, lat] of r.path.coordinates) {
      w = Math.min(w, lon);
      s = Math.min(s, lat);
      e = Math.max(e, lon);
      n = Math.max(n, lat);
    }
  return [
    [w, s],
    [e, n],
  ];
}
