import { Outlet, createRootRouteWithContext } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import { TripStage } from "@/features/stage/TripStage";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: Shell,
});

function Shell() {
  return (
    <div className="grid h-full grid-rows-[52svh_1fr] md:grid-cols-[420px_1fr] md:grid-rows-1">
      <aside className="order-2 min-h-0 overflow-y-auto border-rule bg-paper md:order-1 md:border-r">
        <Outlet />
      </aside>
      <main className="order-1 min-h-0 md:order-2" aria-label="Route map">
        <TripStage />
      </main>
    </div>
  );
}
