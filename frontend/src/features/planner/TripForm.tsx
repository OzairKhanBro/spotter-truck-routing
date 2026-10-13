import { useState } from "react";
import type { Interval, TripInput } from "@/api/types";
import { PlaceInput } from "./PlaceInput";
import { type FormState, defaultForm, toTripInput, validateForm } from "./validate";

const INTERVALS: Interval[] = [10, 25, 50];
const EXAMPLE = {
  origin: { label: "Chicago, Illinois, US", lat: 41.87556, lon: -87.62442 },
  destination: { label: "Denver, Colorado, US", lat: 39.73924, lon: -104.98486 },
};

interface Props {
  pending: boolean;
  serverError: string | null;
  onSubmit: (input: TripInput) => void;
}

export function TripForm({ pending, serverError, onSubmit }: Props) {
  const [form, setForm] = useState<FormState>(() => defaultForm());
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        const problem = validateForm(form);
        setError(problem);
        if (!problem) onSubmit(toTripInput(form));
      }}
    >
      <PlaceInput
        id="origin"
        label="From"
        value={form.origin}
        onChange={(origin) => set({ origin })}
      />
      <PlaceInput
        id="destination"
        label="To"
        value={form.destination}
        onChange={(destination) => set({ destination })}
      />

      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_7.5rem] sm:gap-3">
        <div>
          <label htmlFor="departure" className="field-label">
            Leaving at
          </label>
          <input
            id="departure"
            type="datetime-local"
            className="field-input num"
            value={form.departure}
            onChange={(e) => set({ departure: e.target.value })}
          />
        </div>
        <div>
          <label htmlFor="load" className="field-label">
            Load weight (lb)
          </label>
          <input
            id="load"
            inputMode="numeric"
            className="field-input num"
            value={form.loadLb}
            onChange={(e) => set({ loadLb: e.target.value })}
          />
        </div>
      </div>

      <fieldset>
        <legend className="field-label">Check weather every</legend>
        <div className="grid grid-cols-3 overflow-hidden rounded-md border border-rule bg-white">
          {INTERVALS.map((mi) => (
            <label
              key={mi}
              className="num cursor-pointer py-2.5 text-center text-sm has-checked:bg-ink has-checked:text-sign-white has-focus-visible:outline-3 has-focus-visible:outline-interstate"
            >
              <input
                type="radio"
                name="interval"
                className="sr-only"
                checked={form.intervalMi === mi}
                onChange={() => set({ intervalMi: mi })}
              />
              {mi} mi
            </label>
          ))}
        </div>
      </fieldset>

      {(error ?? serverError) && (
        <p
          role="alert"
          className="rounded-md border-l-4 border-risk-severe bg-white px-3 py-2 text-sm"
        >
          {error ?? serverError}
        </p>
      )}

      <div className="flex items-center gap-3">
        <button type="submit" className="btn-primary flex-1" disabled={pending}>
          {pending ? "Planning routes…" : "Plan routes"}
        </button>
        <button type="button" className="chip" onClick={() => set(EXAMPLE)}>
          Try Chicago → Denver
        </button>
      </div>
    </form>
  );
}
