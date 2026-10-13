import type { LayerProps } from "react-map-gl/maplibre";
import type { ExpressionSpecification } from "maplibre-gl";
import { LEVEL_COLOR } from "@/lib/risk";

export const BASEMAP = "https://tiles.openfreemap.org/styles/positron";
export const US_VIEW = { longitude: -97.5, latitude: 39.2, zoom: 3.3 };

const levelColor: ExpressionSpecification = [
  "match",
  ["get", "level"],
  "low",
  LEVEL_COLOR.low,
  "moderate",
  LEVEL_COLOR.moderate,
  "high",
  LEVEL_COLOR.high,
  "severe",
  LEVEL_COLOR.severe,
  "no_travel",
  LEVEL_COLOR.no_travel,
  "#888888",
];
const isSelected = (id: string): ExpressionSpecification => ["==", ["get", "route"], id];

export const casingLayer = (id: string): LayerProps => ({
  id: "route-casing",
  type: "line",
  layout: {
    "line-cap": "round",
    "line-join": "round",
    "line-sort-key": ["case", isSelected(id), 1, 0],
  },
  paint: {
    "line-color": ["case", isSelected(id), "#1E4FA3", "#1E2328"],
    "line-width": [
      "interpolate",
      ["linear"],
      ["zoom"],
      4,
      ["case", isSelected(id), 7, 4],
      9,
      ["case", isSelected(id), 12, 7],
    ],
    "line-opacity": ["case", isSelected(id), 1, 0.35],
  },
});

export const lineLayer = (id: string): LayerProps => ({
  id: "route-line",
  type: "line",
  layout: {
    "line-cap": "round",
    "line-join": "round",
    "line-sort-key": ["case", isSelected(id), 1, 0],
  },
  paint: {
    "line-color": levelColor,
    "line-width": [
      "interpolate",
      ["linear"],
      ["zoom"],
      4,
      ["case", isSelected(id), 4, 2],
      9,
      ["case", isSelected(id), 7, 4],
    ],
    "line-opacity": ["case", isSelected(id), 1, 0.6],
  },
});

export const hitLayer: LayerProps = {
  id: "route-hit",
  type: "line",
  paint: { "line-width": 18, "line-opacity": 0 },
};

export const checkpointLayer = (id: string): LayerProps => ({
  id: "checkpoint-dots",
  type: "circle",
  paint: {
    "circle-color": levelColor,
    "circle-radius": ["case", isSelected(id), 5, 2.5],
    "circle-stroke-color": "#FAFAF7",
    "circle-stroke-width": ["case", isSelected(id), 1.5, 0.5],
    "circle-opacity": ["case", isSelected(id), 1, 0.6],
  },
});

export const truckLayer: LayerProps = {
  id: "truck-dots",
  type: "circle",
  paint: {
    "circle-radius": 10,
    "circle-color": "#1E2328",
    "circle-stroke-color": "#FAFAF7",
    "circle-stroke-width": 2,
  },
};

export const truckLabelLayer: LayerProps = {
  id: "truck-labels",
  type: "symbol",
  layout: {
    "text-field": ["get", "route"],
    "text-font": ["Noto Sans Bold"],
    "text-size": 12,
    "text-allow-overlap": true,
  },
  paint: { "text-color": "#FAFAF7" },
};

export const heatLayer: LayerProps = {
  id: "corridor-heat",
  type: "raster",
  paint: { "raster-opacity": 0.8, "raster-resampling": "linear", "raster-fade-duration": 0 },
};
