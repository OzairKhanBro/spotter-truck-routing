import type { Level } from "@/lib/risk";

export type LonLat = [number, number];
export type Interval = 10 | 25 | 50;

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface TripInput {
  origin: Place;
  destination: Place;
  departure: string; // ISO-8601 with offset
  load_lb: number;
  interval_mi: Interval;
}

export interface Checkpoint {
  mile: number;
  lon: number;
  lat: number;
  eta: string;
  wind_mph: number;
  gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  level: Level;
  drivers: Array<"wind" | "rain" | "snow">;
  load_adjusted: boolean;
}

export interface Segment {
  level: Level;
  start_mile: number;
  end_mile: number;
  coordinates: LonLat[];
}

export interface Route {
  id: string;
  label: string;
  distance_mi: number;
  duration_s: number;
  arrival: string;
  rank: number;
  path: { coordinates: LonLat[]; seconds: number[] };
  segments: Segment[];
  checkpoints: Checkpoint[];
  summary: { miles_by_level: Record<Level, number>; avg_risk: number; max_level: Level };
}

export interface Trip {
  id: string;
  created_at: string;
  origin: Place;
  destination: Place;
  departure: string;
  load_lb: number;
  interval_mi: Interval;
  timeline_start: string;
  routes: Route[];
  recommendation: { route_id: string; reason: string; all_blocked: boolean };
  notes: string[];
}

export interface Corridor {
  start: string;
  bounds: [west: number, south: number, east: number, north: number];
  cols: number;
  rows: number;
  scores: number[][]; // [hour][row * cols + col], -1 = no data
}
