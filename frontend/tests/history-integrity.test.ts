import { expect, it } from "vitest";
import {
  connected,
  qualifyCadence,
  readHistory,
  RAW_LIMIT,
} from "../src/history";
import { segments, kyivRange, decimate } from "../src/domain";
import { denseActual, NOW, defaults } from "../src/fixtures";
import { DemoAPI } from "../src/mock";
import type { HistoryPage, Point, Window } from "../src/types";
function reader(points: readonly Point[]) {
  return (
    scope: Window,
    cursor: { offset: number } | null,
    limit: number,
  ): HistoryPage => {
    const rows = points.filter((p) => p.at >= scope.start && p.at < scope.end);
    const offset = cursor?.offset ?? 0;
    return {
      rows: rows.slice(offset, offset + limit),
      watermark: points.length,
      cursor:
        offset + limit < rows.length
          ? {
              offset: offset + limit,
              scope: `${scope.start}:${scope.end}`,
              watermark: points.length,
            }
          : null,
    };
  };
}
it("streams a dense 30-day archive with both endpoints, extrema, nulls and bounded rendering", () => {
  const scope = kyivRange("2026-10-06", "2026-11-04");
  const result = readHistory(reader(denseActual), scope, NOW);
  const raw = denseActual.filter(
    (p) => p.at >= scope.start && p.at < scope.end,
  );
  expect(result.rawCount).toBeGreaterThan(8000);
  expect(result.rows.length).toBeLessThanOrEqual(4096);
  expect(result.rows[0]?.at).toBe(raw[0]?.at);
  expect(result.rows.at(-1)?.at).toBe(raw.at(-1)?.at);
  expect(result.rows.some((p) => p.value === 26)).toBe(true);
  expect(result.rows.some((p) => p.value === 16)).toBe(true);
  expect(result.rows.some((p) => p.value === null)).toBe(true);
  expect(result.unknownS).toBeGreaterThanOrEqual(26 * 300);
  const runs = segments(decimate(result.rows), true);
  expect(runs.length).toBeGreaterThanOrEqual(2);
  expect(
    runs.every(
      (run) =>
        !(
          run[0]!.at < denseActual[4200]!.at &&
          run.at(-1)!.at > denseActual[4224]!.at
        ),
    ),
  ).toBe(true);
  // A new scope has its own cursor and endpoints; the frozen source is untouched.
  const next = readHistory(
    reader(denseActual),
    kyivRange("2026-11-03", "2026-11-04"),
    NOW,
  );
  expect(next.rawCount).toBeLessThan(result.rawCount);
  expect(next.rows[0]!.at).toBeGreaterThan(result.rows[0]!.at);
  expect(Object.isFrozen(denseActual[0]?.coverage)).toBe(true);
});
it("source-qualified three-hour cadence connects legitimate sparse history", () => {
  const points = qualifyCadence(
    [
      { at: 0, value: 0 },
      { at: 10800, value: 2 },
    ],
    { source: "synthetic.sparse", cadenceS: 10800, qualified: true },
  );
  expect(segments(points, true)).toHaveLength(1);
  expect(
    readHistory(reader(points), { start: 0, end: 10801 }, 10800).unknownS,
  ).toBe(0);
});
it("silent source gaps split at cadence boundaries without invented actual readings", () => {
  const raw = [
    { at: 0, value: 20 },
    { at: 300, value: 21 },
    { at: 11100, value: 22 },
    { at: 11400, value: 23 },
  ];
  const points = qualifyCadence(raw, {
    source: "synthetic.five-min",
    cadenceS: 300,
    qualified: true,
  });
  const result = readHistory(reader(points), { start: 0, end: 11401 }, 11400);
  expect(result.unknownS).toBe(10800);
  expect(result.gapCount).toBe(1);
  expect(result.rows.filter((p) => p.value !== null).map((p) => p.at)).toEqual(
    raw.map((p) => p.at),
  );
  expect(result.rows.find((p) => p.gap)?.gap).toEqual({
    start: 300,
    end: 11100,
    seconds: 10800,
    count: 1,
  });
  expect(segments(result.rows, true)).toHaveLength(2);
});
it.each(["estimated", "stale", "conflicting", "missing"] as const)(
  "%s data never qualifies as continuous measured history",
  (quality) => {
    const points = qualifyCadence(
      [
        { at: 0, value: 20 },
        { at: 300, value: 21, quality },
        { at: 600, value: 22 },
      ],
      { source: "synthetic.quality", cadenceS: 300, qualified: true },
    );
    expect(segments(points, true)).toHaveLength(3);
    expect(
      readHistory(reader(points), { start: 0, end: 601 }, 600).unknownS,
    ).toBe(600);
  },
);
it("absent or unqualified cadence and source changes fail closed", () => {
  const raw = [
    { at: 0, value: 0 },
    { at: 1, value: 1 },
  ];
  for (const policy of [
    { source: "", cadenceS: 1, qualified: true },
    { source: "a", cadenceS: NaN, qualified: true },
    { source: "a", cadenceS: 1, qualified: false },
  ])
    expect(qualifyCadence(raw, policy).every((p) => !p.coverage)).toBe(true);
  expect(
    connected(
      { ...raw[0]!, coverage: { source: "a", from: 0 } },
      { ...raw[1]!, coverage: { source: "b", from: 0 } },
    ),
  ).toBe(false);
});
it("empty, future and cached histories do not manufacture zero measurements", () => {
  expect(readHistory(reader([]), { start: 0, end: 10 }, 10)).toMatchObject({
    rawCount: 0,
    rows: [],
    unknownS: 10,
  });
  expect(readHistory(reader([]), { start: 10, end: 20 }, 5).unknownS).toBe(0);
  const api = new DemoAPI({
    read: async () => ({ revision: 1, values: defaults, lastRequest: null }),
    commit: async () => {
      throw Error("unused");
    },
  });
  api.setScenario("dense-history");
  const before = readHistory(
    api.history.bind(api),
    { start: NOW - 86400, end: NOW },
    NOW,
  );
  api.feed.value.connected = false;
  expect(
    readHistory(api.history.bind(api), { start: NOW - 86400, end: NOW }, NOW),
  ).toEqual(before);
});
it.each([
  "bad scope",
  "stuck",
  "watermark",
  "oversize",
  "unsorted",
  "outside",
  "nonfinite",
  "large payload",
])("rejects %s pages instead of silently truncating", (fault) => {
  let calls = 0;
  const read = (): HistoryPage => {
    calls++;
    const rows: Point[] =
      fault === "oversize"
        ? Array.from({ length: 129 }, (_, at) => ({ at, value: 1 }))
        : fault === "unsorted"
          ? [
              { at: 2, value: 1 },
              { at: 1, value: 1 },
            ]
          : [
              {
                at: fault === "outside" ? -1 : calls - 1,
                value: fault === "nonfinite" ? NaN : 1,
                ...(fault === "large payload"
                  ? { coverage: { source: "x".repeat(65536), from: 0 } }
                  : {}),
              },
            ];
    return {
      rows,
      watermark: fault === "watermark" ? calls : 2,
      cursor: {
        offset: fault === "stuck" ? 0 : calls,
        watermark: fault === "watermark" ? calls : 2,
        scope: fault === "bad scope" ? "other" : "0:1000",
      },
    };
  };
  expect(() => readHistory(read, { start: 0, end: 1000 }, 999)).toThrow();
});
it("rejects empty advancing pages, invalid scopes and source overflow explicitly", () => {
  expect(() =>
    readHistory(
      () => ({
        rows: [],
        watermark: 1,
        cursor: { offset: 0, scope: "0:1", watermark: 1 },
      }),
      { start: 0, end: 1 },
      1,
    ),
  ).toThrow();
  expect(() => readHistory(reader([]), { start: 1, end: 0 }, 0)).toThrow();
  const read = (_s: Window, cursor: { offset: number } | null): HistoryPage => {
    const offset = cursor?.offset ?? 0;
    return {
      rows: Array.from({ length: 128 }, (_, i) => ({
        at: offset + i,
        value: 1,
      })),
      watermark: RAW_LIMIT + 128,
      cursor: {
        offset: offset + 128,
        watermark: RAW_LIMIT + 128,
        scope: `0:${RAW_LIMIT + 128}`,
      },
    };
  };
  expect(() =>
    readHistory(read, { start: 0, end: RAW_LIMIT + 128 }, RAW_LIMIT),
  ).toThrow(/завеликий/);
});
it("enforces the page payload cap in UTF-8 bytes rather than character count", () => {
  const page: HistoryPage = {
    rows: [
      { at: 0, value: 1, coverage: { source: "і".repeat(40000), from: 0 } },
    ],
    cursor: null,
    watermark: 1,
  };
  expect(JSON.stringify(page).length).toBeLessThan(65536);
  expect(() => readHistory(() => page, { start: 0, end: 1 }, 1)).toThrow(
    /архів/,
  );
});
