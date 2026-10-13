import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const geocodeQuery = (q: string) =>
  queryOptions({
    queryKey: ["geocode", q.toLowerCase()],
    queryFn: () => api.geocode(q),
    staleTime: Infinity,
  });

export const tripQuery = (id: string) =>
  queryOptions({ queryKey: ["trip", id], queryFn: () => api.trip(id), staleTime: Infinity });

export const corridorQuery = (id: string) =>
  queryOptions({
    queryKey: ["trip", id, "corridor"],
    queryFn: () => api.corridor(id),
    staleTime: Infinity,
  });

export function useCreateTrip() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createTrip,
    onSuccess: (trip) => queryClient.setQueryData(tripQuery(trip.id).queryKey, trip),
  });
}
