import { describe, expect, it } from "vite-plus/test";
import { formatDuration, formatMiles } from "./format";

describe("format", () => {
  it("formats drive time as hours and minutes", () => {
    expect(formatDuration(56_695)).toBe("15 h 45 m");
    expect(formatDuration(1_500)).toBe("25 m");
  });
  it("formats miles with separators", () => {
    expect(formatMiles(1016.44)).toBe("1,016 mi");
    expect(formatMiles(4.26)).toBe("4.3 mi");
  });
});
