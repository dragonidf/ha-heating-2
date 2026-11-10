import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { defaults, snapshot } from "../src/fixtures";
import { validateSettings } from "../src/domain";
import { readSnapshot } from "../src/nativeContracts";
import { persisted } from "../src/contracts";
import { App } from "../src/App";
import { DemoAPI } from "../src/mock";
import type { OperatorAPI } from "../src/operator";
import type { Settings } from "../src/types";
const limits = {
  min_voltage_v: 190,
  max_voltage_v: 250,
  hysteresis_v: 5,
  stable_recovery_s: 30,
  voltage_max_age_s: 30,
};
afterEach(cleanup);
it("accepts full voltage settings and preserves exact legacy12 settings", () => {
  expect(validateSettings({ ...defaults, ...limits })).toEqual([]);
  expect(
    persisted({ revision: 1, values: defaults, lastRequest: null }).values,
  ).toEqual(defaults);
  expect(
    persisted({
      revision: 2,
      values: { ...defaults, ...limits },
      lastRequest: "synthetic-migration",
    }).values,
  ).toEqual({ ...defaults, ...limits });
});
it("rejects partial voltage schemas, unsafe bounds and non-finite expert values", () => {
  for (const change of [
    { min_voltage_v: 79 },
    { min_voltage_v: 281 },
    { max_voltage_v: 119 },
    { max_voltage_v: 301 },
    { min_voltage_v: 250, max_voltage_v: 250 },
    { hysteresis_v: -1 },
    { hysteresis_v: 31 },
    { min_voltage_v: 240, max_voltage_v: 250, hysteresis_v: 5 },
    { stable_recovery_s: -1 },
    { stable_recovery_s: 601 },
    { voltage_max_age_s: 0 },
    { voltage_max_age_s: 301 },
    { min_voltage_v: NaN },
    { voltage_max_age_s: Infinity },
  ])
    expect(
      validateSettings({ ...defaults, ...limits, ...change } as Settings)
        .length,
    ).toBeGreaterThan(0);
  expect(() =>
    persisted({
      revision: 1,
      values: { ...defaults, min_voltage_v: 190 },
      lastRequest: null,
    }),
  ).toThrow();
});
function nativeAPI(): OperatorAPI {
  const api = new DemoAPI(
    {
      read: async () => ({
        revision: 1,
        values: { ...defaults, ...limits },
        lastRequest: null,
      }),
      commit: async () => {
        throw Error("synthetic test only");
      },
    },
    0,
  );
  api.feed.reset(snapshot());
  return {
    native: true,
    feed: api.feed,
    session: api.session,
    model: api.model,
    canChange: api.canChange.bind(api),
    canStop: () => true,
    settings: api.settings.bind(api),
    save: api.save.bind(api),
    control: api.control.bind(api),
    modelAction: api.modelAction.bind(api),
    requestId: api.requestId.bind(api),
    history: api.history.bind(api),
    energyHistory: api.energyHistory.bind(api),
    reconnect: api.reconnect.bind(api),
  };
}
it("native voltage limits remain editable and use CAS plus verified readback", async () => {
  const api = nativeAPI();
  let saved = {
    revision: 1,
    values: { ...defaults, ...limits },
    lastRequest: null as string | null,
  };
  let expected: number | undefined;
  api.settings = async () => structuredClone(saved);
  api.save = async (id, revision, values) => {
    expected = revision;
    saved = {
      revision: revision + 1,
      values: values as typeof saved.values,
      lastRequest: id,
    };
    return {
      request_id: id,
      status: "saved",
      revision: saved.revision,
      persisted_revision: saved.revision,
      reason: "Synthetic voltage limits verified",
    };
  };
  const ui = render(<App api={api} />);
  fireEvent.click(ui.getByRole("button", { name: /^Налаштування$/ }));
  const minimum = await ui.findByRole("spinbutton", {
    name: /Мінімальна вхідна напруга/,
  });
  await waitFor(() =>
    expect((minimum as HTMLInputElement).disabled).toBe(false),
  );
  fireEvent.change(minimum, { target: { value: "200" } });
  fireEvent.click(ui.getByRole("button", { name: "Зберегти симуляцію" }));
  await waitFor(() =>
    expect(ui.getByText("Synthetic voltage limits verified")).toBeTruthy(),
  );
  expect(expected).toBe(1);
  expect(saved.values.min_voltage_v).toBe(200);
});

