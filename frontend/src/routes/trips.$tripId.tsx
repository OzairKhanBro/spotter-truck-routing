import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useSuspenseQuery } from "@tanstack/react-query";
import { tripQuery } from "@/api/queries";
import { CheckpointTable } from "@/features/routes/CheckpointTable";
import { RouteSign } from "@/features/routes/RouteSign";
import { formatClock, localZoneName } from "@/lib/format";

export const Route = createFileRoute("/trips/$tripId")({
  validateSearch: (search: Record<string, unknown>): { route?: string } => ({
    route: typeof search.route === "string" ? search.route : undefined,
  }),
  loader: ({ context: { queryClient }, params }) =>
    queryClient.ensureQueryData(tripQuery(params.tripId)),
  component: TripPanel,
  errorComponent: ({ error }) => (
    <div className="panel">
      <p role="alert">{(error as Error).message}</p>
      <Link to="/" className="btn-primary">
        Plan a new trip
      </Link>
    </div>
  ),
});

function TripPanel() {
  const { tripId } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { data: trip } = useSuspenseQuery(tripQuery(tripId));
  const selectedId = search.route ?? trip.recommendation.route_id;
  const selected = trip.routes.find((r) => r.id === selectedId) ?? trip.routes[0];
  const ranked = [...trip.routes].sort((a, b) => a.rank - b.rank);

  return (
    <div className="panel">
      <header>
        <Link
          to="/"
          className="text-[13px] font-medium text-interstate underline-offset-2 hover:underline"
        >
          ← Plan another trip
        </Link>
        <h1 className="mt-2 font-display text-xl leading-snug font-extrabold">
          {trip.origin.label} → {trip.destination.label}
        </h1>
        <p className="num mt-1 text-[13px] text-ink-soft">
          Leaving {formatClock(trip.departure)} · {trip.load_lb.toLocaleString()} lb · checks every{" "}
          {trip.interval_mi} mi · times in {localZoneName()}
        </p>
      </header>

      {trip.recommendation.all_blocked && (
        <p
          role="alert"
          className="rounded-md border-l-4 border-risk-no-travel bg-white px-3 py-2 text-sm"
        >
          Every route crosses No Travel conditions at this departure time. Leave later — drag the
          timeline to see when the corridor clears.
        </p>
      )}
      {trip.notes.map((note) => (
        <p key={note} className="text-sm text-ink-soft">
          {note}
        </p>
      ))}

      <div className="flex flex-col gap-4">
        {ranked.map((route) => (
          <RouteSign
            key={route.id}
            route={route}
            recommended={route.id === trip.recommendation.route_id}
            reason={trip.recommendation.reason}
            selected={route.id === selected.id}
            onSelect={() => navigate({ search: { route: route.id }, replace: true })}
          />
        ))}
      </div>

      <CheckpointTable route={selected} />
    </div>
  );
}
