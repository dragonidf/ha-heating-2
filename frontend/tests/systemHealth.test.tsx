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
