import { describe, expect, it } from "vitest";
import { LiveHAAPI, type LiveBindings, type LiveHass } from "../src/liveHA";

const bindings: LiveBindings = {
  thermostat: "climate.boiler",
  room: "sensor.living",
  grid: "input_select.grid",
  voltage_l1: "sensor.voltage_a",
  voltage_l2: "sensor.voltage_b",
  voltage_l3: "sensor.voltage_c",
  kws_l1: "sensor.kws_a",
  kws_l2: "sensor.kws_b",
  kws_l3: "sensor.kws_c",
  kws_energy: "sensor.kws_energy",
};
const s = (state: string, unit = "", last = new Date().toISOString()) => ({
  state,
  last_changed: last,
  last_reported: last,
  attributes: { unit_of_measurement: unit },
});
function frame(grid = "Наявна мережа"): LiveHass {
  return {
    connected: true,
    states: {
      "climate.boiler": { ...s("heat"), attributes: { temperature: 20.5 } },
      "sensor.living": s("21.3", "°C"),
      "input_select.grid": s(grid),
      "sensor.voltage_a": s("230", "V"),
      "sensor.voltage_b": s("230", "V"),
      "sensor.voltage_c": s("230", "V"),
      "sensor.kws_a": s("0", "kW", "2026-11-11T12:00:00Z"),
      "sensor.kws_b": s("0.012", "kW"),
      "sensor.kws_c": s("0", "kW", "2026-11-11T12:00:00Z"),
      "sensor.kws_energy": s("160.7", "kWh"),
    },
  };
}
describe("Real HA v2 live bridge (no actuator)", () => {
  it("uses authoritative grid selector, never cached phase volts", () => {
    const api = new LiveHAAPI(bindings, frame("Відсутня мережа"));
    expect(api.feed.value.grid).toBe(false);
    expect(api.telemetry.voltages).toEqual([230, 230, 230]);
    expect(api.feed.value.permitted).toBe(false);
    expect(api.feed.value.status.physical_verified).toBe(false);
    expect(api.telemetry.origin).toBe("ha_last_known");
  });
  it("retains unchanged zero KWS phases without inventing a fresh sample", () => {
    const api = new LiveHAAPI(bindings, frame());
    expect(api.telemetry.kws).toEqual([0, 0.012, 0]);
    expect(api.telemetry.kwsTotal).toBe(0.012);
    expect(api.telemetry.lastReported.kws_l1).toBe("2026-11-11T12:00:00Z");
    expect(api.feed.value.status.actual).toBe(null);
  });
  it("does not substitute zero for missing offline KWS", () => {
    const h = frame();
    h.states["sensor.kws_c"] = s("unavailable", "kW");
    const api = new LiveHAAPI(bindings, h);
    expect(api.telemetry.kwsTotal).toBe(null);
    expect(api.telemetry.kws[2]).toBe(null);
  });
  it("rejects abnormal units and cloud aliases without mapping bypass", () => {
    const h = frame();
    h.states["sensor.kws_b"] = s("1500", "W");
    const api = new LiveHAAPI(bindings, h);
    expect(api.telemetry.kwsTotal).toBe(null);
    expect(
      () => new LiveHAAPI({ ...bindings, kws_l2: bindings.kws_l1 }, h),
    ).toThrow();
  });
  it("unknown/unavailable grid never equals availability", () => {
    const api = new LiveHAAPI(bindings, frame("unavailable"));
    expect(api.feed.value.grid).toBe(null);
    api.updateHass(frame("on"));
    expect(api.feed.value.grid).toBe(null);
    api.updateHass(frame("Наявна мережа"));
    expect(api.feed.value.grid).toBe(true);
    expect(api.canChange()).toBe(false);
  });
  it("never exposes a write path and never produces fake history", async () => {
    const api = new LiveHAAPI(bindings, frame());
    expect(api.canChange()).toBe(false);
    expect(api.canStop()).toBe(false);
    expect(api.feed.value.status.mode).toBe("SHADOW");
    expect(api.control("arm", api.session).status).toBe("denied");
    await expect(api.settings()).rejects.toThrow();
    await expect(api.save("id", 1, {} as never, api.session)).rejects.toThrow();
    expect(() => api.history({ start: 1, end: 2 })).toThrow();
    expect(api.view.original).toBe(null);
    expect(api.view.latest).toEqual([]);
  });
  it("reflects device updates as observed states only", () => {
    const api = new LiveHAAPI(bindings, frame());
    const old = api.feed.value.seq;
    const h = frame();
    h.states["sensor.living"] = s("22.1", "°C");
    api.updateHass(h);
    expect(api.feed.value.seq).toBe(old + 1);
    expect(api.feed.value.room.value).toBe(22.1);
    expect(api.feed.value.permitted).toBe(false);
  });
});
