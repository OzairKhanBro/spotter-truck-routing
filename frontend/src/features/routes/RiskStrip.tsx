import type { Route } from "@/api/types";
import { LEVEL_COLOR } from "@/lib/risk";

/** The whole route as one bar, each stretch as wide as its miles. */
export function RiskStrip({ route }: { route: Route }) {
  const total = route.distance_mi || 1;
  return (
    <svg
      viewBox="0 0 100 6"
      preserveAspectRatio="none"
      className="h-1.5 w-full rounded-full"
      aria-hidden
    >
      {route.segments.map((s) => (
        <rect
          key={s.start_mile}
          x={(s.start_mile / total) * 100}
          width={((s.end_mile - s.start_mile) / total) * 100 + 0.05}
          y={0}
          height={6}
          fill={LEVEL_COLOR[s.level]}
        />
      ))}
    </svg>
  );
}
