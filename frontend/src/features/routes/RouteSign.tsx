import type { Route } from "@/api/types";
import { formatClock, formatDuration, formatMiles } from "@/lib/format";
import { RiskStrip } from "./RiskStrip";

interface Props {
  route: Route;
  recommended: boolean;
  reason: string;
  selected: boolean;
  onSelect: () => void;
}

export function RouteSign({ route, recommended, reason, selected, onSelect }: Props) {
  const m = route.summary.miles_by_level;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`block w-full rounded-lg text-left transition-transform duration-150 hover:-translate-y-px ${selected ? "ring-4 ring-interstate" : ""}`}
    >
      <div className="rounded-lg border-2 border-sign-white bg-guide px-4 pt-3 pb-3.5 text-sign-white shadow-[0_0_0_2px_var(--color-guide)]">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-[28px] leading-none font-extrabold">{route.id}</span>
          <span className="truncate font-display text-lg leading-tight font-bold">
            {route.label}
          </span>
        </div>
        <div className="num mt-2 flex flex-wrap gap-x-4 text-[13px] opacity-95">
          <span>{formatMiles(route.distance_mi)}</span>
          <span>{formatDuration(route.duration_s)}</span>
          <span>arrive {formatClock(route.arrival)}</span>
        </div>
        <div className="mt-3 rounded-full bg-sign-white/20 p-0.5">
          <RiskStrip route={route} />
        </div>
        <p className="num mt-2 text-[12px] opacity-90">
          {formatMiles(m.no_travel)} no travel · {formatMiles(m.severe)} severe ·{" "}
          {formatMiles(m.high)} high · avg {route.summary.avg_risk.toFixed(2)}/4
        </p>
      </div>
      {recommended && (
        <div className="mx-3 rounded-b-md border-2 border-t-0 border-ink bg-sign-white px-3 py-1.5 text-ink">
          <span className="font-display text-xs font-extrabold tracking-[0.12em] uppercase">
            Recommended
          </span>
          <span className="ml-2 text-[13px]">{reason}</span>
        </div>
      )}
    </button>
  );
}
