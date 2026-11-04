import { describe, it, expect } from "vitest";
import fixture from "../src/contracts.fixture.json";
import {
  readStatus,
  readReceipt,
  persisted,
  object,
  finite,
} from "../src/contracts";
import { defaults } from "../src/fixtures";
describe("accepted WP2A envelope compatibility", () => {
  it("decodes canonical Python status without physical confirmation", () => {
    expect(readStatus(fixture.status).physical_verified).toBe(false);
    expect(readStatus(fixture.ack).receipt_stage).toBe("ha_acknowledged");
  });
  it("decodes exact durable and failed receipts", () => {
    expect(readReceipt(fixture.saved).persisted_revision).toBe(2);
    expect(readReceipt(fixture.failed).persisted_revision).toBeNull();
  });
  for (const bad of [null, [], 4, "text"])
    it(`rejects non-object ${JSON.stringify(bad)}`, () =>
      expect(() => object(bad)).toThrow());
  it("rejects unknown versions and envelope keys", () => {
    expect(() => readStatus({ ...fixture.status, version: [3, 0] })).toThrow();
    expect(() => readStatus({ ...fixture.status, extra: true })).toThrow();
  });
  it("rejects oversized payload", () =>
    expect(() =>
      readStatus({ ...fixture.status, padding: "x".repeat(262144) }),
    ).toThrow());
  for (const [key, value] of Object.entries({
    status_seq: -1,
    owner_epoch: 1.5,
    snapshot_at: -1,
    actual: "on",
    desired: "off",
    receipt_stage: "physical_success",
    physical_verified: true,
    mode: "",
    boot_id: "",
    archive_lost: NaN,
  }))
    it(`rejects invalid status ${key}`, () =>
      expect(() =>
        readStatus({
          ...fixture.status,
          data: { ...fixture.status.data, [key]: value },
        }),
      ).toThrow());
  for (const change of [
    { status: "saved", persisted_revision: null },
    { status: "unavailable", persisted_revision: 2 },
    { status: "success" },
    { revision: NaN },
    { request_id: 4 },
    { reason: null },
    { persisted_revision: -1 },
  ])
    it(`rejects malformed receipt ${JSON.stringify(change)}`, () =>
      expect(() =>
        readReceipt({
          ...fixture.saved,
          data: { ...fixture.saved.data, ...change },
        }),
      ).toThrow());
  it("accepts a valid simulated persisted settings record", () =>
    expect(
      persisted({ revision: 1, values: defaults, lastRequest: null }).values,
    ).toEqual(defaults));
  for (const change of [
    { revision: 0 },
    { lastRequest: 5 },
    { extra: "x" },
    { values: { ...defaults, night: 26 } },
    { values: { ...defaults, secret: "unexpected" } },
  ])
    it(`rejects corrupted persisted shape ${JSON.stringify(change)}`, () =>
      expect(() =>
        persisted({
          revision: 1,
          values: defaults,
          lastRequest: null,
          ...change,
        }),
      ).toThrow());
  it("accepts finite zero but not nonfinite or string numbers", () => {
    expect(finite(0)).toBe(true);
    expect(finite(Infinity)).toBe(false);
    expect(finite("1")).toBe(false);
  });
});
describe("canonical forecast and scoped budget adapters", () => {
  it("retains original source receipt, model, plan and scope", async () => {
    const { readForecast } = await import("../src/contracts");
    const f = readForecast(fixture.original, fixture.original_source);
    expect(f.received).toBe(f.reference - 44000);
    expect(f.issued).toBe(f.reference - 45000);
    expect(f.model).toBe(3);
    expect(f.plan).toBe("synthetic.plan.frozen");
    expect(f.frozen).toBe(true);
    expect(f.points).toHaveLength(25);
  });
  it("does not treat a late source as original evidence", async () => {
    const { readForecast } = await import("../src/contracts");
    const { originalEligible } = await import("../src/domain");
    expect(
      originalEligible(
        readForecast(fixture.original, {
          ...fixture.original_source,
          data: {
            ...fixture.original_source.data,
            recorded_at: fixture.original.data.reference - 3600,
          },
        }),
      ),
    ).toBe(false);
  });
  it("rejects changed original curve or invalid scope", async () => {
    const { readForecast, readBudget } = await import("../src/contracts");
    expect(() =>
      readForecast(fixture.original, {
        ...fixture.original_source,
        data: { ...fixture.original_source.data, curve: null },
      }),
    ).toThrow();
    expect(() =>
      readBudget({
        ...fixture.budget,
        data: { ...fixture.budget.data, scope: null },
      }),
    ).toThrow();
  });
  it("maps exact WP2A budget without borrowing a different scope", async () => {
    const { readBudget } = await import("../src/contracts");
    const b = readBudget(fixture.budget);
    expect(b.reference).toBe(18.5);
    expect(b.unknownS).toBe(1080);
    expect(b.scope?.end).toBe(1793750400 + 18000);
  });
});
