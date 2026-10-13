import { afterEach, describe, expect, it, vi } from "vite-plus/test";
import { ApiError, api } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("surfaces the server message", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: "Departure is in the past." }), { status: 422 }),
        ),
    );
    await expect(api.trip("x")).rejects.toEqual(new ApiError(422, "Departure is in the past."));
  });
  it("joins schema validation messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: [{ msg: "a" }, { msg: "b" }] }), { status: 422 }),
        ),
    );
    await expect(api.trip("x")).rejects.toThrow("a; b");
  });
  it("explains a dead server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.trip("x")).rejects.toThrow("Can't reach the server");
  });
});
