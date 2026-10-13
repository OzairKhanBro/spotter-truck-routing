import { useEffect, useMemo } from "react";
import { Layer, Source, type SourceProps, useMap } from "react-map-gl/maplibre";
import type { CanvasSource } from "maplibre-gl";
import type { Corridor } from "@/api/types";
import { corridorPixels } from "./corridorPixels";
import { heatLayer } from "./layers";

export function CorridorLayer({ corridor, hour }: { corridor: Corridor; hour: number }) {
  const { current: map } = useMap();
  const canvas = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = corridor.cols;
    c.height = corridor.rows;
    return c;
  }, [corridor]);

  useEffect(() => {
    canvas
      .getContext("2d")!
      .putImageData(
        new ImageData(corridorPixels(corridor, hour), corridor.cols, corridor.rows),
        0,
        0,
      );
    const source = map?.getSource("corridor") as CanvasSource | undefined;
    if (!source) return;
    // A paused canvas source only re-reads its pixels while playing: play for one frame, then pause.
    source.play();
    map!.triggerRepaint();
    const id = requestAnimationFrame(() => requestAnimationFrame(() => source.pause()));
    return () => cancelAnimationFrame(id);
  }, [canvas, corridor, hour, map]);

  const [w, s, e, n] = corridor.bounds;
  // maplibre supports canvas sources at runtime; react-map-gl's SourceProps union omits the type.
  const source = {
    id: "corridor",
    type: "canvas",
    canvas,
    animate: false,
    coordinates: [
      [w, n],
      [e, n],
      [e, s],
      [w, s],
    ],
  } as unknown as SourceProps;
  return (
    <Source {...source}>
      <Layer {...heatLayer} beforeId="route-casing" />
    </Source>
  );
}
