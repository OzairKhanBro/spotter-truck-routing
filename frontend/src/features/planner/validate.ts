import type { Interval, Place, TripInput } from "@/api/types";

export interface FormState {
  origin: Place | null;
  destination: Place | null;
  departure: string; // <input type="datetime-local"> value, local time
  loadLb: string;
  intervalMi: Interval;
}

const HOUR = 3_600_000;
const MAX_AHEAD = 7 * 24 * HOUR;

export function toLocalInput(d: Date): string {
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export function defaultForm(now = new Date()): FormState {
  const next = new Date(now);
  next.setMinutes(60, 0, 0);
  return {
    origin: null,
    destination: null,
    departure: toLocalInput(next),
    loadLb: "40000",
    intervalMi: 25,
  };
}

const parseLoad = (s: string) => Number(s.replaceAll(",", "").trim());

export function validateForm(f: FormState, now = new Date()): string | null {
  if (!f.origin) return "Pick a start from the list.";
  if (!f.destination) return "Pick a destination from the list.";
  if (f.origin.lat === f.destination.lat && f.origin.lon === f.destination.lon) {
    return "Start and destination are the same place.";
  }
  const departure = new Date(f.departure).getTime();
  if (Number.isNaN(departure) || departure < now.getTime() - HOUR) {
    return "Departure is in the past.";
  }
  if (departure > now.getTime() + MAX_AHEAD) return "Pick a departure within the next 7 days.";
  const load = parseLoad(f.loadLb);
  if (!Number.isFinite(load) || load < 1 || load > 150_000) {
    return "Enter a load between 1 and 150,000 lb.";
  }
  return null;
}

export function toTripInput(f: FormState): TripInput {
  return {
    origin: f.origin!,
    destination: f.destination!,
    departure: new Date(f.departure).toISOString(),
    load_lb: Math.round(parseLoad(f.loadLb)),
    interval_mi: f.intervalMi,
  };
}
