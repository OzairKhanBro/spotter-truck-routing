const clock = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  hour: "numeric",
  minute: "2-digit",
});
const hourTick = new Intl.DateTimeFormat(undefined, { hour: "numeric" });
const day = new Intl.DateTimeFormat(undefined, { weekday: "short" });

export function formatDuration(seconds: number): string {
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? `${h} h ${m} m` : `${m} m`;
}

export function formatMiles(mi: number): string {
  return `${mi.toLocaleString(undefined, { maximumFractionDigits: mi < 10 ? 1 : 0 })} mi`;
}

export const formatClock = (t: string | number): string => clock.format(new Date(t));

/** Logbook tick: weekday at local midnight, otherwise the hour ("6 PM"). */
export function formatHourTick(ms: number): string {
  const d = new Date(ms);
  return d.getHours() === 0 ? day.format(d) : hourTick.format(d);
}

export const localZoneName = (): string =>
  new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
    .formatToParts(new Date())
    .find((p) => p.type === "timeZoneName")?.value ?? "";
