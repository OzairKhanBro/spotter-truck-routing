import type { LonLat, Route } from "@/api/types";
import { type Level, maxLevel } from "./risk";

export const HOUR_MS = 3_600_000;
export const TIMELINE_HOURS = 48;

/** Where the truck is `t` seconds after departure. */
export function positionAt(path: Route["path"], t: number): { coord: LonLat; arrived: boolean } {
  const { coordinates: c, seconds: s } = path;
  const last = s.length - 1;
  if (t <= 0) return { coord: c[0], arrived: false };
  if (t >= s[last]) return { coord: c[last], arrived: true };
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (s[mid] <= t) lo = mid;
    else hi = mid;
  }
  const span = s[hi] - s[lo];
  const f = span > 0 ? (t - s[lo]) / span : 0;
  return {
    coord: [c[lo][0] + (c[hi][0] - c[lo][0]) * f, c[lo][1] + (c[hi][1] - c[lo][1]) * f],
    arrived: false,
  };
}

/** Worst risk the truck meets during timeline hour `hour`, or null if it isn't driving then. */
export function levelDuring(
  route: Pick<Route, "checkpoints">,
  startMs: number,
  hour: number,
): Level | null {
  const from = startMs + hour * HOUR_MS;
  const to = from + HOUR_MS;
  const times = route.checkpoints.map((c) => Date.parse(c.eta));
  if (to <= times[0] || from > times[times.length - 1]) return null;
  let worst: Level | null = null;
  for (let i = 0; i < times.length; i++) {
    const level = route.checkpoints[i].level;
    if (times[i] >= from && times[i] < to) worst = worst ? maxLevel(worst, level) : level;
  }
  if (worst) return worst;
  const next = times.findIndex((t) => t >= to);
  return maxLevel(route.checkpoints[next - 1].level, route.checkpoints[next].level);
}
