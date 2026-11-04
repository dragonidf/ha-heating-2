import { describe, expect, it, vi } from "vitest";
import {
  NativeAPI,
  type Hass,
  type HassConnection,
} from "../src/nativeAdapter";
import {
  readSnapshot,
  readOverview,
  readPage,
  readEnergy,
} from "../src/nativeContracts";
import {
  defaults,
  snapshot,
  actual,
  original,
  latest,
  cycleEnergy,
  timeline,
  metrics,
  intervals,
  NOW,
} from "../src/fixtures";
import type { Persisted, Snapshot } from "../src/types";
function server(enabled = true) {
  let state = snapshot();
  state.status.mode = "SHADOW";
  state.permitted = enabled;
  const calls: Record<string, unknown>[] = [];
  let settings: Persisted = {
    revision: 1,
    values: { ...defaults },
    lastRequest: null,
  };
  let listener: ((v: unknown) => void) | undefined;
  let removed = 0;
  const events = new Map<string, () => void>();
  const connection: HassConnection = {
    subscribeMessage: async <T>(
      fn: (v: T) => void,
      message: Record<string, unknown>,
    ) => {
      calls.push(message);
      listener = fn as (v: unknown) => void;
      fn(structuredClone(state) as T);
      return () => {
        listener = undefined;
        removed++;
      };
    },
    addEventListener: (type, fn) => {
      events.set(type, fn);
    },
    removeEventListener: (type) => {
      events.delete(type);
    },
  };
  let fail = "",
    corruptReadback = false;
  const hass: Hass = {
    connection,
    connected: true,
    user: { id: "synthetic-test", is_admin: true },
    callWS: async <T>(message: Record<string, unknown>) => {
      calls.push(message);
      const op = String(message.type).replace("heating_ai/", "");
      if (op === fail) throw Error("synthetic failure");
      let result: unknown;
      if (op === "status") result = state;
      else if (op === "overview")
        result = {
          original,
          latest,
          cycleEnergy,
          timeline,
          metrics,
          model: { revision: 3, candidate: false, frozen: false },
          enabled,
          gates: ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08"],
          physical_authority: false,
        };
      else if (op === "settings/get")
        result = corruptReadback ? { ...settings, revision: 1 } : settings;
      else if (op === "settings/save") {
        if (message.expected_revision !== settings.revision)
          result = {
            request_id: message.request_id,
            status: "conflict",
            revision: settings.revision,
            persisted_revision: null,
            reason: "conflict",
          };
        else {
          settings = {
            revision: settings.revision + 1,
            values: message.values as typeof defaults,
            lastRequest: message.request_id as string,
          };
          result = {
            request_id: message.request_id,
            status: "saved",
            revision: settings.revision,
            persisted_revision: settings.revision,
            reason: "saved",
          };
        }
      } else if (op === "control")
        result = {
          request_id: message.request_id,
          status: "accepted_fake",
          revision: 0,
          persisted_revision: null,
          reason: "synthetic only",
        };
      else if (op === "model")
        result = {
          reason: "synthetic model",
          model: { revision: 3, candidate: true, frozen: false },
        };
      else if (op === "energy") result = intervals;
      else if (op === "history") {
        const rows = actual.filter(
            (p) => p.at >= Number(message.start) && p.at < Number(message.end),
          ),
          offset = (message.cursor as { offset: number } | null)?.offset ?? 0,
          limit = Number(message.limit);
        result = {
          rows: rows.slice(offset, offset + limit),
          watermark: actual.length,
          cursor:
            offset + limit < rows.length
              ? {
                  offset: offset + limit,
                  scope: `${message.start}:${message.end}`,
                  watermark: actual.length,
                }
              : null,
        };
      } else throw Error("unexpected op");
      return structuredClone(result) as T;
    },
  };
  return {
    hass,
    calls,
    events,
    api: new NativeAPI(hass, "synthetic-entry"),
    emit: (s: Snapshot) => listener?.(s),
    get state() {
      return state;
    },
    set state(s) {
      state = s;
    },
    get removed() {
      return removed;
    },
    fail: (v: string) => {
      fail = v;
    },
    corrupt: () => {
      corruptReadback = true;
    },
  };
}
describe("HA injected native bridge", () => {
  it("bootstraps backend overview, bounded history, settings and energy, with common RPC scope", async () => {
    const s = server();
    await s.api.start();
    expect(s.api.canChange()).toBe(true);
    expect(s.api.view?.original).toEqual(original);
    expect(s.api.view?.actual.every((p) => p.at <= NOW)).toBe(true);
    expect(s.api.energyHistory()).toEqual(intervals);
    expect(s.calls.some((c) => c.type === "heating_ai/settings/get")).toBe(
      true,
    );
    for (const call of s.calls) {
      expect(call.entry_id).toBe("synthetic-entry");
      expect(call.version).toEqual([2, 0]);
      if (call.type === "heating_ai/history")
        expect(call.limit).toBeLessThanOrEqual(256);
    }
    s.api.close();
  });
  it("defaults to read-only until authoritative enabled and permitted state", async () => {
    const s = server(false);
    await s.api.start();
    expect(s.api.canChange()).toBe(false);
    await expect(s.api.control("pause", s.api.session)).rejects.toThrow(
      "Лише читання",
    );
    expect(s.calls.some((c) => c.type === "heating_ai/control")).toBe(false);
    s.api.close();
  });
  it("does not manufacture auth from a caller supplied session", async () => {
    const s = server();
    await s.api.start();
    await expect(
      s.api.save("id", 1, defaults, { native: true }),
    ).rejects.toThrow();
    s.api.close();
  });
  it("persists with server CAS and independent verified readback", async () => {
    const s = server();
    await s.api.start();
    const values = { ...defaults, day: 23 };
    const receipt = await s.api.save(
      "synthetic-request",
      1,
      values,
      s.api.session,
    );
    expect(receipt.status).toBe("saved");
    expect((await s.api.settings()).values.day).toBe(23);
    const request = s.calls.find((c) => c.type === "heating_ai/settings/save")!;
    expect(request.boot_id).toBe(s.state.status.boot_id);
    expect(request.generation).toBe(s.state.generation);
    expect(request.owner_epoch).toBe(s.state.status.owner_epoch);
    expect(request).not.toHaveProperty("permitted");
    s.api.close();
  });
  it("reports conflicting server revisions without overwriting", async () => {
    const s = server();
    await s.api.start();
    await s.api.save("one", 1, defaults, s.api.session);
    expect(
      (await s.api.save("two", 1, { ...defaults, day: 23 }, s.api.session))
        .status,
    ).toBe("conflict");
    s.api.close();
  });
  it("rejects unverified readback", async () => {
    const s = server();
    await s.api.start();
    s.corrupt();
    await expect(s.api.save("id", 1, defaults, s.api.session)).rejects.toThrow(
      "не підтверджене",
    );
    s.api.close();
  });
  it("rejects invalid settings and IDs before RPC mutation", async () => {
    const s = server();
    await s.api.start();
    await expect(
      s.api.save("id", 1, { ...defaults, day: NaN }, s.api.session),
    ).rejects.toThrow();
    await expect(s.api.save("", 1, defaults, s.api.session)).rejects.toThrow();
    expect(s.calls.some((c) => c.type === "heating_ai/settings/save")).toBe(
      false,
    );
    s.api.close();
    expect(() => new NativeAPI(s.hass, "bad/entry")).toThrow();
  });
  it("accepts ordered updates and rejects old events", async () => {
    const s = server();
    await s.api.start();
    const next = { ...s.state, seq: s.state.seq + 1, permitted: false };
    s.emit(next);
    expect(s.api.feed.value.permitted).toBe(false);
    s.emit(s.state);
    expect(s.api.feed.value.seq).toBe(next.seq);
    await expect(s.api.control("arm", s.api.session)).rejects.toThrow();
    s.api.close();
  });
  it("refreshes full state on a sequence gap", async () => {
    const s = server();
    await s.api.start();
    s.state = { ...s.state, seq: s.state.seq + 3 };
    s.emit(s.state);
    await s.api.reconnect();
    expect(s.api.feed.value.seq).toBe(s.state.seq);
    expect(s.removed).toBe(1);
    s.api.close();
  });
  it("refreshes boot/generation and never replays a mutation", async () => {
    const s = server();
    await s.api.start();
    s.state = {
      ...s.state,
      seq: 1,
      generation: 4,
      status: { ...s.state.status, boot_id: "new-synthetic-boot" },
    };
    s.emit(s.state);
    await s.api.reconnect();
    expect(s.api.feed.value.generation).toBe(4);
    expect(s.calls.filter((c) => c.type === "heating_ai/control")).toHaveLength(
      0,
    );
    s.api.close();
  });
  it("uses HA disconnect/ready lifecycle and disposes subscriptions", async () => {
    const s = server();
    await s.api.start();
    s.events.get("disconnected")!();
    expect(s.api.canChange()).toBe(false);
    s.events.get("ready")!();
    await s.api.reconnect();
    expect(s.api.feed.value.connected).toBe(true);
    s.api.close();
    expect(s.events.size).toBe(0);
    expect(s.removed).toBe(2);
  });
  it("fails closed on malformed subscription data", async () => {
    const s = server();
    await s.api.start();
    s.emit({
      ...s.state,
      status: { ...s.state.status, physical_verified: true },
    } as unknown as Snapshot);
    expect(s.api.canChange()).toBe(false);
    s.api.close();
  });
  it("keeps temperature and energy errors independent", async () => {
    const s = server();
    s.fail("energy");
    await s.api.start();
    expect(s.api.view?.actual.length).toBeGreaterThan(0);
    expect(() => s.api.energyHistory()).toThrow();
    s.api.close();
    const t = server();
    t.fail("history");
    await t.api.start();
    expect(t.api.energyHistory().length).toBeGreaterThan(0);
    expect(() => t.api.history({ start: NOW - 86400, end: NOW })).toThrow();
    t.api.close();
  });
  it("fails bootstrap closed for revoked/failed status", async () => {
    const s = server();
    s.fail("status");
    await expect(s.api.start()).rejects.toThrow();
    expect(s.api.canChange()).toBe(false);
    s.api.close();
  });
  it("paginates new calendar scopes without frontend persistence", async () => {
    const s = server();
    await s.api.start();
    const range = { start: NOW - 30 * 86400, end: NOW };
    await s.api.loadHistory(range);
    const page = s.api.history(range, null, 256);
    expect(page.rows.length).toBeLessThanOrEqual(256);
    await expect(
      s.api.loadHistory({ start: 0, end: 40 * 86400 }),
    ).rejects.toThrow();
    expect(() =>
      s.api.history(range, {
        offset: -1,
        scope: `${range.start}:${range.end}`,
        watermark: actual.length,
      }),
    ).toThrow();
    s.api.close();
  });
  it("handles asynchronous model/control responses without asserting physical action", async () => {
    const s = server();
    await s.api.start();
    expect((await s.api.control("pause", s.api.session)).status).toBe(
      "accepted_fake",
    );
    expect(await s.api.modelAction("train", s.api.session)).toBe(
      "synthetic model",
    );
    expect(s.api.model.candidate).toBe(true);
    expect(s.api.feed.value.status.physical_verified).toBe(false);
    s.api.close();
  });
});
describe("native trust boundaries", () => {
  it("rejects false physical evidence, unknown status and oversized pages", () => {
    expect(() =>
      readSnapshot({
        ...snapshot(),
        status: { ...snapshot().status, physical_verified: true },
      }),
    ).toThrow();
    expect(() =>
      readSnapshot({
        ...snapshot(),
        room: { value: 0, observed: 0, quality: "invented" },
      }),
    ).toThrow();
    expect(() =>
      readPage({
        rows: Array.from({ length: 257 }, () => ({ at: 0, value: 0 })),
        cursor: null,
        watermark: 1,
      }),
    ).toThrow();
  });
  it("rejects invalid energy and unqualified overview authority", () => {
    expect(() =>
      readEnergy([
        { start: 1, end: 2, kwh: NaN, price: null, category: "confirmed" },
      ]),
    ).toThrow();
    expect(() => readOverview({ physical_authority: true })).toThrow();
  });
});

