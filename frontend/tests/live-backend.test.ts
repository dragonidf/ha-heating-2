import { describe, it, expect, vi } from "vitest";
import {
  LiveHAAPI,
  type LiveBindings,
  type NativeOverview,
} from "../src/liveHA";

describe("native backend binding", () => {
  it("uses authenticated versioned CAS, keeps conflict drafts at the caller, and never grants physical authority", async () => {
    const roles = [
      "thermostat",
      "room",
      "grid",
      "voltage_l1",
      "voltage_l2",
      "voltage_l3",
      "kws_l1",
      "kws_l2",
      "kws_l3",
      "kws_energy",
    ];
    const bindings = Object.fromEntries(
      roles.map((role) => [role, "sensor.synthetic_" + role]),
    ) as LiveBindings;
    const overview: NativeOverview = {
      version: [2, 0],
      seq: 1,
      boot_id: "synthetic.boot",
      owner_epoch: 2,
      settings: {
        revision: 7,
        values: { day_upper: 22 },
        manual_pause: true,
        energy_fault: null,
        counter: 10,
        model_frozen: true,
      },
      safety: {
        voltage_status: "CACHE_STALE_OR_MISSING",
        reason: "raw_witness_missing",
        ages: {},
      },
      controller: {
        mode: "safe_hold",
        reason: "permission_denied",
        actual_commands: 0,
      },
      model: { parameters: null, qualification: "MISSING", frozen: true },
      one_shot: { state: "unknown_outcome", expires: null },
      plan: null,
      fan: null,
      journal: { revision: 1, fenced: true, commands: {} },
      active_limit: { band: "day", target: 21, upper: 22, ceiling: 24.5 },
      physical_commands_enabled: false,
      fault: null,
    };
    const calls: Record<string, unknown>[] = [];
    const api = new LiveHAAPI(
      bindings,
      {
        states: {},
        user: { is_admin: true },
        callWS: async (msg) => {
          calls.push(msg);
          if (msg.operation === "snapshot") return overview;
          if (msg.operation === "history")
            return {
              actual: [],
              energy: [],
              original: null,
              original_status: "MISSING",
            };
          return { status: "conflict", revision: 8 };
        },
      },
      "synthetic.entry",
    );
    await vi.waitFor(() => expect(api.backend?.settings.revision).toBe(7));
    expect(api.canWriteNative).toBe(true);
    const draft = { day_upper: 23 };
    expect(await api.mutateNative("settings/save", draft, 7)).toBe("conflict");
    expect(draft).toEqual({ day_upper: 23 });
    const save = calls.find((row) => row.operation === "settings/save")!;
    expect(save.type).toBe("heating_ai_v2/backend");
    expect(save.version).toEqual([2, 0]);
    expect(save.payload).toMatchObject({
      expected_revision: 7,
      boot_id: "synthetic.boot",
      owner_epoch: 2,
    });
    expect(
      (await api.nativeHistory({ start: 1, end: 2 })).original_status,
    ).toBe("MISSING");
    expect(api.feed.value.permitted).toBe(false);
    expect(api.control("arm", api.session).status).toBe("denied");
    overview.fault = "persistence_failed";
    expect(api.canWriteNative).toBe(false);
    api.close();
    vi.useFakeTimers();
    const hung = new LiveHAAPI(
      bindings,
      {
        states: {},
        user: { is_admin: true },
        callWS: () => new Promise(() => {}),
      },
      "synthetic.hung",
    );
    try {
      await vi.advanceTimersByTimeAsync(8001);
      expect(hung.backendError).toContain("недоступний");
      expect(hung.canWriteNative).toBe(false);
    } finally {
      hung.close();
      vi.useRealTimers();
    }
  });
});
