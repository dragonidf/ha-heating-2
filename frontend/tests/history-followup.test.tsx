import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "fake-indexeddb/auto";
import { History } from "../src/History";
import { Chart } from "../src/Chart";
import { readHistory } from "../src/history";
import { kyivRange } from "../src/domain";
import { NOW, snapshot } from "../src/fixtures";
import { DemoAPI } from "../src/mock";
import { BrowserStore } from "../src/storage";
import type { HistoryCursor, HistoryPage, Point, Window } from "../src/types";

afterEach(cleanup);
const api = () =>
  new DemoAPI(new BrowserStore("synthetic-followup-" + crypto.randomUUID()), 0);
function reader(points: readonly Point[]) {
  return (
    scope: Window,
    cursor: HistoryCursor | null,
    limit: number,
  ): HistoryPage => {
    const selected = points.filter(
      (p) => p.at >= scope.start && p.at < scope.end,
    );
    const offset = cursor?.offset ?? 0,
      rows = selected.slice(offset, offset + limit);
    return {
      rows,
      watermark: points.length,
      cursor:
        offset + rows.length < selected.length
          ? {
              offset: offset + rows.length,
              scope: `${scope.start}:${scope.end}`,
              watermark: points.length,
            }
          : null,
    };
  };
}
it.each(["read", "tariff"])(
  "healthy temperature and original survive energy %s failure",
  (fault) => {
    const a = api();
    vi.spyOn(a, "energyHistory").mockImplementation(() => {
      if (fault === "read") throw Error("synthetic ledger unavailable");
      return [
        {
          start: NOW - 3600,
          end: NOW,
          kwh: 1,
          price: null,
          category: "confirmed",
          tariffs: [
            { start: NOW - 3600, end: NOW, price: 4 },
            { start: NOW - 1800, end: NOW, price: 6 },
          ],
        },
      ];
    });
    const { container } = render(
      <History api={a} state={snapshot()} onModel={() => {}} />,
    );
    expect(
      screen.getByRole("img", { name: /Історія температури/ }),
    ).toBeTruthy();
    expect(
      container.querySelectorAll('path[data-series="actual"]').length,
    ).toBeGreaterThan(0);
    expect(
      container.querySelectorAll('path[data-series="original"]').length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.change(screen.getByLabelText("Показник"), {
      target: { value: "energy" },
    });
    expect(screen.getByRole("alert").textContent).toMatch(/енергі|тариф/i);
    expect(container.querySelector(".energy-grid")).toBeNull();
    fireEvent.change(screen.getByLabelText("Показник"), {
      target: { value: "temperature" },
    });
    expect(
      screen.getByRole("img", { name: /Історія температури/ }),
    ).toBeTruthy();
  },
);
it.each(["energy", "cost"])(
  "healthy %s survives a failed temperature cursor",
  (metric) => {
    const a = api();
    vi.spyOn(a, "history").mockImplementation(() => {
      throw Error("synthetic cursor unavailable");
    });
    vi.spyOn(a, "energyHistory").mockReturnValue([
      { start: NOW - 3600, end: NOW, kwh: 1, category: "confirmed", price: 4 },
    ]);
    const { container } = render(
      <History api={a} state={snapshot()} onModel={() => {}} />,
    );
    expect(screen.getByRole("alert").textContent).toContain("Історію");
    fireEvent.change(screen.getByLabelText("Показник"), {
      target: { value: metric },
    });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(container.querySelector(".energy-grid strong")?.textContent).toBe(
      metric === "energy" ? "1,0кВт·год" : "4,0грн",
    );
    expect(
      screen.getByRole("img", {
        name: metric === "energy" ? /Історія енергії/ : /Історія вартості/,
      }),
    ).toBeTruthy();
  },
);
it("quarantines future provider observations while preserving legitimate past data", () => {
  const points = Object.freeze([
    { at: 0, value: 20 },
    { at: 150, value: 30 },
  ]);
  const result = readHistory(reader(points), { start: 0, end: 200 }, 100);
  expect(result.rows.filter((p) => p.value !== null)).toEqual([
    { at: 0, value: 20 },
  ]);
  expect(result.unknownS).toBe(100);
  expect(points[1]?.value).toBe(30);
});
it("a future actual cannot affect the curve, axis, table or forecast cursor fact", () => {
  const { container } = render(
    <Chart
      actual={[
        { at: 0, value: 20 },
        { at: 150, value: 99, quality: "valid" },
      ]}
      forecast={[{ at: 150, value: 22 }]}
      scope={{ start: 0, end: 200 }}
      now={100}
      label="Майбутній вимір"
    />,
  );
  const coordinates = [
    ...container.querySelectorAll('path[data-series="actual"]'),
  ].flatMap((p) =>
    [...(p.getAttribute("d") ?? "").matchAll(/[ML]([\d.]+),/g)].map((m) =>
      Number(m[1]),
    ),
  );
  expect(Math.max(...coordinates)).toBeLessThanOrEqual(448);
  fireEvent.change(screen.getByLabelText("Час: Майбутній вимір"), {
    target: { value: "1" },
  });
  expect(screen.getByText(/Факт — °C/)).toBeTruthy();
  fireEvent.click(screen.getByText("Таблиця значень · без кольору"));
  expect(screen.queryByText("99,0")).toBeNull();
  expect(screen.getByRole("img").textContent).not.toMatch(/99/);
});
it.each(["", null])(
  "invalid quality %j cannot become a confirmed actual",
  (quality) => {
    const p = { at: 0, value: 77, quality } as unknown as Point;
    const result = readHistory(reader([p]), { start: 0, end: 1 }, 0);
    expect(result.rows[0]?.value).toBeNull();
    const { container } = render(
      <Chart
        actual={[p]}
        scope={{ start: 0, end: 1 }}
        now={0}
        label="Некваліфікований вимір"
      />,
    );
    expect(container.querySelector('path[data-series="actual"]')).toBeNull();
  },
);

it.each([
  "estimated",
  "stale",
  "missing",
  "conflicting",
  "unrecognised",
  false,
  0,
])(
  "explicit unqualified quality %j cannot enter the measured curve or coverage",
  (quality) => {
    const p = {
      at: 10,
      value: 77,
      quality,
      coverage: { source: "synthetic", from: 0 },
    } as unknown as Point;
    const result = readHistory(
      reader([{ at: 0, value: 20 }, p]),
      { start: 0, end: 20 },
      20,
    );
    expect(
      result.rows.filter((p) => p.value !== null).map((p) => p.value),
    ).toEqual([20]);
    expect(result.unknownS).toBe(20);
    const { container } = render(
      <Chart
        actual={[p]}
        forecast={[{ at: 10, value: 21 }]}
        scope={{ start: 0, end: 20 }}
        now={20}
        label="Якість джерела"
      />,
    );
    expect(container.querySelector('path[data-series="actual"]')).toBeNull();
    fireEvent.pointerDown(screen.getByRole("img"), { clientX: 400 });
    expect(screen.getByText(/Факт — °C/)).toBeTruthy();
  },
);
it("exact now and known zero survive, one millisecond ahead is quarantined with no skew allowance", () => {
  const points: Point[] = [
    { at: 99, value: 20, quality: "valid" },
    {
      at: 100,
      value: 0,
      quality: "valid",
      coverage: { source: "synthetic", from: 99 },
    },
    { at: 100.001, value: 99, quality: "valid" },
  ];
  const result = readHistory(reader(points), { start: 0, end: 200 }, 100);
  expect(result.rows.some((p) => p.at === 100 && p.value === 0)).toBe(true);
  expect(result.rows.every((p) => p.at <= 100)).toBe(true);
  expect(result.quarantinedCount).toBe(1);
  expect(result.rawCount).toBe(3);
});
it("future quarantine consumes raw cursors without changing archives or admitting future gap annotations", () => {
  const points = Array.from({ length: 300 }, (_, at) => ({ at, value: at }));
  const before = JSON.stringify(points);
  const result = readHistory(reader(points), { start: 0, end: 300 }, 130);
  expect(result.rawCount).toBe(300);
  expect(result.quarantinedCount).toBe(169);
  expect(result.rows.every((p) => p.at <= 130)).toBe(true);
  expect(result.rows.filter((p) => p.value !== null).at(-1)?.at).toBe(130);
  expect(JSON.stringify(points)).toBe(before);
  const future = readHistory(reader(points), { start: 200, end: 300 }, 130);
  expect(future).toMatchObject({
    rows: [],
    rawCount: 100,
    quarantinedCount: 100,
    unknownS: 0,
  });
});
it("quarantine does not exempt future rows from ordering, capacity or cursor checks", () => {
  expect(() =>
    readHistory(
      () => ({
        rows: [
          { at: 150, value: 30 },
          { at: 149, value: 20 },
        ],
        watermark: 2,
        cursor: null,
      }),
      { start: 0, end: 200 },
      100,
    ),
  ).toThrow();
  expect(() =>
    readHistory(
      () => ({
        rows: [{ at: 150, value: 30 }],
        watermark: 2,
        cursor: { offset: 0, scope: "0:200", watermark: 2 },
      }),
      { start: 0, end: 200 },
      100,
    ),
  ).toThrow();
});
it("domain failures clear independently on source recovery, with empty and offline behavior intact", () => {
  const a = api();
  const { rerender } = render(
    <History api={a} state={snapshot()} onModel={() => {}} />,
  );
  for (const scenario of ["energy-error", "temperature-error"] as const) {
    a.setScenario(scenario);
    rerender(<History api={a} state={a.feed.value} onModel={() => {}} />);
    fireEvent.change(screen.getByLabelText("Показник"), {
      target: { value: scenario === "energy-error" ? "energy" : "temperature" },
    });
    expect(screen.getByRole("alert")).toBeTruthy();
    a.setScenario("normal");
    rerender(<History api={a} state={a.feed.value} onModel={() => {}} />);
    expect(screen.queryByRole("alert")).toBeNull();
  }
  a.setScenario("empty");
  rerender(<History api={a} state={a.feed.value} onModel={() => {}} />);
  expect(
    screen.getByRole("heading", {
      name: "За ці дати немає збережених вимірів",
    }),
  ).toBeTruthy();
  a.setScenario("offline");
  rerender(<History api={a} state={a.feed.value} onModel={() => {}} />);
  expect(screen.getByText(/Кешована синтетична історія/)).toBeTruthy();
});
it("future and unqualified synthetic rows remain excluded after reconnect and a date change", () => {
  const a = api();
  a.setScenario("future-history");
  const { container, rerender } = render(
    <History api={a} state={a.feed.value} onModel={() => {}} />,
  );
  expect(screen.getByText(/Відхилено майбутніх вимірів: 2/)).toBeTruthy();
  a.reconnect();
  a.setScenario("future-history");
  rerender(<History api={a} state={a.feed.value} onModel={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "24 год" }));
  expect(screen.getByText(/Відхилено майбутніх вимірів: 2/)).toBeTruthy();
  const nowLine = Number(
    container.querySelector(".now-line")?.getAttribute("x1"),
  );
  const x = [
    ...container.querySelectorAll('path[data-series="actual"]'),
  ].flatMap((p) =>
    [...(p.getAttribute("d") ?? "").matchAll(/[ML]([\d.]+),/g)].map((m) =>
      Number(m[1]),
    ),
  );
  expect(Math.max(...x)).toBeLessThanOrEqual(nowLine + 0.01);
});

