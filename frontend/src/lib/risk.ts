export const LEVELS = ["low", "moderate", "high", "severe", "no_travel"] as const;
export type Level = (typeof LEVELS)[number];

export const LEVEL_LABEL: Record<Level, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
  no_travel: "No travel",
};

// Keep in sync with --color-risk-* in styles/app.css.
export const LEVEL_COLOR: Record<Level, string> = {
  low: "#5E9C76",
  moderate: "#E9B824",
  high: "#EA7A1F",
  severe: "#C8232C",
  no_travel: "#4A1050",
};

export const levelIndex = (level: Level): number => LEVELS.indexOf(level);

export const maxLevel = (a: Level, b: Level): Level => (levelIndex(a) >= levelIndex(b) ? a : b);
