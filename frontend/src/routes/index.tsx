import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useCreateTrip } from "@/api/queries";
import { MultiStepLoader } from "@/components/ui/multi-step-loader";
import { TripForm } from "@/features/planner/TripForm";

export const Route = createFileRoute("/")({ component: PlanPage });

const PLAN_STEPS = [
  { text: "Finding three truck routes" },
  { text: "Placing weather checkpoints" },
  { text: "Reading the forecast at each ETA" },
  { text: "Scoring risk for your load" },
  { text: "Picking the safest route" },
];

function PlanPage() {
  const navigate = useNavigate();
  const createTrip = useCreateTrip();

  return (
    <div className="panel">
      <header>
        <p className="font-display text-xs font-bold tracking-[0.14em] text-guide uppercase">
          Weather-aware truck routing
        </p>
        <h1 className="mt-1 font-display text-[28px] leading-tight font-extrabold">Plan a run</h1>
        <p className="mt-2 text-ink-soft">
          Compare three truck routes against the forecast at the time you'll reach each stretch.
        </p>
      </header>
      <TripForm
        pending={createTrip.isPending}
        serverError={createTrip.error?.message ?? null}
        onSubmit={(input) =>
          createTrip.mutate(input, {
            onSuccess: (trip) => navigate({ to: "/trips/$tripId", params: { tripId: trip.id } }),
          })
        }
      />
      <MultiStepLoader
        loadingStates={PLAN_STEPS}
        loading={createTrip.isPending}
        duration={1400}
        loop={false}
      />
    </div>
  );
}
