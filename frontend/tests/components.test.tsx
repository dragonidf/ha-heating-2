import { describe, it, expect, afterEach } from "vitest";
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import "fake-indexeddb/auto";
import { App } from "../src/App";
import { DemoAPI } from "../src/mock";
import { BrowserStore } from "../src/storage";
afterEach(cleanup);
const setup = () => {
  const api = new DemoAPI(
    new BrowserStore("synthetic-component-" + crypto.randomUUID()),
    0,
  );
  render(<App api={api} />);
  return api;
};
describe("rendered operator flows", () => {
  it("missing room renders unknown not zero; one priority alert", async () => {
    const api = setup();
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: /Збільшити ціль/ })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    fireEvent.click(screen.getByText("Сценарії демо · синтетичні дані"));
    fireEvent.change(screen.getByLabelText("Сценарій", { exact: true }), {
      target: { value: "missing" },
    });
    expect(screen.getByRole("alert").textContent).toContain("Немає свіжого");
    expect(api.feed.value.room.value).toBeNull();
    expect(document.querySelector(".room-value")?.textContent).toBe("—°C");
  });
  it("save failure preserves draft and previous durable settings", async () => {
    const api = setup();
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: /Збільшити ціль/ })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: "Налаштування" }));
    const day = screen.getByRole("spinbutton", { name: /Температура вдень/ });
    fireEvent.change(day, { target: { value: "22" } });
    api.fault = "write";
    fireEvent.click(screen.getByRole("button", { name: "Зберегти симуляцію" }));
    await screen.findByText(/Запис або перевірку не підтверджено/);
    expect((day as HTMLInputElement).value).toBe("22");
    expect((await api.settings()).values.day).toBe(21.5);
  });
  it("settings conflict preserves draft and requires explicit rebase", async () => {
    const api = setup();
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: /Збільшити ціль/ })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: "Налаштування" }));
    const day = screen.getByRole("spinbutton", { name: /Температура вдень/ });
    fireEvent.change(day, { target: { value: "22" } });
    const state = await api.settings();
    await api.save(
      "synthetic.other",
      state.revision,
      { ...state.values, day: 23 },
      api.session,
    );
    fireEvent.click(screen.getByRole("button", { name: "Зберегти симуляцію" }));
    await screen.findByRole("heading", {
      name: "Налаштування змінилися в іншому вікні",
    });
    expect((day as HTMLInputElement).value).toBe("22");
    expect(
      screen
        .getByRole("button", { name: "Зберегти симуляцію" })
        .hasAttribute("disabled"),
    ).toBe(true);
  });
});
describe("late or unverifiable save acknowledgements", () => {
  it("a wrong request receipt cannot leave an infinite saving state", async () => {
    class WrongReceipt extends DemoAPI {
      override async save(...args: Parameters<DemoAPI["save"]>) {
        const r = await super.save(...args);
        return { ...r, request_id: "synthetic.wrong-request" };
      }
    }
    const api = new WrongReceipt(
      new BrowserStore("synthetic-wrong-" + crypto.randomUUID()),
      0,
    );
    render(<App api={api} />);
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: /Збільшити ціль/ })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: "Налаштування" }));
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Температура вдень/ }),
      { target: { value: "22" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Зберегти симуляцію" }));
    await screen.findByText(/Непідтверджений запит/);
    expect(screen.queryByText("Збережено лише в симуляції")).toBeNull();
  });
  it("failed client readback after a receipt preserves draft without success", async () => {
    class ReadbackFailure extends DemoAPI {
      calls = 0;
      override async settings() {
        this.calls++;
        if (this.calls > 1) throw Error("synthetic unavailable");
        return super.settings();
      }
    }
    const api = new ReadbackFailure(
      new BrowserStore("synthetic-client-read-" + crypto.randomUUID()),
      0,
    );
    render(<App api={api} />);
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: /Збільшити ціль/ })
          .hasAttribute("disabled"),
      ).toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: "Налаштування" }));
    fireEvent.change(
      screen.getByRole("spinbutton", { name: /Температура вдень/ }),
      { target: { value: "22" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Зберегти симуляцію" }));
    await screen.findByText(/Підтвердження не перевірено/);
    expect(screen.queryByText("Збережено лише в симуляції")).toBeNull();
    expect(
      (
        screen.getByRole("spinbutton", {
          name: /Температура вдень/,
        }) as HTMLInputElement
      ).value,
    ).toBe("22");
  });
});
