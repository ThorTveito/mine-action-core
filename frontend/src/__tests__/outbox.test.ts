import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { discard, enqueue, flushOutbox, loadOutbox, newClientId } from "../outbox";
import type { FieldReportInput } from "../types";

const report = (id: string): FieldReportInput => ({
  client_id: id,
  observed_at: "2026-01-01T00:00:00Z",
  finding_type: "item_found",
  item_category: "ap_mine",
  quantity: 1,
  source: "direct_observation",
  description: "",
  lon: 8.5,
  lat: 61.5,
  gps_accuracy_m: 5,
});

const respond = (status: number, body: unknown = {}) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("outbox", () => {
  it("stores and discards reports on the device", () => {
    enqueue(report("a"));
    enqueue(report("b"));
    expect(loadOutbox().map((q) => q.payload.client_id)).toEqual(["a", "b"]);
    discard("a");
    expect(loadOutbox().map((q) => q.payload.client_id)).toEqual(["b"]);
  });

  it("sends everything when the connection is back", async () => {
    const fetch = vi.fn(() => respond(201, { id: 1 }));
    vi.stubGlobal("fetch", fetch);
    enqueue(report("a"));
    enqueue(report("b"));
    expect(await flushOutbox()).toEqual({ sent: 2, remaining: 0, needsLogin: false });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(loadOutbox()).toEqual([]);
  });

  it("keeps the queue in order while still offline", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    enqueue(report("a"));
    enqueue(report("b"));
    const result = await flushOutbox();
    expect(result.sent).toBe(0);
    expect(loadOutbox().map((q) => q.payload.client_id)).toEqual(["a", "b"]);
    expect(loadOutbox()[0].lastError).toBe("Waiting for connection");
  });

  it("parks a report the server refuses instead of retrying it forever", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => respond(422, { detail: "observed_at is in the future" })),
    );
    enqueue(report("bad"));
    await flushOutbox();
    const [item] = loadOutbox();
    expect(item.needsAttention).toBe(true);
    expect(item.lastError).toContain("future");
  });

  it("pauses when the login has expired", async () => {
    localStorage.setItem("mac.token", "expired");
    vi.stubGlobal("fetch", vi.fn(() => respond(401, { detail: "Login required" })));
    enqueue(report("a"));
    expect((await flushOutbox()).needsLogin).toBe(true);
    expect(loadOutbox()).toHaveLength(1);
  });

  it("generates RFC 4122-shaped ids", () => {
    expect(newClientId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
});