it.each([
  ["2026-03-29", 23, 10800],
  ["2026-10-25", 25, 14400],
  ["2026-11-04", 24, 0],
] as const)(
  "UTC cutoff survives Kyiv %s (%sh day) and exact local midnight",
  (date, hours, offset) => {
    const scope = kyivRange(date, date),
      now = scope.start + offset;
    expect(scope.end - scope.start).toBe(hours * 3600);
    const points: Point[] = [
      { at: scope.start, value: 20 },
      ...(offset ? [{ at: now, value: 0, quality: "valid" as const }] : []),
      { at: now + 0.001, value: 99, quality: "valid" },
      { at: scope.end - 0.001, value: 88, quality: "valid" },
    ];
    const result = readHistory(reader(points), scope, now);
    expect(result.quarantinedCount).toBe(2);
    expect(result.rows.every((p) => p.at <= now)).toBe(true);
    expect(result.unknownS).toBe(offset);
  },
);
it.each(["temperature", "energy"])(
  "reconnect refreshes an unchanged-scope %s archive after recovery",
  (metric) => {
    const a = api();
    let broken = true;
    const history = a.history.bind(a),
      ledger = a.energyHistory.bind(a);
    vi.spyOn(a, "history").mockImplementation((...args) => {
      if (broken && metric === "temperature")
        throw Error("synthetic read fault");
      return history(...args);
    });
    vi.spyOn(a, "energyHistory").mockImplementation(() => {
      if (broken && metric === "energy") throw Error("synthetic read fault");
      return ledger();
    });
    const { rerender } = render(
      <History api={a} state={a.feed.value} onModel={() => {}} />,
    );
    fireEvent.change(screen.getByLabelText("Показник"), {
      target: { value: metric },
    });
    expect(screen.getByRole("alert")).toBeTruthy();
    broken = false;
    a.reconnect();
    rerender(<History api={a} state={a.feed.value} onModel={() => {}} />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.getByRole("img", {
        name:
          metric === "temperature" ? /Історія температури/ : /Історія енергії/,
      }),
    ).toBeTruthy();
  },
);
