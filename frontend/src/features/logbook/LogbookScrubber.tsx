import { useMemo } from "react";
import type { Trip } from "@/api/types";
import { formatClock, formatHourTick } from "@/lib/format";
import { LEVEL_COLOR, LEVEL_LABEL } from "@/lib/risk";
import { HOUR_MS, TIMELINE_HOURS } from "@/lib/timeline";
import { logbookRows } from "./logbook";

const COL = 10;
const ROW = 16;
const TOP = 4;

interface Props {
  trip: Trip;
  hour: number;
  onHour: (hour: number) => void;
  selectedId?: string;
}

export function LogbookScrubber({ trip, hour, onHour, selectedId }: Props) {
  const startMs = Date.parse(trip.timeline_start);
  const rows = useMemo(() => logbookRows(trip, startMs), [trip, startMs]);
  const width = TIMELINE_HOURS * COL;
  const height = TOP + rows.length * ROW;
  const atMs = startMs + hour * HOUR_MS;
  const ticks = Array.from({ length: TIMELINE_HOURS / 6 + 1 }, (_, i) => i * 6);

  return (
    <section
      aria-label="Forecast timeline"
      className="border-t border-rule bg-paper px-3 pt-2 pb-3 md:px-5"
    >
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <h2 className="field-label mb-0">Forecast · drag through the next 48 hours</h2>
        <p className="num text-[13px] font-semibold" aria-live="polite">
          {formatClock(atMs)}{" "}
          <span className="font-normal text-ink-soft">+{Math.floor(hour)} h</span>
        </p>
      </div>
      <div className="flex gap-2">
        <div className="flex flex-col pt-[3px]" aria-hidden>
          {rows.map((r) => (
            <span
              key={r.id}
              className={`font-display text-[13px] leading-[16px] font-extrabold ${r.id === selectedId ? "text-interstate" : "text-ink-soft"}`}
            >
              {r.id}
            </span>
          ))}
        </div>
        <div className="relative flex-1 rounded-[3px] bg-white ring-1 ring-rule has-[input:focus-visible]:ring-3 has-[input:focus-visible]:ring-interstate">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="none"
            className="block w-full"
            style={{ height: rows.length * 16 + 8 }}
            aria-hidden
          >
            {Array.from({ length: TIMELINE_HOURS + 1 }, (_, h) => {
              const midnight = new Date(startMs + h * HOUR_MS).getHours() === 0;
              return (
                <line
                  key={h}
                  x1={h * COL}
                  x2={h * COL}
                  y1={0}
                  y2={height}
                  stroke={midnight ? "#1E2328" : "#D5DBD6"}
                  strokeWidth={midnight ? 1.2 : h % 6 === 0 ? 0.6 : 0.3}
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
            {rows.map((r, i) =>
              r.cells.map((level, h) =>
                level ? (
                  <line
                    key={`${r.id}-${h}`}
                    x1={h * COL}
                    x2={(h + 1) * COL}
                    y1={TOP + i * ROW + ROW / 2}
                    y2={TOP + i * ROW + ROW / 2}
                    stroke={LEVEL_COLOR[level]}
                    strokeWidth={r.id === selectedId ? 7 : 4}
                    strokeLinecap="butt"
                    vectorEffect="non-scaling-stroke"
                  >
                    <title>{`Route ${r.id}, hour ${h}: ${LEVEL_LABEL[level]}`}</title>
                  </line>
                ) : null,
              ),
            )}
            <line
              x1={hour * COL}
              x2={hour * COL}
              y1={0}
              y2={height}
              stroke="#1E4FA3"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          <input
            type="range"
            min={0}
            max={TIMELINE_HOURS}
            step={0.25}
            value={hour}
            onChange={(e) => onHour(Number(e.target.value))}
            aria-label="Forecast hour"
            aria-valuetext={`${formatClock(atMs)}, ${Math.floor(hour)} hours after departure hour`}
            className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
          />
        </div>
      </div>
      <div className="num relative mt-1 ml-5 h-4 text-[11px] text-ink-soft" aria-hidden>
        {ticks.map((h) => (
          <span
            key={h}
            className={`absolute -translate-x-1/2 whitespace-nowrap ${h % 12 === 0 ? "" : "hidden sm:inline"}`}
            style={{ left: `${(h / TIMELINE_HOURS) * 100}%` }}
          >
            {formatHourTick(startMs + h * HOUR_MS)}
          </span>
        ))}
      </div>
    </section>
  );
}
