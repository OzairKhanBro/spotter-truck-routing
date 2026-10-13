import { describe, expect, it } from "vite-plus/test";
import { defaultForm, toTripInput, validateForm } from "./validate";

const NOW = new Date("2026-10-14T15:20:00");
const chicago = { label: "Chicago, Illinois, US", lat: 41.88, lon: -87.63 };
const denver = { label: "Denver, Colorado, US", lat: 39.74, lon: -104.99 };
const ok = { ...defaultForm(NOW), origin: chicago, destination: denver };

describe("validateForm", () => {
  it("defaults to the next whole hour, 40,000 lb, every 25 mi", () => {
    const f = defaultForm(NOW);
    expect(f.departure).toBe("2026-10-14T16:00");
    expect(f.loadLb).toBe("40000");
    expect(f.intervalMi).toBe(25);
  });
  it("accepts a complete form", () => {
    expect(validateForm(ok, NOW)).toBeNull();
  });
  it.each([
    [{ origin: null }, "Pick a start from the list."],
    [{ destination: null }, "Pick a destination from the list."],
    [{ destination: chicago }, "Start and destination are the same place."],
    [{ departure: "2026-10-14T13:00" }, "Departure is in the past."],
    [{ departure: "2026-10-22T16:00" }, "Pick a departure within the next 7 days."],
    [{ loadLb: "0" }, "Enter a load between 1 and 150,000 lb."],
    [{ loadLb: "heavy" }, "Enter a load between 1 and 150,000 lb."],
  ])("rejects %o", (patch, message) => {
    expect(validateForm({ ...ok, ...patch }, NOW)).toBe(message);
  });
});

describe("validateForm edges", () => {
  it.each(["1", "150,000", "150000"])("accepts load %s lb", (loadLb) => {
    expect(validateForm({ ...ok, loadLb }, NOW)).toBeNull();
  });
  it.each(["150001", "", "-5"])("rejects load %o", (loadLb) => {
    expect(validateForm({ ...ok, loadLb }, NOW)).toBe("Enter a load between 1 and 150,000 lb.");
  });
  it("accepts a departure up to 1 hour ago and exactly 7 days ahead", () => {
    expect(validateForm({ ...ok, departure: "2026-10-14T14:20" }, NOW)).toBeNull();
    expect(validateForm({ ...ok, departure: "2026-10-21T15:20" }, NOW)).toBeNull();
  });
});

describe("toTripInput", () => {
  it("sends departure as UTC and load as a number", () => {
    const input = toTripInput({ ...ok, departure: "2026-10-14T16:00", loadLb: "42,500" });
    expect(input.departure).toBe(new Date("2026-10-14T16:00").toISOString());
    expect(input.load_lb).toBe(42500);
  });
});
