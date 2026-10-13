import { useState } from "react";
import { useMatch, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { corridorQuery, tripQuery } from "@/api/queries";
import { LogbookScrubber } from "@/features/logbook/LogbookScrubber";
import { TripMap } from "@/features/map/TripMap";

export function TripStage() {
  const match = useMatch({ from: "/trips/$tripId", shouldThrow: false });
  const tripId = match?.params.tripId;
  const routeParam = match?.search.route;
  const navigate = useNavigate();
  // The hour belongs to one trip: a new trip starts back at departure without remounting the map.
  const [scrub, setScrub] = useState({ tripId, hour: 0 });
  const hour = scrub.tripId === tripId ? scrub.hour : 0;

  const trip = useQuery({ ...tripQuery(tripId ?? ""), enabled: !!tripId }).data;
  const corridorResult = useQuery({ ...corridorQuery(tripId ?? ""), enabled: !!trip });
  const corridor = corridorResult.data;
  const selectedId = routeParam ?? trip?.recommendation.route_id;

  return (
    <div className="flex h-full flex-col">
      <div className="relative min-h-0 flex-1">
        <TripMap
          trip={tripId ? trip : undefined}
          corridor={tripId ? corridor : undefined}
          hour={hour}
          selectedId={selectedId}
          onSelect={(route) =>
            tripId &&
            navigate({ to: "/trips/$tripId", params: { tripId }, search: { route }, replace: true })
          }
        />
        {trip && corridorResult.isPending && (
          <p className="chip absolute top-3 left-3">Loading the 48-hour forecast corridor…</p>
        )}
        {trip && corridorResult.isError && (
          <p role="alert" className="chip absolute top-3 left-3">
            Heatmap unavailable: {corridorResult.error.message}
          </p>
        )}
      </div>
      {tripId && trip && (
        <LogbookScrubber
          trip={trip}
          hour={hour}
          onHour={(h) => setScrub({ tripId, hour: h })}
          selectedId={selectedId}
        />
      )}
    </div>
  );
}
