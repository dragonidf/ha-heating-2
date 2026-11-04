import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Збільшити ціль на0,5 °C у симуляції" }),
  ).toBeEnabled();
});
test("home screenshot and first viewport hierarchy", async ({ page }, info) => {
  await expect(page).toHaveScreenshot("home.png", { fullPage: true });
  const chart = await page
    .getByRole("heading", { name: "Наступні 24 години" })
    .boundingBox();
  expect(chart?.y).toBeLessThan(
    info.project.name.includes("mobile") ? 844 : 700,
  );
  if (info.project.name.includes("mobile")) {
    const main = await page.locator("main").boundingBox();
    expect(main?.height).toBeLessThanOrEqual(1300);
  }
  await expect(page.getByText("Фізичний стан котла — невідомий")).toBeVisible();
});
test("keyboard navigation, chart alternative and no external requests", async ({
  page,
}) => {
  const external: string[] = [];
  page.on("request", (r) => {
    if (!r.url().startsWith("http://127.0.0.1:4173")) external.push(r.url());
  });
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "До основного вмісту" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Історія", exact: true }),
  ).toBeVisible();
  await expect(page.locator("main")).toBeFocused();
  await page.getByText("Таблиця значень · без кольору").click();
  await expect(page.getByRole("table").first()).toBeVisible();
  expect(external).toEqual([]);
});
test("CAS settings save, persistence, draft cancel and undo", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  const day = page.getByRole("spinbutton", { name: "Температура вдень" });
  await day.fill("22");
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    page.getByText("Збережено лише в симуляції", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  await expect(day).toHaveValue("22");
  await day.fill("23");
  await page.getByRole("button", { name: "Скасувати", exact: true }).click();
  await expect(day).toHaveValue("22");
  await page.getByRole("button", { name: "Повернути чернетку" }).click();
  await expect(day).toHaveValue("23");
});
test("offline disables writes and reconnect needs full snapshot", async ({
  page,
  context,
}) => {
  await context.setOffline(true);
  await expect(
    page.getByRole("button", { name: "Збільшити ціль на0,5 °C у симуляції" }),
  ).toBeDisabled();
  await expect(page.getByText("Немає зв’язку · останні дані")).toBeVisible();
  await context.setOffline(false);
  await expect(
    page.getByRole("button", { name: "Збільшити ціль на0,5 °C у симуляції" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Відновити симуляцію" }).click();
  await expect(
    page.getByRole("button", { name: "Збільшити ціль на0,5 °C у симуляції" }),
  ).toBeEnabled();
});
test("missing original stays missing while actual history and energy are usable", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page
    .getByLabel("Сценарій", { exact: true })
    .selectOption("missing-original");
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await expect(
    page.getByText("Немає завчасного прогнозу на цей період.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByLabel("Показник", { exact: true }).selectOption("energy");
  await expect(
    page.getByText("Невідоме покриття", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Показник", { exact: true }).selectOption("cost");
  await expect(
    page.getByRole("img", { name: /Історія вартості/ }),
  ).toBeVisible();
});
test("accessibility AA, light theme and 200% text do not overflow", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Увімкнути світлу тему" }).click();
  for (const label of ["Дім", "Історія", "Налаштування"]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    expect(
      (
        await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze()
      ).violations,
    ).toEqual([]);
    await page.addStyleTag({ content: ":root{font-size:30px}" });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});
test("two browser clients conflict without losing draft and explicitly rebase", async ({
  page,
  context,
}) => {
  const other = await context.newPage();
  await other.goto("/");
  await expect(
    other.getByRole("button", { name: /Збільшити ціль/ }),
  ).toBeEnabled();
  for (const p of [page, other])
    await p.getByRole("button", { name: "Налаштування", exact: true }).click();
  await page.getByRole("spinbutton", { name: /Температура вдень/ }).fill("22");
  await other.getByRole("spinbutton", { name: /Температура вдень/ }).fill("23");
  await other
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    other.getByText("Збережено лише в симуляції", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Налаштування змінилися в іншому вікні",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("spinbutton", { name: /Температура вдень/ }),
  ).toHaveValue("22");
  await page
    .getByRole("button", {
      name: "Взяти нову версію за основу, зберегти чернетку",
    })
    .click();
  await expect(
    page.getByRole("button", { name: "Зберегти симуляцію", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Залишити моє: Денна ціль", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    page.getByText("Збережено лише в симуляції", { exact: true }),
  ).toBeVisible();
  await other.close();
});
test("storage readback failure never shows saved and retry retains draft", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page
    .getByLabel("Відмова запису", { exact: true })
    .selectOption("readback");
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  const day = page.getByRole("spinbutton", { name: /Температура вдень/ });
  await day.fill("22");
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    page.getByText(/Запис або перевірку не підтверджено/),
  ).toBeVisible();
  await expect(day).toHaveValue("22");
  await expect(
    page.getByText("Збережено лише в симуляції", { exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Відмова запису", { exact: true }).selectOption("none");
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Налаштування змінилися в іншому вікні",
    }),
  ).toBeVisible();
});
test("danger, manual, stale, revoked, empty and false ACK remain honest", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  for (const scenario of [
    "safety",
    "manual",
    "stale",
    "missing",
    "revoked",
    "false-ack",
    "grid-off",
    "recovering",
    "anomaly",
    "fire",
    "overspend",
    "long-copy",
  ]) {
    await page.getByLabel("Сценарій", { exact: true }).selectOption(scenario);
    await expect(page.getByRole("alert")).toHaveCount(1);
    await expect(
      page.getByText("Фізичний стан котла — невідомий", { exact: true }),
    ).toBeVisible();
    if (
      ["safety", "stale", "missing", "revoked", "recovering"].includes(scenario)
    )
      await expect(
        page.getByRole("button", { name: /Збільшити ціль/ }),
      ).toBeDisabled();
  }
  await page.getByLabel("Сценарій", { exact: true }).selectOption("empty");
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await expect(
    page.getByText("За ці дати немає збережених вимірів", { exact: true }),
  ).toBeVisible();
});
test("chart keyboard/touch, midnight DST and custom history range", async ({
  page,
}) => {
  const slider = page.getByRole("slider", { name: "Час: Прогноз температури" });
  await slider.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator(".chart-readout").first()).toContainText("Факт");
  await page
    .getByRole("img", { name: /Прогноз температури/ })
    .click({ position: { x: 100, y: 80 } });
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await page.getByLabel("Від", { exact: true }).fill("2026-03-29");
  await page.getByLabel("До", { exact: true }).fill("2026-03-29");
  await expect(page.getByText(/Календар Europe\/Kyiv ·23год/)).toBeVisible();
  await page.getByLabel("Від", { exact: true }).fill("2026-10-25");
  await page.getByLabel("До", { exact: true }).fill("2026-10-25");
  await expect(page.getByText(/Календар Europe\/Kyiv ·25год/)).toBeVisible();
});
test("fan sheet keyboard focus, one-shot and nested model actions", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Швидкість і деталі" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Швидкість і деталі" }),
  ).toBeFocused();
  await page
    .getByText("Одноразовий запит після відновлення живлення · симуляція", {
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Запланувати один раз у симуляції" })
    .click();
  await expect(
    page.getByText("очікує живлення", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Скасувати запит", exact: true })
    .click();
  await expect(page.getByText("скасований", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await page.getByRole("button", { name: "Точність прогнозу" }).click();
  await expect(
    page.getByRole("heading", { name: "Champion v3" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Перевірити синтетичного кандидата" })
    .click();
  await page
    .getByRole("button", { name: "Прийняти кандидата в симуляції" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Champion v4" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Відкотити модель у симуляції" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Champion v3" }),
  ).toBeVisible();
});
test("dark theme accessibility, 320/700/1100 layouts, long copy and touch targets", async ({
  page,
}) => {
  for (const width of [320, 700, 1100]) {
    await page.setViewportSize({ width, height: 900 });
    for (const tab of ["Дім", "Історія", "Налаштування"]) {
      await page.getByRole("button", { name: tab, exact: true }).click();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
  await page.getByRole("button", { name: "Дім", exact: true }).click();
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page.getByLabel("Сценарій", { exact: true }).selectOption("long-copy");
  await page.setViewportSize({ width: 320, height: 900 });
  await page.addStyleTag({ content: ":root{font-size:30px}" });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const undersized = await page
    .locator(
      "button:visible,input:not([type=checkbox]):visible,select:visible,summary:visible",
    )
    .evaluateAll((es) =>
      es
        .filter((e) => e.getBoundingClientRect().height < 44 - 0.5)
        .map((e) => e.textContent?.slice(0, 30)),
    );
  expect(undersized).toEqual([]);
});
test("disconnect during save keeps draft without a stale success", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  await page.getByRole("spinbutton", { name: /Температура вдень/ }).fill("22");
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(
    page.getByRole("spinbutton", { name: /Температура вдень/ }),
  ).toBeDisabled();
  await expect(
    page.getByText("Збережено лише в симуляції", { exact: true }),
  ).toHaveCount(0);
});
test("known zero, synthetic heating and STOP never claim physical success", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page.getByLabel("Сценарій", { exact: true }).selectOption("zero");
  await expect(page.locator(".room-value")).toHaveText("0,0°C");
  await expect(
    page.getByText("Потрібне тепло. Запланований нагрів умовний.", {
      exact: true,
    }),
  ).toBeVisible();
  for (const value of ["heating", "device-stop"]) {
    await page.getByLabel("Сценарій", { exact: true }).selectOption(value);
    await expect(
      page.getByText("Фізичний стан котла — невідомий", { exact: true }),
    ).toBeVisible();
  }
});

test("disjoint two-window settings edits survive merge, reload and full-field comparison", async ({
  page,
  context,
}) => {
  const other = await context.newPage();
  await other.goto("/");
  await expect(
    other.getByRole("button", { name: /Збільшити ціль/ }),
  ).toBeEnabled();
  for (const p of [page, other])
    await p.getByRole("button", { name: "Налаштування", exact: true }).click();
  await page.getByRole("spinbutton", { name: /Температура вдень/ }).fill("22");
  await other.getByRole("spinbutton", { name: /М’який бюджет/ }).fill("800");
  await page.getByRole("button", { name: "Дім", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Збільшити ціль/ }),
  ).toBeDisabled();
  await expect(
    page.getByText("Спочатку збережіть або скасуйте чернетку в налаштуваннях", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  await expect(
    page.getByRole("spinbutton", { name: /Температура вдень/ }),
  ).toHaveValue("22");
  await other
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    other.getByText("Збережено лише в симуляції", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Налаштування змінилися в іншому вікні",
    }),
  ).toBeVisible();
  const comparison = page.getByRole("table", {
    name: "Усі параметри: основа, ваша чернетка та нова версія",
  });
  await expect(comparison.locator("tbody tr")).toHaveCount(12);
  await page
    .getByRole("button", {
      name: "Взяти нову версію за основу, зберегти чернетку",
    })
    .click();
  await expect(
    page.getByRole("spinbutton", { name: /М’який бюджет/ }),
  ).toHaveValue("800");
  await page
    .getByRole("button", { name: "Зберегти симуляцію", exact: true })
    .click();
  await expect(
    page.getByText("Збережено лише в симуляції", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Налаштування", exact: true }).click();
  await expect(
    page.getByRole("spinbutton", { name: /Температура вдень/ }),
  ).toHaveValue("22");
  await expect(
    page.getByRole("spinbutton", { name: /М’який бюджет/ }),
  ).toHaveValue("800");
  await other.close();
});

test("dense full-range history preserves newest facts, gaps and scoped cached navigation", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page
    .getByLabel("Сценарій", { exact: true })
    .selectOption("dense-history");
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await page.getByRole("button", { name: "30 днів", exact: true }).click();
  const overview = page.getByText(/Увесь період:/);
  await expect(overview).toContainText(/8\d{3} вихідних вимірів/);
  const paths = page.locator('path[data-series="actual"]');
  expect(await paths.count()).toBeGreaterThan(1);
  const maximumX = await paths.evaluateAll((elements) =>
    Math.max(
      ...elements.flatMap((el) =>
        [...(el.getAttribute("d") ?? "").matchAll(/[ML]([\d.]+),/g)].map((m) =>
          Number(m[1]),
        ),
      ),
    ),
  );
  expect(maximumX).toBeGreaterThan(820);
  await page
    .getByText("Таблиця значень · без кольору", { exact: true })
    .click();
  await expect(page.getByRole("table").first()).toBeVisible();
  await page.getByRole("button", { name: "24 год", exact: true }).click();
  await expect(overview).toContainText("25 вихідних вимірів");
  await page.getByLabel("Сценарій", { exact: true }).selectOption("empty");
  await expect(
    page.getByRole("heading", { name: "За ці дати немає збережених вимірів" }),
  ).toBeVisible();
});

test("counter crossing Kyiv midnight is estimated once with honest changing-tariff cost", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page
    .getByLabel("Сценарій", { exact: true })
    .selectOption("dense-history");
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  for (const [date, cost] of [
    ["2026-11-03", "2,0грн"],
    ["2026-11-04", "3,0грн"],
  ]) {
    await page.getByLabel("Від", { exact: true }).fill(date!);
    await page.getByLabel("До", { exact: true }).fill(date!);
    await page.getByLabel("Показник", { exact: true }).selectOption("energy");
    await expect(page.locator(".energy-grid strong").nth(0)).toHaveText(
      "0,0кВт·год",
    );
    await expect(page.locator(".energy-grid strong").nth(1)).toHaveText(
      "0,5кВт·год",
    );
    await page.getByLabel("Показник", { exact: true }).selectOption("cost");
    await expect(page.locator(".energy-grid strong").nth(0)).toHaveText(
      "0,0грн",
    );
    await expect(page.locator(".energy-grid strong").nth(1)).toHaveText(cost!);
    await expect(page.getByText(/Вартість часткова/)).toBeVisible();
  }
  await page.getByRole("button", { name: "7 днів", exact: true }).click();
  await page.getByLabel("Показник", { exact: true }).selectOption("energy");
  await expect(page.locator(".energy-grid strong").nth(0)).toHaveText(
    "1,0кВт·год",
  );
  await page.getByLabel("Показник", { exact: true }).selectOption("cost");
  await expect(page.locator(".energy-grid strong").nth(0)).toHaveText("0,0грн");
  await expect(page.locator(".energy-grid strong").nth(1)).toHaveText("5,0грн");
});

test("temperature and original remain available through an independent energy archive failure", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page
    .getByLabel("Сценарій", { exact: true })
    .selectOption("energy-error");
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await expect(
    page.getByRole("img", { name: /Історія температури/ }),
  ).toBeVisible();
  expect(
    await page.locator('path[data-series="original"]').count(),
  ).toBeGreaterThan(0);
  expect(
    await page.locator('path[data-series="actual"]').count(),
  ).toBeGreaterThan(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  for (const metric of ["energy", "cost"]) {
    await page.getByLabel("Показник", { exact: true }).selectOption(metric);
    await expect(page.getByRole("alert")).toContainText(
      "Підсумок і покриття невідомі",
    );
    await expect(page.locator(".energy-grid")).toHaveCount(0);
  }
  await page
    .getByLabel("Показник", { exact: true })
    .selectOption("temperature");
  await page.getByRole("button", { name: "24 год", exact: true }).click();
  await expect(
    page.getByRole("img", { name: /Історія температури/ }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByLabel("Сценарій", { exact: true }).selectOption("normal");
  await page.getByLabel("Показник", { exact: true }).selectOption("energy");
  await expect(
    page.getByRole("img", { name: /Історія енергії/ }),
  ).toBeVisible();
});

test("energy and cost remain available through an independent temperature cursor failure", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page
    .getByLabel("Сценарій", { exact: true })
    .selectOption("temperature-error");
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Історію не вдалося прочитати",
  );
  for (const metric of ["energy", "cost"]) {
    await page.getByLabel("Показник", { exact: true }).selectOption(metric);
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(
      page.getByRole("img", {
        name: metric === "energy" ? /Історія енергії/ : /Історія вартості/,
      }),
    ).toBeVisible();
    const known = await page
      .locator(".energy-grid strong")
      .first()
      .textContent();
    expect(known).not.toMatch(/^0,0/);
  }
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  await page.getByLabel("Сценарій", { exact: true }).selectOption("normal");
  await page
    .getByLabel("Показник", { exact: true })
    .selectOption("temperature");
  await expect(
    page.getByRole("img", { name: /Історія температури/ }),
  ).toBeVisible();
});

test("future and unqualified observations never cross the now divider as actuals after reconnect", async ({
  page,
}) => {
  await page
    .getByText("Сценарії демо · синтетичні дані", { exact: true })
    .click();
  await page
    .getByLabel("Сценарій", { exact: true })
    .selectOption("future-history");
  await page.getByRole("button", { name: "Історія", exact: true }).click();
  const check = async () => {
    await expect(
      page.getByText(/Відхилено майбутніх вимірів: 2/),
    ).toBeVisible();
    const nowX = Number(await page.locator(".now-line").getAttribute("x1"));
    const coordinates = await page
      .locator('path[data-series="actual"]')
      .evaluateAll((elements) =>
        elements.flatMap((el) =>
          [...(el.getAttribute("d") ?? "").matchAll(/[ML]([\d.]+),/g)].map(
            (m) => Number(m[1]),
          ),
        ),
      );
    expect(coordinates.length).toBeGreaterThan(0);
    expect(Math.max(...coordinates)).toBeLessThanOrEqual(nowX + 0.01);
    await page
      .getByRole("slider", { name: "Час: Історія температури" })
      .focus();
    await page.keyboard.press("End");
    await expect(page.locator(".chart-readout")).toContainText("Факт — °C");
  };
  await page.getByRole("button", { name: "24 год", exact: true }).click();
  await page
    .getByRole("button", { name: "Поточний прогноз", exact: true })
    .click();
  await check();
  await page
    .getByText("Таблиця значень · без кольору", { exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "99,0", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("cell", { name: "88,0", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("cell", { name: "77,0", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("cell", { name: "0,0", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Новий повний стан", exact: true })
    .click();
  await page
    .getByLabel("Сценарій", { exact: true })
    .selectOption("future-history");
  await check();
});
