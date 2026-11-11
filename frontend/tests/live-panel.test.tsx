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
      "sensor.fireplace": source("27.5", "°C"),
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
    const panel = document.createElement("heating-ai-v2-panel") as HTMLElement & {
      hass: LiveHass;
      panel: { config: Record<string, string> };
    };
    panel.panel = { config: mapping };
    panel.hass = hass();
    document.body.appendChild(panel);
    await waitFor(() => {
      expect(panel.shadowRoot?.textContent).toContain("Камін та циркуляція");
      expect(panel.shadowRoot?.textContent).toContain("21,5");
      expect(panel.shadowRoot?.textContent).toContain("Зупинити");
      expect(panel.shadowRoot?.textContent).toContain("Реальні дані");
      expect(panel.shadowRoot?.textContent).not.toContain("Симуляція");
    });

    panel.hass = hass("Відсутня мережа");
    await waitFor(() => expect(panel.shadowRoot?.textContent).toContain(
      "Відсутня мережа",
    ));
    expect(panel.shadowRoot?.textContent).toContain("230.0 В");

    const history = [...(panel.shadowRoot?.querySelectorAll("nav button") ?? [])]
      .find((node) => node.textContent?.includes("Історія"));
    expect(history).toBeDefined();
    fireEvent.click(history!);
    await waitFor(() => expect(panel.shadowRoot?.textContent).toContain(
      "Міграцію історії не завершено",
    ));
    const settings = [...(panel.shadowRoot?.querySelectorAll("nav button") ?? [])]
      .find((node) => node.textContent?.includes("Налаштування"));
    fireEvent.click(settings!);
    await waitFor(() => expect(panel.shadowRoot?.textContent).toContain(
      "Налаштування та модель",
    ));
    expect(panel.shadowRoot?.querySelector("[data-theme]")).not.toBeNull();
  });

  it("refuses missing bindings rather than showing synthetic readings", async () => {
    const panel = document.createElement("heating-ai-v2-panel") as HTMLElement & {
      hass: LiveHass;
      panel: { config: Record<string, string> };
    };
    panel.panel = { config: { ...mapping, kws_l3: "" } };
    panel.hass = hass();
    document.body.appendChild(panel);
    await waitFor(() => expect(panel.shadowRoot?.textContent).toContain(
      "Не вдалося перевірити прив'язки",
    ));
    expect(panel.shadowRoot?.textContent).not.toContain("Симуляція");
  });
});
