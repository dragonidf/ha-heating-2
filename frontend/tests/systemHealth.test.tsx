import { afterEach, expect, it } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/react";
import { SystemHealth } from "../src/SystemHealth";
import { readSnapshot } from "../src/nativeContracts";
import { snapshot } from "../src/fixtures";
import type { SystemHealthView } from "../src/types";
afterEach(cleanup);
function health(): SystemHealthView {
  return {
    mode: "WAITING",
    notification: null,
    last_notice: "Очікуємо мережу",
    physical_verified: false,
    semantics: "proposed_only_no_device_ack",
    components: [
      "living_room",
      "fireplace",
      "thermostat",
      "utility",
      "kws",
      "controller",
    ].map((key) => ({
      key,
      label: key === "utility" ? "Мережа" : key,
      status: "WAITING",
      reason: "Очікування мережі/KWS",
      severity: "warning",
      age_s: null,
      checked_at: 1,
      last_transition: 1,
      physical_verified: false,
      fallback_action: "WAITING",
    })),
  };
}
it("shows compact counts and actionable waiting reason, with expandable component ages", () => {
  const ui = render(<SystemHealth health={health()} />);
  expect(ui.getByLabelText("Стан системи")).toBeTruthy();
  expect(ui.getByText(/OK 0/)).toBeTruthy();
  fireEvent.click(ui.getByText(/Стан системи/));
  expect(ui.getAllByText(/Давність невідома/)).toHaveLength(6);
  expect(ui.getByText(/Фізичний стан не підтверджений/)).toBeTruthy();
});
it("surfaces a genuine fault without false OK or physical confirmation", () => {
  const h = health();
  h.components = h.components.map((c, i) =>
    i === 0
      ? {
          ...c,
          status: "PROBLEM",
          reason: "Немає підтверджених звітів вітальні",
        }
      : c,
  );
  const ui = render(<SystemHealth health={h} />);
  expect(ui.getByRole("alert").textContent).toContain("вітальні");
  expect(ui.queryByText(/AUTO_PROPOSED/)).toBeNull();
});
it("validates optional shared snapshot health and rejects malformed or fake physical OK", () => {
  const s = { ...snapshot(), system_health: health() };
  expect(readSnapshot(s).system_health?.components).toHaveLength(6);
  for (const bad of [
    {
      ...s.system_health,
      proposal: {
        id: "synthetic.bad",
        stage: "proposed",
        action: "proposed_fallback",
        mode: "AUTO",
        physical_authority: true,
      },
    },
    { ...s.system_health, physical_verified: true },
    { ...s.system_health, components: [] },
    {
      ...s.system_health,
      components: s.system_health.components.map((c) => ({ ...c, age_s: -1 })),
    },
  ])
    expect(() => readSnapshot({ ...s, system_health: bad })).toThrow();
});
it("labels a HEAT proposal as proposed rather than completed handoff", () => {
  const h = health();
  h.mode = "HEAT_PROPOSED";
  h.components = h.components.map((c) => ({
    ...c,
    fallback_action: "HEAT_PROPOSED",
  }));
  const ui = render(<SystemHealth health={h} />);
  fireEvent.click(ui.getByText(/Стан системи/));
  expect(ui.getAllByText(/Запропоновано повернення HEAT/)).toHaveLength(6);
  expect(ui.getByText(/Фізичний стан не підтверджений/)).toBeTruthy();
});

function sourceHealth(): SystemHealthView {
  return {
    ...health(),
    source_freshness: {
      living_device_last_activity: 100,
      living_temperature_last_observed: 0,
      return_water_last_observed: 100,
      device_age_s: 0,
      temperature_age_s: 100,
      return_age_s: 0,
      activity_window_s: 3660,
      device_quality: "OK",
      temperature_quality: "STALE",
      return_quality: "OK",
      return_veto: false,
      failure_confirmed: false,
      physical_authority: false,
      scope: "synthetic_only",
    },
  };
}
it("separates humidity activity from stale temperature and auxiliary probe", () => {
  const ui = render(<SystemHealth health={sourceHealth()} />);
  expect(ui.getByText(/Активність пристрою T&H: OK/)).toBeTruthy();
  expect(
    ui.getByText(/Реальний вимір вітальні: Очікування даних · 100 с/),
  ).toBeTruthy();
  expect(ui.getByText(/Зовнішній щуп обратки: OK/)).toBeTruthy();
  expect(
    ui.getByText(/Поріг активності 3660 с — лише попередження/),
  ).toBeTruthy();
  expect(ui.getByText(/Вологість не оновлює температуру/)).toBeTruthy();
});
it("shows source failure and return veto without physical acknowledgement", () => {
  const h = sourceHealth();
  if (!h.source_freshness) throw Error("fixture missing");
  h.source_freshness = {
    ...h.source_freshness,
    temperature_quality: "OFFLINE",
    return_veto: true,
    failure_confirmed: true,
  };
  const ui = render(<SystemHealth health={h} />);
  expect(ui.getByText(/джерело недоступне/)).toBeTruthy();
  expect(ui.getByText(/вето нагріву/)).toBeTruthy();
  expect(ui.getByText(/Фізичний стан не підтверджений/)).toBeTruthy();
});
it("rejects false source provenance and malformed independent ages", () => {
  const h = sourceHealth();
  expect(
    readSnapshot({ ...snapshot(), system_health: h }).system_health
      ?.source_freshness?.device_quality,
  ).toBe("OK");
  for (const bad of [
    { temperature_age_s: -1 },
    { device_quality: "OFFLINE" },
    { physical_authority: true },
    { activity_window_s: Infinity },
    { scope: "physical" },
    { return_veto: "yes" },
    { temperature_quality: "fresh" },
  ]) {
    expect(() =>
      readSnapshot({
        ...snapshot(),
        system_health: {
          ...h,
          source_freshness: { ...h.source_freshness, ...bad },
        },
      }),
    ).toThrow();
  }
});
it("shows passive HA timing separately from qualified recovery policy and rejects fake ACK", () => {
  const h = sourceHealth();
  if (!h.source_freshness) throw Error("fixture missing");
  h.source_freshness = {
    ...h.source_freshness,
    activity_provenance: "ha_state_write",
    measurement_authorization_age_s: 30,
    recovery_dwell_s: 15,
    recovery_policy_ready: true,
    physical_commands_enabled: false,
  };
  h.passive_sources = [
    {
      role: "temperature",
      value: 22,
      last_reported: 100,
      last_updated: 90,
      last_changed: 80,
      available: true,
      origin: "ha_state_write",
      physical_measurement: "BLOCKED",
      physical_commands_enabled: false,
    },
  ];
  const ui = render(<SystemHealth health={h} />);
  expect(ui.getByText(/Дозвіл виміру: 30 с/)).toBeTruthy();
  expect(ui.getByText(/запис HA не є виміром пристрою/)).toBeTruthy();
  expect(
    readSnapshot({ ...snapshot(), system_health: h }).system_health
      ?.passive_sources,
  ).toHaveLength(1);
  for (const bad of [
    { physical_measurement: "CONFIRMED" },
    { physical_commands_enabled: true },
    { last_updated: 101 },
    { role: "thermostat" },
  ])
    expect(() =>
      readSnapshot({
        ...snapshot(),
        system_health: {
          ...h,
          passive_sources: [{ ...h.passive_sources![0], ...bad }],
        },
      }),
    ).toThrow();
  expect(() =>
    readSnapshot({
      ...snapshot(),
      system_health: {
        ...h,
        source_freshness: { ...h.source_freshness, recovery_dwell_s: 30 },
      },
    }),
  ).toThrow();
});