function voltage(
  status:
    "LOW" | "HIGH" | "MISSING_OR_STALE" | "STABILIZING" | "NORMAL" = "NORMAL",
) {
  return {
    status,
    eligible: status === "NORMAL",
    affected_phases: status === "NORMAL" ? [] : ["L2"],
    reason: "synthetic voltage evidence",
    ages: { L1: 2, L2: 2, L3: 2 },
    phases: ["L1", "L2", "L3"].map((phase) => ({
      phase,
      voltage_v: 230,
      age_s: 2,
      online: true,
      qualified: true,
    })),
    limits,
    source_role: "grid_input_voltage",
    source_provider: "zigbee2mqtt_input220",
    physical_authority: false,
    scope: "synthetic_only",
  };
}
it.each(["LOW", "HIGH", "MISSING_OR_STALE", "STABILIZING", "NORMAL"] as const)(
  "shows native %s input voltage, phases, evidence age and synthetic source role",
  async (status) => {
    const api = nativeAPI();
    api.feed.reset({
      ...snapshot(),
      voltage: voltage(status),
      demand_eligible: status === "NORMAL",
    } as Parameters<typeof api.feed.reset>[0]);
    const ui = render(<App api={api} />);
    expect(
      ui.getByRole("heading", { name: "Вхідна напруга мережі" }),
    ).toBeTruthy();
    expect(ui.getByText(status, { exact: false })).toBeTruthy();
    expect(ui.getByText(/Не вимір напруги на клемах котла/)).toBeTruthy();
    expect(ui.getByText(/Zigbee2MQTT input 220/)).toBeTruthy();
    expect(
      ui.getByRole("table", { name: "Синтетичні звіти вхідних фаз" }),
    ).toBeTruthy();
  },
);
it("voltage fault disables heat-demand intent without locking settings or logical STOP", async () => {
  const api = nativeAPI();
  api.feed.reset({
    ...snapshot(),
    voltage: voltage("LOW"),
    demand_eligible: false,
  } as Parameters<typeof api.feed.reset>[0]);
  const ui = render(<App api={api} />);
  await waitFor(() =>
    expect(
      (ui.getByRole("button", { name: "Пауза симуляції" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  );
  expect(
    (
      ui.getByRole("button", {
        name: "Запланувати один раз у симуляції",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.click(ui.getByRole("button", { name: /^Налаштування$/ }));
  await waitFor(() =>
    expect(
      (
        ui.getByRole("spinbutton", {
          name: /Мінімальна вхідна напруга/,
        }) as HTMLInputElement
      ).disabled,
    ).toBe(false),
  );
});

it("rejects foreign voltage roles, unknown states, malformed phases and fictitious authority", () => {
  for (const change of [
    { source_role: "boiler_voltage" },
    { source_provider: "kws_voltage" },
    { status: "invented" },
    { physical_authority: true },
    { phases: [] },
    { ages: { L1: -1, L2: 0, L3: 0 } },
    { eligible: false },
    { limits: { ...limits, min_voltage_v: NaN } },
  ])
    expect(() =>
      readSnapshot({ ...snapshot(), voltage: { ...voltage(), ...change } }),
    ).toThrow();
});

const power = {
  source_role: "boiler_power_energy",
  source_provider: "tuya_local_kws",
  cloud_duplicate_policy: "excluded_no_fallback",
  stage: "~6kW",
  total_active_w: 6100,
  total_imported_kwh: 1234.5,
  phases: [
    { phase: "L1", active_w: 2800, age_s: 1 },
    { phase: "L2", active_w: 3300, age_s: 1 },
    { phase: "L3", active_w: 0, age_s: 1 },
  ],
  reason: "synthetic calibrated asymmetric profile",
  physical_authority: false,
  physical_heat: null,
  scope: "synthetic_only",
};
it.each(["OFF", "PUMP_ONLY", "~3kW", "~6kW", "~9kW", "UNKNOWN"])(
  "shows KWS %s only as a synthetic stage estimate and excludes cloud duplicate",
  (stage) => {
    const api = nativeAPI();
    api.feed.reset({ ...snapshot(), power: { ...power, stage } } as Parameters<
      typeof api.feed.reset
    >[0]);
    const ui = render(<App api={api} />);
    expect(
      ui.getByRole("heading", { name: "Потужність та лічильник котла" }),
    ).toBeTruthy();
    expect(ui.getByText(stage, { exact: true })).toBeTruthy();
    expect(ui.getByText(/KWS через Tuya Local/)).toBeTruthy();
    expect(ui.getByText(/Хмарна копія Tuya не додається/)).toBeTruthy();
    expect(ui.getByText(/Стан реле не доводить нагрів/)).toBeTruthy();
  },
);
it("rejects cloud/mixed KWS evidence, fictitious physical heat and malformed stage", () => {
  for (const change of [
    { source_provider: "tuya_cloud" },
    { cloud_duplicate_policy: "sum" },
    { stage: "verified_6kW" },
    { physical_heat: true },
    { physical_authority: true },
    { total_imported_kwh: -1 },
    { phases: [] },
    { total_active_w: NaN },
  ])
    expect(() =>
      readSnapshot({ ...snapshot(), power: { ...power, ...change } }),
    ).toThrow();
});