describe("native failure isolation and request fencing", () => {
  it("keeps healthy status and logical STOP available when overview fails", async () => {
    const s = server();
    s.fail("overview");
    await expect(s.api.start()).resolves.toBeUndefined();
    expect(s.api.feed.value.connected).toBe(true);
    expect(s.api.view?.original).toBeNull();
    expect(s.api.dataErrors.join()).toContain("огляд");
    expect((await s.api.control("pause", s.api.session)).status).toBe(
      "accepted_fake",
    );
    s.api.close();
  });
  it("keeps healthy status and STOP when settings archive fails", async () => {
    const s = server();
    s.fail("settings/get");
    await expect(s.api.start()).resolves.toBeUndefined();
    expect((await s.api.control("pause", s.api.session)).status).toBe(
      "accepted_fake",
    );
    s.api.close();
  });
  it("historical empty scopes cannot erase current Home actual points", async () => {
    const s = server();
    await s.api.start();
    const before = s.api.view!.actual;
    await s.api.loadHistory({ start: 1, end: 86400 });
    expect(s.api.view!.actual).toEqual(before);
    s.api.close();
  });
  it("ignores late history responses from a superseded scope", async () => {
    const s = server();
    await s.api.start();
    const call = s.hass.callWS.bind(s.hass);
    let release!: (value: unknown) => void;
    s.hass.callWS = async <T>(message: Record<string, unknown>) =>
      message.type === "heating_ai/history" && message.start === 1
        ? ((await new Promise<unknown>((resolve) => {
            release = resolve;
          })) as T)
        : call<T>(message);
    const late = s.api.loadHistory({ start: 1, end: 86400 });
    const current = { start: NOW - 86400, end: NOW };
    await s.api.loadHistory(current);
    release({ rows: [], cursor: null, watermark: actual.length });
    await late;
    expect(s.api.history(current).rows.length).toBeGreaterThan(0);
    s.api.close();
  });
  it("bounds hanging HA RPCs with a deadline", async () => {
    const s = server();
    const call = s.hass.callWS.bind(s.hass);
    s.hass.callWS = async <T>(message: Record<string, unknown>) =>
      message.type === "heating_ai/status"
        ? new Promise<T>(() => {})
        : call<T>(message);
    vi.useFakeTimers();
    const pending = s.api.start();
    const rejected = expect(pending).rejects.toThrow();
    await vi.advanceTimersByTimeAsync(2001);
    await rejected;
    expect(s.api.canChange()).toBe(false);
    s.api.close();
    vi.useRealTimers();
  });
  it("makes command and model request IDs explicit", async () => {
    const s = server();
    await s.api.start();
    await s.api.control("pause", s.api.session);
    await s.api.modelAction("train", s.api.session);
    for (const type of ["heating_ai/control", "heating_ai/model"])
      expect(s.calls.find((call) => call.type === type)?.request_id).toMatch(
        /^native\.ui\./,
      );
    s.api.close();
  });
});

