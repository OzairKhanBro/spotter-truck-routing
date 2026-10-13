import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { geocodeQuery } from "@/api/queries";
import type { Place } from "@/api/types";
import { useDebouncedValue } from "@/lib/useDebouncedValue";

interface Props {
  id: string;
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
}

export function PlaceInput({ id, label, value, onChange }: Props) {
  const [text, setText] = useState(value?.label ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const q = useDebouncedValue(text.trim(), 250);

  // Show the chosen place's label when the value is set from outside (e.g. the example button).
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    if (value) setText(value.label);
  }

  const searching = open && q.length >= 3 && q !== value?.label;
  const search = useQuery({ ...geocodeQuery(q), enabled: searching });
  const options = search.data ?? [];
  const listId = `${id}-options`;

  const choose = (place: Place) => {
    onChange(place);
    setText(place.label);
    setOpen(false);
  };

  return (
    <div className="relative">
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <input
        id={id}
        className="field-input"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={searching && options.length > 0}
        aria-controls={listId}
        aria-activedescendant={searching && options[active] ? `${id}-opt-${active}` : undefined}
        autoComplete="off"
        placeholder="City, address, or ZIP"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChange(null);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (!searching || options.length === 0) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((i) => Math.min(i + 1, options.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(options[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {searching && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-rule bg-white py-1 shadow-lg"
        >
          {search.isPending && <li className="px-3 py-2 text-ink-soft">Searching…</li>}
          {search.isError && <li className="px-3 py-2 text-ink-soft">{search.error.message}</li>}
          {search.isSuccess && options.length === 0 && (
            <li className="px-3 py-2 text-ink-soft">No places match. Try a city and state.</li>
          )}
          {options.map((place, i) => (
            <li
              key={`${place.lat},${place.lon},${i}`}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={`cursor-pointer px-3 py-2 ${i === active ? "bg-paper" : ""}`}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(place)}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
