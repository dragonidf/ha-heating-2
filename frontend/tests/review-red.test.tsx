import { afterEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import "fake-indexeddb/auto";

vi.mock("../src/fixtures", async (importOriginal) => {
  const fixtures = await importOriginal<typeof import("../src/fixtures")>();
  return {
    ...fixtures,
    intervals: [
      {
        // One synthetic counter difference spanning midnight in Europe/Kyiv.
        start: Date.parse("2026-11-03T21:50:00Z") / 1000,
        end: Date.parse("2026-11-03T22:10:00Z") / 1000,
        kwh: 1,
        category: "confirmed",
        price: 4,
        method: "counter_difference",
      },
    ],
  };
});

import { Chart } from "../src/Chart";
import { History } from "../src/History";
import { kyivRange } from "../src/domain";
import { defaults, snapshot } from "../src/fixtures";
import { DemoAPI } from "../src/mock";
import { BrowserStore } from "../src/storage";
import type { HistoryCursor, HistoryPage, Point, Window } from "../src/types";
import { useSettings } from "../src/useSettings";

afterEach(cleanup);

function storeName() {
  return "synthetic-review-" + crypto.randomUUID();
}

it("conflict rebase preserves a different client's disjoint settings edit", async () => {
  const name = storeName();
  const local = new DemoAPI(new BrowserStore(name), 0);
  const remote = new DemoAPI(new BrowserStore(name), 0);
  const { result } = renderHook(() => useSettings(local));
  await waitFor(() => expect(result.current.saved?.revision).toBe(1));

  // Both windows start at revision 1; only the remote window edits the fan.
  const base = await remote.settings();
  expect(base.revision).toBe(1);
  expect(
    (
      await remote.save(
        "synthetic.remote.fan",
        1,
        { ...base.values, fan: 70 },
        remote.session,
      )
    ).status,
  ).toBe("saved");
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await act(() => result.current.save());
  expect(result.current.conflict?.revision).toBe(2);

  act(() => result.current.rebase());
  await act(() => result.current.save());
  const persisted = await remote.settings();
  expect(persisted.revision).toBe(3);
  expect(persisted.values.day).toBe(22);
  expect(persisted.values.fan).toBe(70);
});

it("30-day history includes the newest observation beyond 8640 raw readings", () => {
  const range = kyivRange("2026-10-06", "2026-11-04");
  const dense: Point[] = [];
  for (let at = range.start; at < range.end; at += 300) {
    dense.push({ at, value: 21 + Math.sin((at - range.start) / 86400) });
  }
  expect(dense.length).toBeGreaterThan(8640);
  class DenseHistoryAPI extends DemoAPI {
    override history(
      scope: Window,
      cursor: HistoryCursor | null = null,
      limit = 128,
    ): HistoryPage {
      const selected = dense.filter(
        (p) => p.at >= scope.start && p.at < scope.end,
      );
      const offset = cursor?.offset ?? 0;
      const rows = selected.slice(offset, offset + limit);
      return {
        rows,
        watermark: dense.length,
        cursor:
          offset + rows.length < selected.length
            ? {
                offset: offset + rows.length,
                scope: `${scope.start}:${scope.end}`,
                watermark: dense.length,
              }
            : null,
      };
    }
  }
  const api = new DenseHistoryAPI(new BrowserStore(storeName()), 0);
  const { container } = render(
    <History
      api={api}
      state={{ ...snapshot(), now: range.end - 1 }}
      onModel={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "30 днів" }));

  const xCoordinates = [
    ...container.querySelectorAll('path[data-series="actual"]'),
  ]
    .flatMap((path) => [
      ...(path.getAttribute("d") ?? "").matchAll(/[ML]([\d.]+),/g),
    ])
    .map((match) => Number(match[1]));
  expect(xCoordinates.length).toBeGreaterThan(0);
  const newest = dense[dense.length - 1]!;
  const newestX =
    48 + ((newest.at - range.start) / (range.end - range.start)) * 800;
  // A bounded chart may aggregate, but must cover the selected range through its newest fact.
  expect(Math.max(...xCoordinates)).toBeGreaterThanOrEqual(newestX - 0.02);
});

