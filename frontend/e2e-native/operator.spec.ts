import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  backendStatus,
  qualifySource,
  sourceEvent,
  shadowContext,
} from "./helpers";
const panelPath = process.env.TEST_HA_PANEL_PATH ?? "/heating-ai";
async function login(page: Page) {
  const username = process.env.TEST_HA_USER,
    password = process.env.TEST_HA_PASSWORD;
  if (!username || !password)
    throw Error(
      "Disposable HA synthetic credentials required via TEST_HA_USER/TEST_HA_PASSWORD",
    );
  await page.goto(panelPath);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: /log in|увійти|войти/i }).click();
  await expect(page.locator("heating-ai-panel")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Дім", exact: true }),
  ).toBeAttached();
  await expect(page.locator("dialog-http-pending-config")).toHaveCount(0);
}
async function setSimulation(page: Page, enabled: boolean) {
  const select = async (value: boolean) => {
    await page.evaluate(
      async ({ enabled }) => {
        const app = document.querySelector("home-assistant") as HTMLElement & {
          hass: {
            panels: Record<string, { config: { entry_id: string } }>;
            callApi<T>(
              method: string,
              path: string,
              parameters?: unknown,
            ): Promise<T>;
          };
        };
        const entryId = app.hass.panels["heating-ai"]!.config.entry_id;
        const flow = await app.hass.callApi<{ flow_id: string }>(
          "POST",
          "config/config_entries/options/flow",
          { handler: entryId },
        );
        const result = await app.hass.callApi<{ type: string }>(
          "POST",
          `config/config_entries/options/flow/${flow.flow_id}`,
          { simulation_enabled: enabled },
        );
        if (result.type !== "create_entry")
          throw Error("Synthetic options flow failed closed");
      },
      { enabled: value },
    );
    await expect
      .poll(async () => {
        try {
          return await page.evaluate(async () => {
            const app = document.querySelector(
              "home-assistant",
            ) as HTMLElement & {
              hass: {
                panels: Record<string, { config: { entry_id: string } }>;
                callWS<T>(message: Record<string, unknown>): Promise<T>;
              };
            };
            const result = await app.hass.callWS<{ enabled: boolean }>({
              type: "heating_ai/overview",
              entry_id: app.hass.panels["heating-ai"]!.config.entry_id,
              version: [2, 0],
            });
            return result.enabled;
          });
        } catch {
          return null;
        }
      })
      .toBe(value);
  };
  // An explicit off/on fixture setup guarantees a new boot with no cached source assertion.
  if (enabled) await select(false);
  await select(enabled);
  // HA routes away while a native panel is unregistered during entry reload.
  await page.goto(panelPath);
  await expect(
    page.getByRole("heading", { name: "Дім", exact: true }),
  ).toBeAttached();
  if (enabled) {
    const empty = await backendStatus(page);
    expect(empty.room.value).toBeNull();
    expect(empty.room.quality).toBe("missing");
    expect(empty.permitted).toBe(false);
    await qualifySource(page, 1);
    // Previous tests may have explicitly paused; this is an explicit user resume in the synthetic fixture.
    if ((await backendStatus(page)).status.mode === "MANUAL_PAUSE") {
      await page
        .getByRole("button", { name: "Продовжити в симуляції", exact: true })
        .click();
      await expect
        .poll(async () => (await backendStatus(page)).status.mode)
        .toBe("RECOVERING");
      await qualifySource(page, 2);
    }
  }
}
test.beforeEach(async ({ page }) => {
  // The network-none namespace has a reachable loopback HA but no routable NIC.
  // Explicitly emulate that online test link through the browser protocol;
  // this changes no container route and leaves the real offline transition test intact.
  console.info(
    "Cold namespace navigator.onLine:",
    await page.evaluate(() => navigator.onLine),
  );
  await page.context().setOffline(true);
  await page.context().setOffline(false);
  expect(await page.evaluate(() => navigator.onLine)).toBe(true);
  await login(page);
});
test("native authenticated registration, disabled simulation and shadow isolation", async ({
  page,
}, info) => {
  await setSimulation(page, false);
  const panel = page.locator("heating-ai-panel");
  await expect(
    panel.getByRole("status").filter({ hasText: /^Лише читання\. Симуляція/ }),
  ).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Збільшити ціль на0,5 °C у симуляції" }),
  ).toBeDisabled();
  await expect(
    panel.getByText("Фізичний стан котла — невідомий"),
  ).toBeVisible();
  await expect(panel.locator(".simulation-lab")).toHaveCount(0);
  expect(await panel.evaluate((element) => !!element.shadowRoot)).toBe(true);
  await page.screenshot({
    path: info.outputPath("native-disabled.png"),
    fullPage: true,
  });
});
test("native backend history, immutable original evidence and independently scoped energy", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Історія", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Читаємо синтетичний архів…")).toHaveCount(0);
  await page.getByText("Докази завчасного прогнозу", { exact: true }).click();
  await expect(
    page.getByText("Є синтетичні докази", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Показник", { exact: true }).selectOption("energy");
  await expect(
    page.getByText(/Архів енергії або тарифи недоступні/),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "30 днів", exact: true }).click();
  await expect(page.getByText("Читаємо синтетичний архів…")).toHaveCount(0);
});
test("native enabled simulation saves with server CAS and survives panel reload", async ({
  page,
}) => {
  await setSimulation(page, true);
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  const day = page.getByRole("spinbutton", { name: "Температура вдень" });
  await expect(day).toBeEnabled();
  const before = await day.inputValue(),
    next = before === "22" ? "23" : "22";
  await day.fill(next);
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    page.getByText("Чернетка відповідає збереженому стану", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  await expect(day).toHaveValue(next);
  await day.fill("99");
  await expect(
    page.getByRole("button", { name: "Зберегти симуляцію", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Скасувати", exact: true }).click();
  await expect(day).toHaveValue(next);
  await page.getByRole("button", { name: "Дім", exact: true }).click();
  await sourceEvent(page, { invalid: true });
  await expect
    .poll(async () => (await backendStatus(page)).permitted)
    .toBe(false);
  await expect(
    page.getByRole("button", { name: "Збільшити ціль на0,5 °C у симуляції" }),
  ).toBeDisabled();
  const pause = page.getByRole("button", {
    name: "Пауза симуляції",
    exact: true,
  });
  await expect(pause).toBeEnabled();
  await pause.click();
  await expect
    .poll(async () => (await backendStatus(page)).status.mode)
    .toBe("MANUAL_PAUSE");
  await expect(page.getByText("Фізичний стан котла — невідомий")).toBeVisible();
});
test("native HA disconnect disables writes and ready reconnect refreshes authoritative state", async ({
  page,
  context,
}) => {
  await setSimulation(page, true);
  const target = page.getByRole("button", {
    name: "Збільшити ціль на0,5 °C у симуляції",
  });
  await expect(target).toBeEnabled();
  await context.setOffline(true);
  await expect(target).toBeDisabled();
  await expect(page.getByText("Немає зв’язку · останні дані")).toBeVisible();
  await context.setOffline(false);
  // Online must obtain a fresh snapshot even when HA's socket never closed.
  await expect(target).toBeEnabled();
  await expect(page.getByText("Фізичний стан котла — невідомий")).toBeVisible();
});
test("native theme, keyboard, responsive and accessible UI in HA shadow root", async ({
  page,
}, info) => {
  const panel = page.locator("heating-ai-panel");
  await panel.getByRole("button", { name: "Увімкнути світлу тему" }).click();
  await expect(panel.locator(".app")).toHaveAttribute("data-theme", "light");
  const context = await panel.evaluate(shadowContext);
  const light = await new AxeBuilder({ page })
    .include(context)
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(light.violations).toEqual([]);
  await panel.getByRole("button", { name: "Увімкнути темну тему" }).click();
  await panel.getByRole("button", { name: "Історія", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(panel.locator("main")).toBeFocused();
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  await page.getByText("Модель і діагностика", { exact: true }).click();
  await panel
    .getByText("Докази відновлення енергії та безпека", { exact: true })
    .click();
  await expect(panel.getByText(/^G1\/B01–B08 BLOCKED\./)).toBeVisible();
  const results = await new AxeBuilder({ page })
    .include(context)
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(results.violations).toEqual([]);
  expect(await panel.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: info.outputPath("native-diagnostics.png"),
    fullPage: true,
  });
});
test("native module stays on existing authenticated HA connection without external runtime requests", async ({
  page,
}) => {
  const external: string[] = [],
    sockets: string[] = [];
  const base = new URL(page.url()).origin;
  page.on("request", (request) => {
    if (!request.url().startsWith(base + "/")) external.push(request.url());
  });
  page.on("websocket", (socket) => sockets.push(socket.url()));
  await page.reload();
  await expect(page.locator("heating-ai-panel .app")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Дім", exact: true }),
  ).toBeAttached();
  expect(external).toEqual([]);
  expect(sockets).toHaveLength(1);
  expect(new URL(sockets[0]!).pathname).toBe("/api/websocket");
  await expect(page.locator("heating-ai-panel .simulation-lab")).toHaveCount(0);
});

test("native 200 percent text keeps main tabs and settings accessible", async ({
  page,
}, info) => {
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "200%";
  });
  const panel = page.locator("heating-ai-panel");
  for (const name of ["Історія", "Налаштування", "Дім"]) {
    await panel.getByRole("button", { name, exact: true }).click();
    await expect(
      panel.getByRole("heading", { name, exact: true }),
    ).toBeAttached();
    expect(await panel.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
      true,
    );
  }
  await page.screenshot({
    path: info.outputPath("native-text-200.png"),
    fullPage: true,
  });
});
