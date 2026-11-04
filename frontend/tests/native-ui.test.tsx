import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  waitFor,
  within,
} from "@testing-library/react";
import { App } from "../src/App";
import { persisted } from "../src/contracts";
import { DemoAPI } from "../src/mock";
import { defaults, snapshot, NOW } from "../src/fixtures";
import type { OperatorAPI } from "../src/operator";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function readonlyNative(): OperatorAPI {
  const api = new DemoAPI(
    {
      read: async () => ({ revision: 1, values: defaults, lastRequest: null }),
      commit: async () => {
        throw Error("not used");
      },
    },
    0,
  );
  api.feed.reset({ ...snapshot(), permitted: false });
  return {
    ...api,
    native: true,
    feed: api.feed,
    session: api.session,
    model: api.model,
    settings: api.settings.bind(api),
    save: api.save.bind(api),
    control: api.control.bind(api),
    modelAction: api.modelAction.bind(api),
    canChange: api.canChange.bind(api),
    requestId: api.requestId.bind(api),
    reconnect: api.reconnect.bind(api),
    history: api.history.bind(api),
    energyHistory: api.energyHistory.bind(api),
    view: {
      actual: [],
      original: null,
      latest: [],
      timeline: [],
      metrics: [],
      cycleEnergy: {
        reference: null,
        known: 0,
        estimated: null,
        unknownS: 86400,
        scope: { start: NOW - 86400, end: NOW },
        projected: null,
      },
    },
    dataErrors: ["Синтетичний огляд недоступний"],
  };
}
it("navigation and skip link focus the current app main inside Shadow DOM", async () => {
  vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => {
    fn(0);
    return 0;
  });
  const host = document.createElement("div");
  document.body.append(host);
  const shadow = host.attachShadow({ mode: "open" }),
    mount = document.createElement("div");
  shadow.append(mount);
  const ui = render(<App api={readonlyNative()} />, { container: mount });
  await waitFor(() =>
    expect(
      within(mount).getByRole("button", { name: /^Налаштування$/ }),
    ).toBeTruthy(),
  );
  fireEvent.click(
    within(mount).getByRole("button", { name: /^Налаштування$/ }),
  );
  expect(shadow.activeElement).toBe(mount.querySelector("main"));
  const link = within(mount).getByRole("link", { name: "До основного вмісту" });
  link.focus();
  fireEvent.click(link);
  expect(shadow.activeElement).toBe(mount.querySelector("main"));
  ui.unmount();
  host.remove();
});
it("native missing overview shows honest actual-only History and no demo fault controls", async () => {
  const ui = render(<App api={readonlyNative()} />);
  expect(ui.getByText("Синтетичний огляд недоступний")).toBeTruthy();
  expect(ui.queryByText("Сценарії демо · синтетичні дані")).toBeNull();
  fireEvent.click(ui.getByRole("button", { name: /^Історія$/ }));
  expect(ui.getByText("MISSING · не відновлюється заднім числом")).toBeTruthy();
  expect(
    ui.getByText(
      "Немає завчасного прогнозу на цей період. Показуємо тільки доступний факт.",
    ),
  ).toBeTruthy();
});
it("native settings archive failure does not disable logical pause", async () => {
  const api = readonlyNative();
  api.feed.reset(snapshot());
  api.settings = async () => {
    throw Error("synthetic store failure");
  };
  const ui = render(<App api={api} />);
  await waitFor(() =>
    expect(
      ui.getByText("Збережені налаштування не прочитані. Зміни заблоковано."),
    ).toBeTruthy(),
  );
  const pause = ui.getByRole("button", {
    name: "Пауза симуляції",
  }) as HTMLButtonElement;
  expect(pause.disabled).toBe(false);
  expect(
    (
      ui.getByRole("button", {
        name: "Збільшити ціль на0,5 °C у симуляції",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
});

it("native missing projection never falls back to standalone fixture forecasts", () => {
  const api = readonlyNative();
  const { view: _view, ...withoutView } = api;
  const ui = render(<App api={withoutView} />);
  fireEvent.click(ui.getByRole("button", { name: /^Історія$/ }));
  expect(ui.getByText("MISSING · не відновлюється заднім числом")).toBeTruthy();
  expect(ui.queryByText("Є синтетичні докази")).toBeNull();
});

it("native independent pause remains enabled on source and settings failures", async () => {
  const api = readonlyNative();
  api.feed.reset({
    ...snapshot(),
    permitted: false,
    room: { value: null, observed: 0, quality: "missing" },
    status: { ...snapshot().status, mode: "SAFE_HOLD" },
  });
  api.canStop = () => true;
  api.settings = async () => {
    throw Error("synthetic critical failure");
  };
  const ui = render(<App api={api} />);
  await waitFor(() =>
    expect(
      ui.getByText("Збережені налаштування не прочитані. Зміни заблоковано."),
    ).toBeTruthy(),
  );
  expect(
    (ui.getByRole("button", { name: "Пауза симуляції" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
  expect(
    (
      ui.getByRole("button", {
        name: "Збільшити ціль на0,5 °C у симуляції",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
});
it("native reconnect rejection is handled with an offline message", async () => {
  const api = readonlyNative();
  api.feed.reset({ ...api.feed.value, connected: false });
  api.reconnect = async () => {
    throw Error("synthetic disconnected deadline");
  };
  const ui = render(<App api={api} />);
  fireEvent.click(ui.getByRole("button", { name: "Відновити симуляцію" }));
  await waitFor(() =>
    expect(
      ui.getByText("Зв’язок не відновлено. Останні дані лише для читання."),
    ).toBeTruthy(),
  );
});
it("settings hook accepts verified native readback with a different JSON key order", async () => {
  const api = readonlyNative();
  api.feed.reset(snapshot());
  let state = {
    revision: 1,
    values: { ...defaults },
    lastRequest: null as string | null,
  };
  api.settings = async () =>
    persisted({
      ...state,
      values: Object.fromEntries(
        Object.entries(state.values).sort(([a], [b]) => a.localeCompare(b)),
      ),
    });
  api.save = async (id, _expected, values) => {
    state = { revision: 2, values, lastRequest: id };
    return {
      request_id: id,
      status: "saved",
      revision: 2,
      persisted_revision: 2,
      reason: "Verified synthetic readback",
    };
  };
  const ui = render(<App api={api} />);
  fireEvent.click(ui.getByRole("button", { name: /^Налаштування$/ }));
  const day = ui.getByRole("spinbutton", {
    name: /Температура вдень/,
  }) as HTMLInputElement;
  await waitFor(() => expect(day.disabled).toBe(false));
  fireEvent.change(day, { target: { value: "22" } });
  fireEvent.click(ui.getByRole("button", { name: "Зберегти симуляцію" }));
  await waitFor(() =>
    expect(ui.getByText("Verified synthetic readback")).toBeTruthy(),
  );
});