describe("native lifecycle fences", () => {
  it("refreshes when the initial subscription races a new backend boot", async () => {
    const s = server(),
      subscribe = s.hass.connection.subscribeMessage.bind(s.hass.connection);
    let first = true;
    s.hass.connection.subscribeMessage = async <T>(
      callback: (v: T) => void,
      message: Record<string, unknown>,
    ) => {
      if (first) {
        first = false;
        s.state = {
          ...s.state,
          generation: 4,
          status: { ...s.state.status, boot_id: "raced-synthetic-boot" },
        };
      }
      return subscribe(callback, message);
    };
    await s.api.start();
    await vi.waitFor(() => {
      expect(s.api.feed.value.connected).toBe(true);
      expect(s.api.feed.value.generation).toBe(4);
    });
    s.api.close();
  });
  it("invalidates detached panel mutation permissions", async () => {
    const s = server();
    await s.api.start();
    s.api.close();
    expect(s.api.canChange()).toBe(false);
    await expect(s.api.control("pause", s.api.session)).rejects.toThrow();
    await expect(s.api.reconnect()).rejects.toThrow("закрита");
  });
});

describe("native independent STOP and authoritative qualification", () => {
  it("keeps logical STOP available with missing source and unavailable critical settings", async () => {
    const s = server();
    s.state = {
      ...s.state,
      permitted: false,
      room: { value: null, observed: 0, quality: "missing" },
      status: { ...s.state.status, mode: "SAFE_HOLD" },
    };
    s.fail("settings/get");
    await s.api.start();
    expect(s.api.canChange()).toBe(false);
    expect(s.api.canStop()).toBe(true);
    const receipt = await s.api.control("pause", s.api.session);
    expect(receipt.status).toBe("accepted_fake");
    expect(s.api.feed.value.status.physical_verified).toBe(false);
    await expect(s.api.control("arm", s.api.session)).rejects.toThrow();
    await expect(
      s.api.save("no-settings", 1, defaults, s.api.session),
    ).rejects.toThrow();
    s.api.close();
  });
  it("fences independent STOP by live HA admin, session and connection", async () => {
    const s = server();
    await s.api.start();
    await expect(s.api.control("pause", {})).rejects.toThrow();
    s.hass.user = { id: "synthetic-reader", is_admin: false };
    expect(s.api.canStop()).toBe(false);
    await expect(s.api.control("pause", s.api.session)).rejects.toThrow();
    s.hass.user = { id: "synthetic-test", is_admin: true };
    s.events.get("disconnected")!();
    expect(s.api.canStop()).toBe(false);
    await expect(s.api.control("pause", s.api.session)).rejects.toThrow();
    s.api.close();
  });
  it("requires current session after an independent STOP response", async () => {
    const s = server();
    await s.api.start();
    const call = s.hass.callWS.bind(s.hass);
    s.hass.callWS = async <T>(message: Record<string, unknown>) => {
      const result = await call<T>(message);
      if (message.type === "heating_ai/control")
        s.events.get("disconnected")!();
      return result;
    };
    await expect(s.api.control("pause", s.api.session)).rejects.toThrow(
      "Сесію змінено",
    );
    s.api.close();
  });
  it("honors backend-qualified age 60 and still denies fresh but unpermitted input", async () => {
    const s = server();
    s.state.room.observed = s.state.now - 60;
    await s.api.start();
    expect(s.api.canChange()).toBe(true);
    s.emit({
      ...s.state,
      seq: s.state.seq + 1,
      permitted: false,
      room: { ...s.state.room, observed: s.state.now },
    });
    expect(s.api.canChange()).toBe(false);
    await expect(s.api.control("arm", s.api.session)).rejects.toThrow();
    s.api.close();
  });
  it("verifies settings by value when backend JSON keys are sorted", async () => {
    const s = server();
    await s.api.start();
    const call = s.hass.callWS.bind(s.hass);
    s.hass.callWS = async <T>(message: Record<string, unknown>) => {
      const result = await call<unknown>(message);
      if (message.type === "heating_ai/settings/get") {
        const value = result as Persisted;
        return {
          ...value,
          values: Object.fromEntries(
            Object.entries(value.values).sort(([a], [b]) => a.localeCompare(b)),
          ),
        } as T;
      }
      return result as T;
    };
    expect(
      (
        await s.api.save(
          "key-order",
          1,
          { ...defaults, day: 22 },
          s.api.session,
        )
      ).status,
    ).toBe("saved");
    s.api.close();
  });
});
it("refreshes independent STOP eligibility from the current injected HA user", async () => {
  const s = server();
  await s.api.start();
  expect(s.api.canStop()).toBe(true);
  s.api.updateConnection(true, {
    ...s.hass,
    user: { id: s.hass.user!.id, is_admin: false },
  });
  expect(s.api.canStop()).toBe(false);
  await expect(s.api.control("pause", s.api.session)).rejects.toThrow();
  s.api.close();
});
