import type { Corridor } from "@/api/types";
import { LEVEL_COLOR, LEVELS } from "@/lib/risk";

const RGB = LEVELS.map((level) => {
  const n = Number.parseInt(LEVEL_COLOR[level].slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255] as const;
});

/** RGBA for each grid cell at a (possibly fractional) hour. Color = level band, alpha grows with risk. */
export function corridorPixels(corridor: Corridor, hour: number): Uint8ClampedArray<ArrayBuffer> {
  const last = corridor.scores.length - 1;
  const h0 = Math.min(Math.max(Math.floor(hour), 0), last);
  const h1 = Math.min(h0 + 1, last);
  const f = hour - h0;
  const a = corridor.scores[h0];
  const b = corridor.scores[h1];
  const out = new Uint8ClampedArray(a.length * 4);
  for (let k = 0; k < a.length; k++) {
    if (a[k] < 0 || b[k] < 0) continue;
    const score = a[k] + (b[k] - a[k]) * f;
    const [r, g, bl] = RGB[Math.min(Math.floor(score), 4)];
    out.set([r, g, bl, Math.round(255 * Math.min(0.12 + score * 0.18, 0.85))], k * 4);
  }
  return out;
}
