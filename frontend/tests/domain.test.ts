import { describe, it, expect } from "vitest";
import {
  originalEligible,
  decimate,
  kyivRange,
  prioritize,
  energySummary,
  validateSettings,
} from "../src/domain";
import { defaults } from "../src/fixtures";
describe("original12h evidence", () => {
  it("rejects old issue received after cutoff", () =>
    expect(
      originalEligible({
        reference: 100000,
        issued: 56000,
        received: 95000,
        coverage: { start: 56000, end: 100000 },
        frozen: true,
      }),
    ).toBe(false));
  it("accepts both timestamps exactly at cutoff", () =>
    expect(
      originalEligible({
        reference: 100000,
        issued: 56800,
        received: 56800,
        coverage: { start: 56000, end: 100000 },
        frozen: true,
      }),
    ).toBe(true));
  it("rejects uncovered reference", () =>
    expect(
      originalEligible({
        reference: 100000,
        issued: 56000,
        received: 56800,
        coverage: { start: 56000, end: 99999 },
        frozen: true,
      }),
    ).toBe(false));
  it("does not accept latest as frozen original", () =>
    expect(
      originalEligible({
        reference: 100000,
        issued: 56000,
        received: 56800,
        coverage: { start: 56000, end: 100000 },
        frozen: false,
      }),
    ).toBe(false));
});
describe("history truth and time", () => {
  it("retains spikes, endpoints and null gaps", () => {
    const points = Array.from({ length: 1000 }, (_, i) => ({
      at: i,
      value: i === 505 ? 90 : i === 510 ? null : 20,
    }));
    const out = decimate(points, 64);
    expect(out.some((p) => p.value === 90)).toBe(true);
    expect(out.some((p) => p.value === null)).toBe(true);
    expect(out[0]?.at).toBe(0);
    expect(out.at(-1)?.at).toBe(999);
    expect(out.length).toBeLessThan(points.length);
  });
  it("uses23h at spring DST midnight", () => {
    const r = kyivRange("2026-03-29", "2026-03-29");
    expect(r.end - r.start).toBe(23 * 3600);
  });
  it("uses25h at autumn DST midnight", () => {
    const r = kyivRange("2026-10-25", "2026-10-25");
    expect(r.end - r.start).toBe(25 * 3600);
  });
  it("rejects malformed and reversed calendar dates", () => {
    expect(() => kyivRange("2026-02-30", "2026-03-01")).toThrow();
    expect(() => kyivRange("2026-11-05", "2026-11-04")).toThrow();
  });
});
describe("operator truthfulness", () => {
  it("shows one highest-priority alert", () =>
    expect(
      prioritize([
        { priority: "budget", text: "budget" },
        { priority: "safety", text: "stop" },
        { priority: "manual", text: "manual" },
      ])?.text,
    ).toBe("stop"));
  it("never calls negative incomplete remainder savings", () => {
    const r = energySummary({
      reference: 5,
      known: 6,
      estimated: 2,
      unknownS: 180,
      scope: { start: 0, end: 1000 },
      projected: 8,
    });
    expect(r.remaining).toBe(-1);
    expect(r.overrun).toBe(3);
    expect(r.complete).toBe(false);
  });
  it("keeps unscoped amount unavailable", () =>
    expect(
      energySummary({
        reference: 5,
        known: 0,
        estimated: 0,
        unknownS: 30,
        scope: null,
        projected: 8,
      }).remaining,
    ).toBeNull());
  it("validates dependent comfort and half-degree steps", () => {
    expect(
      validateSettings({ ...defaults, night: 24, day: 21 }).length,
    ).toBeGreaterThan(0);
    expect(validateSettings({ ...defaults, day: 21.3 }).length).toBeGreaterThan(
      0,
    );
    expect(validateSettings(defaults)).toEqual([]);
  });
});
describe("numeric and chart edges", () => {
  it("keeps zero distinct from null and every gap disconnected", async () => {
    const { segments, fmt, dateTime, time } = await import("../src/domain");
    expect(fmt(null)).toBe("—");
    expect(fmt(0)).not.toBe("—");
    expect(
      segments([
        { at: 1, value: 0 },
        { at: 2, value: null },
        { at: 3, value: 1 },
        { at: 4, value: null },
      ]),
    ).toHaveLength(2);
    expect(dateTime(1793750400)).toContain("2026");
    expect(time(1793750400)).toBe("02:00");
  });
  it("retains small arrays and bounds worst case alternating gaps", () => {
    const points = Array.from({ length: 4096 }, (_, i) => ({
      at: i,
      value: i % 2 ? null : 0,
    }));
    expect(decimate(points, 32).length).toBeLessThanOrEqual(4096);
    expect(decimate([{ at: 1, value: 0 }])).toEqual([{ at: 1, value: 0 }]);
    expect(() => decimate([...points, { at: 4097, value: 1 }])).toThrow();
    expect(() => decimate([], 1)).toThrow();
  });
  it("rejects unqualified origin, nonfinite times and reversed issued/received", () => {
    const p = {
      reference: 100000,
      issued: 56800,
      received: 56000,
      coverage: { start: 0, end: 100000 },
      frozen: true,
    };
    expect(originalEligible(p)).toBe(false);
    expect(originalEligible({ ...p, received: NaN })).toBe(false);
    expect(prioritize([])).toBeNull();
  });
  it("no verified reference or projected total remains unavailable", () => {
    expect(
      energySummary({
        reference: null,
        known: 0,
        estimated: 0,
        unknownS: 0,
        scope: { start: 0, end: 1 },
        projected: null,
      }),
    ).toEqual({ remaining: null, overrun: null, complete: true });
  });
  for (const change of [
    { day: 15 },
    { night: 27 },
    { budget: -1 },
    { budget: NaN },
    { windowStart: "25:00" },
    { windowEnd: "xx" },
    { windowStart: "07:00", windowEnd: "07:00" },
    { fan: 101 },
    { fan: NaN },
    { freshness: 4 },
    { freshness: NaN },
    { scenario: 12 },
    { strategy: "invalid" },
    { mode: "physical" },
    { circulation: "device" },
    { aiAdvice: 1 },
  ])
    it(`rejects invalid settings ${JSON.stringify(change)}`, () =>
      expect(
        validateSettings({ ...defaults, ...change } as typeof defaults).length,
      ).toBeGreaterThan(0));
});
describe("deadline handling", () => {
  it("resolves successful local work", async () => {
    const { withDeadline } = await import("../src/domain");
    expect(await withDeadline(Promise.resolve(0), 20)).toBe(0);
  });
  it("bounds unavailable work without infinite loading", async () => {
    const { withDeadline } = await import("../src/domain");
    await expect(withDeadline(new Promise(() => undefined), 5)).rejects.toThrow(
      "Час очікування",
    );
  });
});
it("synthetic heating/STOP and a real numeric zero remain distinct from missing", async () => {
  const { snapshot } = await import("../src/fixtures");
  expect(snapshot("heating").status.actual).toBe("heat");
  expect(snapshot("device-stop").status.actual).toBe("stop_demand");
  expect(snapshot("zero").room.value).toBe(0);
  expect(snapshot("missing").room.value).toBeNull();
});
it("custom range cap counts calendar days rather than assuming every day is24h", () => {
  expect(() => kyivRange("2026-03-01", "2026-03-31")).not.toThrow();
  expect(() => kyivRange("2026-03-01", "2026-04-01")).toThrow();
});
