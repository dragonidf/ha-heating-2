// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { waitFor, fireEvent } from "@testing-library/react";
import "../src/live-panel";
import type { LiveHass } from "../src/liveHA";

const stamp = new Date().toISOString();
const source = (state: string, unit = "") => ({
  state,
  last_reported: stamp,
  last_changed: stamp,
  attributes: { unit_of_measurement: unit },
});
const mapping = {
  thermostat: "climate.boiler",
  room: "sensor.room",
  grid: "input_select.grid",
  voltage_l1: "sensor.v1",
  voltage_l2: "sensor.v2",
  voltage_l3: "sensor.v3",
  kws_l1: "sensor.kws1",
  kws_l2: "sensor.kws2",
  kws_l3: "sensor.kws3",
  kws_energy: "sensor.kwh",
  return_probe: "sensor.return_probe",
  fireplace: "sensor.fireplace",
  circulation: "fan.local",
  fan_mode: "input_select.fan_mode",
  fan_night: "input_number.night",
  fan_standard: "input_number.standard",
  fan_intense: "input_number.intense",
};
function hass(grid = "Наявна мережа"): LiveHass {
  return {
    connected: true,
    callWS: async (_request: Record<string, unknown>) => ({
      "sensor.room": [{ s: "21.5", lu: Date.now() / 1000 - 600 }],
    }),
    states: {
      "climate.boiler": {
        ...source("heat"),
        attributes: { temperature: 20.5 },
      },
      "sensor.room": source("21.5", "°C"),
      "input_select.grid": source(grid),
      "sensor.v1": source("230", "V"),
      "sensor.v2": source("231", "V"),
      "sensor.v3": source("232", "V"),
      "sensor.kws1": source("0", "kW"),
      "sensor.kws2": source("0.012", "kW"),
      "sensor.kws3": source("0", "kW"),
      "sensor.kwh": source("160.7", "kWh"),
      "sensor.return_probe": source("22.1", "°C"),
      "sensor.fireplace": source("27.5", "°C"),
      "sensor.v2_status": {
        ...source("SHADOW"),
        attributes: {
          v2_entry_id: "synthetic-entry",
          coast_preview: {
            status: "UNQUALIFIED_CONDITIONAL_COAST",
            temperature_min_c: 20.8,
            temperature_end_c: 20.8,
            hours_covered: 8,
            forecast_qualified: false,
            commands_enabled: false,
          },
          provider_summary: {
            weather_status: "RECEIVED_ISSUED_UNKNOWN",
            weather_hours_count: 23,
            weather_horizon_end: Date.now() / 1000 + 20000,
            weather_issued_at: null,
            outage_status: "OUTAGE_EVENTS_ONLY",
            next_outage_at: Date.now() / 1000 + 2400,
            outages_upcoming_count: 2,
            normal_grid_forecast_qualified: false,
          },
        },
      },
      "fan.local": {
        ...source("off"),
        attributes: { percentage: 42 },
      },
      "input_select.fan_mode": source("Зупинити"),
      "input_number.night": source("38", "%"),
      "input_number.standard": source("42", "%"),
      "input_number.intense": source("45", "%"),
    },
  };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("Actual Home Assistant custom panel mounting", () => {
  it("mounts the real 3-tab UI and updates from HA without demo fallback", async () => {
    const panel = document.createElement(
      "heating-ai-v2-panel",
    ) as HTMLElement & {
      hass: LiveHass;
      panel: { config: Record<string, string> };
    };
    panel.panel = { config: { ...mapping, entry_id: "synthetic-entry" } };
    panel.hass = hass();
    document.body.appendChild(panel);
    await waitFor(() => {
      expect(panel.shadowRoot?.textContent).toContain("Зворотна лінія котла");
      expect(panel.shadowRoot?.textContent).toContain("Камін та циркуляція");
      expect(panel.shadowRoot?.textContent).toContain("23 точок");
      expect(panel.shadowRoot?.textContent).toContain("20,8 °C");
      expect(panel.shadowRoot?.textContent).toContain(
        "Час випуску погодного прогнозу",
      );
      expect(panel.shadowRoot?.textContent).toContain("21,5");
      expect(panel.shadowRoot?.textContent).toContain("Зупинити");
      expect(panel.shadowRoot?.textContent).toContain("Реальні дані");
      expect(panel.shadowRoot?.textContent).not.toContain("Симуляція");
    });

    panel.hass = hass("Відсутня мережа");
    await waitFor(() =>
      expect(panel.shadowRoot?.textContent).toContain("Відсутня мережа"),
    );
    expect(panel.shadowRoot?.textContent).toContain("230.0 В");

    const history = [
      ...(panel.shadowRoot?.querySelectorAll("nav button") ?? []),
    ].find((node) => node.textContent?.includes("Історія"));
    expect(history).toBeDefined();
    fireEvent.click(history!);
    await waitFor(() =>
      expect(panel.shadowRoot?.textContent).toContain(
        "Міграцію історії не завершено",
      ),
    );
    await waitFor(() =>
      expect(panel.shadowRoot?.textContent).toContain("Записи HA: 1"),
    );
    const settings = [
      ...(panel.shadowRoot?.querySelectorAll("nav button") ?? []),
    ].find((node) => node.textContent?.includes("Налаштування"));
    fireEvent.click(settings!);
    await waitFor(() =>
      expect(panel.shadowRoot?.textContent).toContain("Налаштування та модель"),
    );
    expect(panel.shadowRoot?.querySelector("[data-theme]")).not.toBeNull();
  });

  it("plots the real conditional 24h trajectory and proposed heat windows, without issuing commands", async () => {
    const ha = hass();
    const now = Date.now() / 1000;
    const state = ha.states["sensor.v2_status"];
    expect(state).toBeDefined();
    state!.attributes.virtual_plan = {
      status: "VIRTUAL_CONDITIONAL",
      reason: "comfort_shortfall",
      computed_at: now,
      projected_min_c: 20.5,
      nominal_energy_kwh: 3.5,
      horizon_hours: 24,
      segment_count: 1,
      segments_truncated: false,
      segments: [{ start: now + 600, end: now + 1800, conditional: true }],
      trajectory: [300, 600, 900].map(offset => ({
        at: now + offset, value: 21.3 - offset / 3000, quality: "estimated",
      })),
    };
    const panel = document.createElement("heating-ai-v2-panel") as HTMLElement & {
      hass: LiveHass; panel: { config: Record<string, string> };
    };
    panel.panel = { config: { ...mapping, entry_id: "synthetic-entry" } };
    panel.hass = ha;
    document.body.appendChild(panel);
    await waitFor(() => {
      const root = panel.shadowRoot;
      expect(root?.textContent).toContain("Температура та план нагріву");
      expect(root?.querySelectorAll("path.timeline-forecast").length).toBeGreaterThan(0);
      expect(root?.querySelectorAll("rect.timeline-heat").length).toBe(1);
      expect(root?.textContent).toContain("Умовний нагрів");
      expect(root?.textContent).toContain("20,5°");
      expect(root?.querySelector("details.live-technical")?.hasAttribute("open")).toBe(false);
      expect(root?.textContent).toContain("SHADOW · без команд");
    });
    expect(ha.states["climate.boiler"]?.state).toBe("heat");
  });

  it("gets the full trajectory from authenticated backend while HA Recorder attributes stay compact", async () => {
    const ha = hass();
    const now = Date.now() / 1000;
    const plan = {
      status: "VIRTUAL_CONDITIONAL",
      reason: "comfort_shortfall",
      computed_at: now,
      projected_min_c: 20.4,
      nominal_energy_kwh: 4.3,
      horizon_hours: 24,
      segment_count: 1,
      segments_truncated: false,
      segments: [{ start: now + 450, end: now + 2400, conditional: true }],
      trajectory: [300, 600, 900].map(offset => ({
        at: now + offset, value: 21.2 - offset / 3500, quality: "estimated",
      })),
    };
    const row = ha.states["sensor.v2_status"];
    expect(row).toBeDefined();
    // A real sensor must NOT publish the expensive forecast curve into Recorder.
    const { trajectory: _hidden, ...compact } = plan;
    row!.attributes.virtual_plan = compact;
    ha.callWS = async message => {
      if (message.type === "heating_ai_v2/backend" && message.operation === "snapshot") {
        return {
          version: [2, 0], seq: 1, boot_id: "isolated", owner_epoch: 0,
          settings: {
            revision: 0, values: {
              day_target: 21.5, night_target: 20.5,
              sleep_start: "23:00:00", sleep_end: "06:30:00",
            }, manual_pause: true, energy_fault: null, counter: null, model_frozen: true,
          },
          safety: { voltage_status: "UNQUALIFIED", reason: "shadow", ages: {} },
          controller: { mode: "safe_hold", reason: "hard_stop", actual_commands: 0 },
          active_limit: { band: "day", target: 21.5, upper: 22.0, ceiling: 24.5 },
          model: { parameters: null, qualification: "NOT_PARITY_VERIFIED", frozen: true },
          one_shot: { state: "unknown_outcome", expires: null },
          journal: { revision: 0, fenced: true, commands: {} },
          fan: null, plan, physical_commands_enabled: false, fault: null,
        };
      }
      return { "sensor.room": [{ s: "21.5", lu: now - 600 }] };
    };
    const panel = document.createElement("heating-ai-v2-panel") as HTMLElement & {
      hass: LiveHass; panel: { config: Record<string, string> };
    };
    panel.panel = { config: { ...mapping, entry_id: "synthetic-entry" } };
    panel.hass = ha;
    document.body.appendChild(panel);
    await waitFor(() => {
      const root = panel.shadowRoot;
      expect(root?.querySelectorAll("path.timeline-forecast").length).toBeGreaterThan(0);
      expect(root?.querySelectorAll("rect.timeline-heat").length).toBe(1);
      expect(root?.textContent).toContain("20,4°");
      expect(root?.textContent).toContain("SHADOW · без команд");
    });
    expect((row!.attributes.virtual_plan as Record<string, unknown>).trajectory).toBeUndefined();
  });

  it("refuses missing bindings rather than showing synthetic readings", async () => {
    const panel = document.createElement(
      "heating-ai-v2-panel",
    ) as HTMLElement & {
      hass: LiveHass;
      panel: { config: Record<string, string> };
    };
    panel.panel = { config: { ...mapping, kws_l3: "" } };
    panel.hass = hass();
    document.body.appendChild(panel);
    await waitFor(() =>
      expect(panel.shadowRoot?.textContent).toContain(
        "Не вдалося перевірити прив'язки",
      ),
    );
    expect(panel.shadowRoot?.textContent).not.toContain("Симуляція");
  });
});
