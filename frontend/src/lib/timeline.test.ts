import { describe, expect, it } from "vite-plus/test";
import type { Checkpoint, Route } from "@/api/types";
import { HOUR_MS, levelDuring, positionAt } from "./timeline";

const path = {
  coordinates: [
    [0, 0],
    [1, 0],
    [2, 0],
  ] as [number, number][],
  seconds: [0, 3600, 5400],
};

describe("positionAt", () => {
  it("stays at the origin before departure", () => {
    expect(positionAt(path, -100)).toEqual({ coord: [0, 0], arrived: false });
  });
  it("interpolates by drive time", () => {
    expect(positionAt(path, 4500).coord).toEqual([1.5, 0]);
  });
  it("parks at the destination after arrival", () => {
    expect(positionAt(path, 9999)).toEqual({ coord: [2, 0], arrived: true });
  });
});

const T0 = Date.parse("2026-10-14T00:00:00Z");
const cp = (minutes: number, level: Checkpoint["level"]): Checkpoint => ({
  mile: minutes,
  lon: 0,
  lat: 0,
  eta: new Date(T0 + minutes * 60_000).toISOString(),
  wind_mph: 0,
  gust_mph: 0,
  rain_in_hr: 0,
  snow_in_hr: 0,
  level,
  drivers: [],
  load_adjusted: false,
});
const route = {
  checkpoints: [cp(30, "low"), cp(80, "severe"), cp(200, "moderate"), cp(320, "low")],
} as Route;

describe("levelDuring", () => {
  it("is null before departure and after arrival", () => {
    expect(levelDuring(route, T0 - HOUR_MS, 0)).toBeNull();
    expect(levelDuring(route, T0, 6)).toBeNull();
  });
  it("takes the worst checkpoint inside the hour", () => {
    expect(levelDuring(route, T0, 1)).toBe("severe");
  });
  it("uses the surrounding stretch when no checkpoint falls inside the hour", () => {
    expect(levelDuring(route, T0, 2)).toBe("severe"); // 120–180 min between 80 (severe) and 200 (moderate)
  });
});
