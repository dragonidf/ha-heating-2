import { describe, it, expect } from "vitest";
import "fake-indexeddb/auto";
import { DemoAPI, SnapshotFeed } from "../src/mock";
import { BrowserStore } from "../src/storage";
import { defaults, snapshot, NOW } from "../src/fixtures";
const api = () =>
  new DemoAPI(new BrowserStore("synthetic-test-" + crypto.randomUUID()), 0);
describe("transactional simulation", () => {
  it("only marks saved after durable revision and readback", async () => {
    const a = api();
    const r = await a.save("r1", 1, { ...defaults, day: 22 }, a.session);
    expect(r.status).toBe("saved");
    expect(r.persisted_revision).toBe(2);
    expect((await a.settings()).values.day).toBe(22);
  });
  it("rejects arbitrary serialized authority", async () => {
    const a = api();
    expect((await a.save("r1", 1, defaults, {})).status).toBe("denied");
  });
  it("two clients cannot lose an update", async () => {
    const store = new BrowserStore("synthetic-test-" + crypto.randomUUID());
    const a = new DemoAPI(store, 0),
      b = new DemoAPI(store, 0);
    const r = await Promise.all([
      a.save("a", 1, { ...defaults, day: 22 }, a.session),
      b.save("b", 1, { ...defaults, day: 23 }, b.session),
    ]);
    expect(r.map((x) => x.status).sort()).toEqual(["conflict", "saved"]);
  });
  it("a repeated request never increments revision twice", async () => {
    const a = api();
    const r = await a.save("r1", 1, defaults, a.session);
    expect(await a.save("r1", 1, defaults, a.session)).toEqual(r);
  });
  it("readback failure cannot return saved", async () => {
    const a = api();
    a.fault = "readback";
    expect((await a.save("r1", 1, defaults, a.session)).status).toBe(
      "unavailable",
    );
  });
  it("write failure keeps prior state", async () => {
    const a = api();
    a.fault = "write";
    await a.save("r1", 1, { ...defaults, day: 22 }, a.session);
    expect((await a.settings()).values.day).toBe(defaults.day);
  });
  it("revoked and stale clients cannot commit", async () => {
    const a = api();
    a.setScenario("revoked");
    expect((await a.save("r1", 1, defaults, a.session)).status).toBe("denied");
    a.setScenario("stale");
    expect((await a.save("r2", 1, defaults, a.session)).status).toBe(
      "unavailable",
    );
  });
  it("disconnect in flight never yields a saved receipt", async () => {
    const a = new DemoAPI(
      new BrowserStore("synthetic-test-" + crypto.randomUUID()),
      30,
    );
    const result = a.save("r1", 1, defaults, a.session);
    a.setScenario("offline");
    expect((await result).status).toBe("unavailable");
  });
});
describe("ordered subscription", () => {
  it("ignores stale/replayed updates and disables on a sequence gap", () => {
    const f = new SnapshotFeed(snapshot());
    expect(f.accept(snapshot("manual", 1))).toBe(false);
    expect(f.accept(snapshot("normal", 3))).toBe(false);
    expect(f.value.connected).toBe(false);
  });
  it("old connection cannot overwrite a reconnect snapshot", () => {
    const f = new SnapshotFeed(snapshot());
    f.reset(snapshot("normal", 10, 2));
    expect(f.accept(snapshot("manual", 11, 1))).toBe(false);
    expect(f.value.generation).toBe(2);
  });
  it("recovery never replays one-shot unknown outcome", () => {
    const a = api();
    a.setScenario("recovering");
    expect(a.feed.value.oneShot.state).toBe("unknown_outcome");
    expect(a.feed.value.status.desired).toBe("stop_demand");
    expect(a.feed.value.now).toBe(NOW);
  });
});
describe("operator simulation guards", () => {
  it("emits new ordered snapshots to subscribers and unsubscribe works", () => {
    const f = new SnapshotFeed(snapshot());
    let count = 0;
    const off = f.subscribe(() => count++);
    expect(f.accept(snapshot("manual", 2))).toBe(true);
    off();
    f.accept(snapshot("normal", 3));
    expect(count).toBe(1);
  });
  it("pause/resume change owner but never assert physical state", () => {
    const a = api();
    expect(a.control("pause", a.session).status).toBe("accepted_fake");
    expect(a.feed.value.status.mode).toBe("MANUAL_PAUSE");
    expect(a.control("resume", a.session).status).toBe("accepted_fake");
    expect(a.feed.value.status.mode).toBe("RECOVERING");
    expect(a.feed.value.status.actual).toBeNull();
  });
  it("one-shot states are distinct and unknown cannot be rearmed", () => {
    const a = api();
    a.control("arm", a.session);
    expect(a.feed.value.oneShot.state).toBe("armed");
    a.control("cancel", a.session);
    expect(a.feed.value.oneShot.state).toBe("cancelled");
    a.control("expire", a.session);
    expect(a.feed.value.oneShot.state).toBe("expired");
    a.control("unknown", a.session);
    expect(a.feed.value.oneShot.state).toBe("unknown_outcome");
    expect(a.control("arm", a.session).status).toBe("denied");
  });
  it("arbitrary authority cannot control or change model", () => {
    const a = api();
    expect(a.control("arm", {}).status).toBe("denied");
    expect(a.modelAction("train", {})).toContain("відхилено");
  });
  it("model candidate/holdout gate, freeze and rollback do not alter history", () => {
    const a = api();
    const before = a.history({ start: NOW - 86400, end: NOW });
    expect(a.modelAction("promote", a.session)).toContain("Недостатньо");
    a.modelAction("train", a.session);
    expect(a.model.candidate).toBe(true);
    a.modelAction("promote", a.session);
    expect(a.model.revision).toBe(4);
    a.modelAction("freeze", a.session);
    expect(a.modelAction("train", a.session)).toContain("заморожено");
    a.modelAction("freeze", a.session);
    a.modelAction("rollback", a.session);
    expect(a.model.revision).toBe(3);
    expect(a.history({ start: NOW - 86400, end: NOW })).toEqual(before);
  });
  it("invalid settings and duplicate pending save cannot be acknowledged", async () => {
    const a = new DemoAPI(
      new BrowserStore("synthetic-test-" + crypto.randomUUID()),
      10,
    );
    expect(
      (await a.save("bad", 1, { ...defaults, day: NaN }, a.session)).status,
    ).toBe("denied");
    const first = a.save("first", 1, defaults, a.session);
    expect((await a.save("second", 1, defaults, a.session)).status).toBe(
      "unavailable",
    );
    await first;
  });
  it("timeout is explicit and bounded", async () => {
    const a = api();
    a.fault = "timeout";
    expect((await a.save("t", 1, defaults, a.session)).status).toBe(
      "unavailable",
    );
    expect((await a.settings()).revision).toBe(1);
  });
  it("reconnection changes generation and clears stale source qualification", () => {
    const a = api();
    a.setScenario("offline");
    const generation = a.feed.value.generation;
    a.reconnect();
    expect(a.feed.value.connected).toBe(true);
    expect(a.feed.value.generation).toBe(generation + 1);
  });
  it("cursor paging is scoped, bounded and immutable", () => {
    const a = api(),
      range = { start: NOW - 7 * 86400, end: NOW };
    const first = a.history(range, null, 16);
    expect(first.rows).toHaveLength(16);
    expect(first.cursor).not.toBeNull();
    const second = a.history(range, first.cursor, 16);
    expect(second.rows[0]?.at).toBeGreaterThan(first.rows.at(-1)?.at ?? 0);
    expect(() => a.history({ start: 0, end: 1 }, first.cursor)).toThrow();
    expect(() =>
      a.history(range, {
        offset: -1,
        scope: `${range.start}:${range.end}`,
        watermark: first.watermark,
      }),
    ).toThrow();
    expect(() =>
      a.history(range, {
        offset: 9999,
        scope: `${range.start}:${range.end}`,
        watermark: first.watermark,
      }),
    ).toThrow();
    expect(() => a.history(range, null, 257)).toThrow();
    expect(() => a.history({ start: 2, end: 1 })).toThrow();
    a.setScenario("empty");
    expect(a.history(range).rows).toHaveLength(0);
  });
  it("same id with a different body conflicts rather than overwrites", async () => {
    const a = api();
    await a.save("id", 1, defaults, a.session);
    expect(
      (await a.save("id", 1, { ...defaults, day: 22 }, a.session)).status,
    ).toBe("conflict");
  });
});
describe("one-shot logical consumption", () => {
  it("consumes a qualified fake intent only once without asserting actual heat", () => {
    const a = api();
    a.control("arm", a.session);
    expect(a.control("consume", a.session).status).toBe("accepted_fake");
    expect(a.feed.value.oneShot.state).toBe("consumed");
    expect(a.control("consume", a.session).status).toBe("denied");
    expect(a.feed.value.status.actual).toBeNull();
  });
  it("manual ownership and missing grid deny fake consumption", () => {
    const a = api();
    a.control("arm", a.session);
    a.control("pause", a.session);
    expect(a.control("consume", a.session).status).toBe("denied");
    const b = api();
    b.setScenario("grid-off");
    b.control("arm", b.session);
    expect(b.control("consume", b.session).status).toBe("denied");
  });
});
describe("bounded save identities", () => {
  it("rejects oversized ids and non-integer revisions before writing", async () => {
    const a = api();
    await expect(
      a.save("x".repeat(129), 1, defaults, a.session),
    ).rejects.toThrow();
    await expect(a.save("id", NaN, defaults, a.session)).rejects.toThrow();
    expect((await a.settings()).revision).toBe(1);
  });
});
it("frozen learning does not prevent explicit synthetic rollback", () => {
  const a = api();
  a.modelAction("train", a.session);
  a.modelAction("promote", a.session);
  a.modelAction("freeze", a.session);
  a.modelAction("rollback", a.session);
  expect(a.model.revision).toBe(3);
  expect(a.model.frozen).toBe(true);
});
it("persisted observation mode blocks fake one-shot heat but retains unknown actual", async () => {
  const a = api();
  await a.save("observe", 1, { ...defaults, mode: "observation" }, a.session);
  expect(a.feed.value.status.mode).toBe("SHADOW");
  expect(a.feed.value.status.desired).toBe("stop_demand");
  a.control("arm", a.session);
  expect(a.control("consume", a.session).status).toBe("denied");
  expect(a.feed.value.status.physical_verified).toBe(false);
});
it("persisted fan request stays separate from its unknown actual state", async () => {
  const a = api();
  await a.save(
    "fan",
    1,
    { ...defaults, circulation: "manual", fan: 38 },
    a.session,
  );
  expect(a.feed.value.fan.requested).toBe(38);
  expect(a.feed.value.fan.actual).toBeNull();
});
