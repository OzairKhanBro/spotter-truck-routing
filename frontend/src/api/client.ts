import type { Corridor, Place, Trip, TripInput } from "./types";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg ?? "").join("; ");
  return `The server returned an error (${status}). Try again.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { headers: { "content-type": "application/json" }, ...init });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, messageFrom(body, res.status));
  return body as T;
}

export const api = {
  geocode: (q: string) => request<Place[]>(`/geocode?q=${encodeURIComponent(q)}`),
  createTrip: (input: TripInput) =>
    request<Trip>("/trips", { method: "POST", body: JSON.stringify(input) }),
  trip: (id: string) => request<Trip>(`/trips/${id}`),
  corridor: (id: string) => request<Corridor>(`/trips/${id}/corridor`),
};
