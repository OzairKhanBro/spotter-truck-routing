import { describe, expect, it } from "vite-plus/test";
import { LEVELS, levelIndex, maxLevel } from "./risk";

describe("risk levels", () => {
  it("orders levels from low to no travel", () => {
    expect(LEVELS).toEqual(["low", "moderate", "high", "severe", "no_travel"]);
    expect(levelIndex("severe")).toBe(3);
  });

  it("picks the worse of two levels", () => {
    expect(maxLevel("moderate", "high")).toBe("high");
    expect(maxLevel("no_travel", "low")).toBe("no_travel");
  });
});
