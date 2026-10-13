import type { Route } from "@/api/types";
import { formatClock } from "@/lib/format";
import { LEVEL_COLOR, LEVEL_LABEL } from "@/lib/risk";

export function CheckpointTable({ route }: { route: Route }) {
  return (
    <section aria-labelledby="checkpoints-heading">
      <h2 id="checkpoints-heading" className="field-label">
        Route {route.id} checkpoints
      </h2>
      <div className="max-h-[42svh] overflow-auto rounded-md border border-rule bg-white">
        <table className="num w-full text-[12.5px]">
          <thead className="sticky top-0 bg-white text-left text-ink-soft">
            <tr>
              <th className="px-2 py-1.5 font-semibold">Mile</th>
              <th className="px-2 py-1.5 font-semibold">ETA</th>
              <th className="px-2 py-1.5 font-semibold">Wind</th>
              <th className="px-2 py-1.5 font-semibold">Rain</th>
              <th className="px-2 py-1.5 font-semibold">Snow</th>
              <th className="px-2 py-1.5 font-semibold">Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((c) => (
              <tr key={c.mile} className="border-t border-rule">
                <td className="px-2 py-1.5">{Math.round(c.mile)}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">{formatClock(c.eta)}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">
                  {Math.round(c.wind_mph)}{" "}
                  <span className="text-ink-soft">g{Math.round(c.gust_mph)}</span>
                </td>
                <td className="px-2 py-1.5">{c.rain_in_hr.toFixed(2)}</td>
                <td className="px-2 py-1.5">{c.snow_in_hr.toFixed(2)}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">
                  <span
                    className="mr-1.5 inline-block size-2.5 rounded-full align-middle"
                    style={{ background: LEVEL_COLOR[c.level] }}
                  />
                  {LEVEL_LABEL[c.level]}
                  {c.drivers.length > 0 && (
                    <span className="text-ink-soft">
                      {" "}
                      · {c.drivers.join(", ")}
                      {c.load_adjusted ? " + load" : ""}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[12px] text-ink-soft">
        Wind in mph (g = gusts, not scored). Rain and snow in in/hr.
      </p>
    </section>
  );
}
