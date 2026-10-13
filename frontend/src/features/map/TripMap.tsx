import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Map, {
  Layer,
  Popup,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from "react-map-gl/maplibre";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Corridor, Trip } from "@/api/types";
import { formatClock } from "@/lib/format";
import { LEVEL_LABEL } from "@/lib/risk";
import { CorridorLayer } from "./CorridorLayer";
import { checkpointsGeoJson, segmentsGeoJson, tripBounds, trucksGeoJson } from "./geojson";
import {
  BASEMAP,
  US_VIEW,
  casingLayer,
  checkpointLayer,
  hitLayer,
  lineLayer,
  truckLabelLayer,
  truckLayer,
} from "./layers";

interface Props {
  trip?: Trip;
  corridor?: Corridor;
  hour: number;
  selectedId?: string;
  onSelect: (routeId: string) => void;
}

// maplibre 6 resolves its worker relative to its own module, which breaks once Vite pre-bundles it.
maplibregl.setWorkerUrl(workerUrl);

const EMPTY = { type: "FeatureCollection" as const, features: [] };
const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function TripMap({ trip, corridor, hour, selectedId = "", onSelect }: Props) {
  const mapRef = useRef<MapRef>(null);
  const [loaded, setLoaded] = useState(false);
  const [hover, setHover] = useState<{ route: string; index: number } | null>(null);

  const segments = useMemo(() => (trip ? segmentsGeoJson(trip) : EMPTY), [trip]);
  const checkpoints = useMemo(() => (trip ? checkpointsGeoJson(trip) : EMPTY), [trip]);
  const startMs = trip ? Date.parse(trip.timeline_start) : 0;
  const trucks = useMemo(
    () => (trip ? trucksGeoJson(trip, startMs, hour) : EMPTY),
    [trip, startMs, hour],
  );

  useEffect(() => {
    if (!loaded || !trip) return;
    mapRef.current?.fitBounds(tripBounds(trip), {
      padding: 64,
      duration: reducedMotion() ? 0 : 900,
    });
  }, [loaded, trip]); // the cached trip object is stable, so this refits once per trip

  const onMove = useCallback((e: MapLayerMouseEvent) => {
    const f = e.features?.find((x) => x.layer.id === "checkpoint-dots");
    setHover(f ? { route: String(f.properties.route), index: Number(f.properties.index) } : null);
  }, []);

  const hovered = hover && trip?.routes.find((r) => r.id === hover.route)?.checkpoints[hover.index];

  return (
    <Map
      ref={mapRef}
      mapLib={maplibregl}
      initialViewState={US_VIEW}
      mapStyle={BASEMAP}
      onLoad={() => setLoaded(true)}
      interactiveLayerIds={["route-hit", "checkpoint-dots"]}
      onMouseMove={onMove}
      onMouseLeave={() => setHover(null)}
      onClick={(e) => {
        const id = e.features?.[0]?.properties?.route;
        if (id) onSelect(String(id));
      }}
      cursor={hover ? "pointer" : "grab"}
      attributionControl={{ compact: true }}
      style={{ width: "100%", height: "100%" }}
    >
      <Source id="segments" type="geojson" data={segments}>
        <Layer {...casingLayer(selectedId)} />
        <Layer {...lineLayer(selectedId)} />
        <Layer {...hitLayer} />
      </Source>
      {corridor && trip && <CorridorLayer key={trip.id} corridor={corridor} hour={hour} />}
      <Source id="checkpoints" type="geojson" data={checkpoints}>
        <Layer {...checkpointLayer(selectedId)} />
      </Source>
      <Source id="trucks" type="geojson" data={trucks}>
        <Layer {...truckLayer} />
        <Layer {...truckLabelLayer} />
      </Source>
      {hover && hovered && (
        <Popup
          longitude={hovered.lon}
          latitude={hovered.lat}
          closeButton={false}
          offset={10}
          maxWidth="260px"
        >
          <div className="num text-[12px] leading-relaxed text-ink">
            <strong className="font-display text-[13px]">
              Route {hover.route} · mile {Math.round(hovered.mile)}
            </strong>
            <div>ETA {formatClock(hovered.eta)}</div>
            <div>
              Wind {Math.round(hovered.wind_mph)} mph (gusts {Math.round(hovered.gust_mph)})
            </div>
            <div>
              Rain {hovered.rain_in_hr.toFixed(2)} in/hr · Snow {hovered.snow_in_hr.toFixed(2)}{" "}
              in/hr
            </div>
            <div className="font-semibold">
              {LEVEL_LABEL[hovered.level]}
              {hovered.drivers.length > 0 &&
                ` — ${hovered.drivers.join(", ")}${hovered.load_adjusted ? ", raised by load" : ""}`}
            </div>
          </div>
        </Popup>
      )}
    </Map>
  );
}