it("actual timestamps three hours apart do not imply continuous measured coverage", () => {
  const { container } = render(
    <Chart
      actual={[
        { at: 0, value: 20 },
        { at: 3 * 3600, value: 21 },
      ]}
      scope={{ start: 0, end: 3 * 3600 + 1 }}
      now={3 * 3600}
      label="Синтетична кімната без доказів суцільного покриття"
    />,
  );
  const paths = [...container.querySelectorAll('path[data-series="actual"]')];
  expect(paths.length).toBeGreaterThan(0);
  // No explicit null is necessary: absent continuity evidence cannot fabricate a line.
  expect(paths.some((path) => /L/.test(path.getAttribute("d") ?? ""))).toBe(
    false,
  );
});

it.each([
  ["2026-11-03", "energy"],
  ["2026-11-04", "energy"],
  ["2026-11-03", "cost"],
  ["2026-11-04", "cost"],
])(
  "partial counter interval is not a whole measured daily total for %s %s",
  (date, metric) => {
    const { container } = render(
      <History
        api={new DemoAPI(new BrowserStore(storeName()), 0)}
        state={snapshot()}
        onModel={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Від"), { target: { value: date } });
    fireEvent.change(screen.getByLabelText("До"), { target: { value: date } });
    fireEvent.change(screen.getByLabelText("Показник"), {
      target: { value: metric },
    });
    const known = container.querySelector(".energy-grid strong");
    expect(known).not.toBeNull();
    // A counter difference has no evidence assigning either partial day's share.
    // An allocation may be disclosed as estimated; neither day may claim the whole fact.
    expect(known?.textContent).toBe(
      metric === "cost" ? "0,0грн" : "0,0кВт·год",
    );
  },
);
it("recovered estimates remain unknown in the actual chart and readout", () => {
  const { container } = render(
    <Chart
      actual={[
        { at: 0, value: 20 },
        { at: 300, value: 21, quality: "estimated" },
        { at: 600, value: 22 },
      ]}
      scope={{ start: 0, end: 601 }}
      now={600}
      label="Якість відновлених даних"
    />,
  );
  expect(container.querySelectorAll("circle.sample.actual")).toHaveLength(2);
  fireEvent.change(screen.getByLabelText("Час: Якість відновлених даних"), {
    target: { value: "1" },
  });
  expect(screen.getByText(/Факт — °C/)).toBeTruthy();
});
it.each(["estimated", "confirmed"] as const)(
  "known zero cost retains %s quality and is visible as zero rather than missing",
  (category) => {
    const api = new DemoAPI(new BrowserStore(storeName()), 0);
    vi.spyOn(api, "energyHistory").mockReturnValue([
      {
        start: snapshot().now - 1200,
        end: snapshot().now - 600,
        kwh: 0,
        category,
        price: 4,
        method: "counter_difference",
      },
    ]);
    const { container } = render(
      <History api={api} state={snapshot()} onModel={() => {}} />,
    );
    fireEvent.change(screen.getByLabelText("Показник"), {
      target: { value: "cost" },
    });
    expect(
      container.querySelectorAll(
        `path[data-series="${category === "estimated" ? "latest" : "actual"}"]`,
      ),
    ).toHaveLength(1);
  },
);
it("missing source interval exposes its boundaries in both accessible table and cursor readout", () => {
  const points: Point[] = [
    { at: 0, value: 20 },
    {
      at: 5400,
      value: null,
      gap: { start: 0, end: 10800, seconds: 10800, count: 1 },
    },
    { at: 10800, value: 21 },
  ];
  render(
    <Chart
      actual={points}
      scope={{ start: 0, end: 10801 }}
      now={10800}
      label="Межі прогалини"
    />,
  );
  fireEvent.click(screen.getByText("Таблиця значень · без кольору"));
  fireEvent.change(screen.getByLabelText("Час: Межі прогалини"), {
    target: { value: "1" },
  });
  expect(screen.getAllByText(/немає доказів покриття.*180 хв/)).toHaveLength(2);
});
