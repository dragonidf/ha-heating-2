import { expect, it } from "vitest";
import { scopedEnergy } from "../src/historyEnergy";
import { kyivRange } from "../src/domain";
import type { EnergyInterval } from "../src/types";
const base: EnergyInterval = {
  start: 0,
  end: 1200,
  kwh: 1,
  price: 4,
  category: "confirmed",
  method: "counter_difference",
};
it("adjacent partial counter periods allocate estimates once and preserve historical input", () => {
  const input = Object.freeze([Object.freeze(base)]),
    before = JSON.stringify(input);
  const left = scopedEnergy(input, { start: 0, end: 600 }, 1200),
    right = scopedEnergy(input, { start: 600, end: 1200 }, 1200);
  expect(left.known + right.known).toBe(0);
  expect(left.estimated + right.estimated).toBe(1);
  expect(left.costKnown + right.costKnown).toBe(0);
  expect(left.costEstimated + right.costEstimated).toBe(4);
  expect(left.entries[0]).toMatchObject({
    start: 0,
    end: 600,
    kwh: 0.5,
    category: "estimated",
    method: "prorated_estimate",
  });
  expect(scopedEnergy(input, { start: 0, end: 1200 }, 1200)).toMatchObject({
    known: 1,
    estimated: 0,
    costKnown: 4,
  });
  expect(JSON.stringify(input)).toBe(before);
});
it("qualified integrated-power slices retain derived quality on exact temporal clipping", () => {
  const p = {
    ...base,
    method: "integrated_power" as const,
    category: "derived" as const,
  };
  const result = scopedEnergy([p], { start: 300, end: 900 }, 1200);
  expect(result).toMatchObject({
    known: 0.5,
    estimated: 0,
    costKnown: 2,
    costEstimated: 0,
    unknownS: 0,
  });
  expect(result.entries[0]).toMatchObject({
    start: 300,
    end: 900,
    category: "derived",
  });
});
it.each(["counter_difference", "integrated_power"] as const)(
  "tariff changes split %s cost with honest allocation quality",
  (method) => {
    const result = scopedEnergy(
      [
        {
          ...base,
          method,
          tariffs: [
            { start: 0, end: 600, price: 4 },
            { start: 600, end: 1200, price: 6 },
          ],
        },
      ],
      { start: 0, end: 1200 },
      1200,
    );
    expect(result.known).toBe(1);
    expect(result.costKnown).toBe(method === "integrated_power" ? 5 : 0);
    expect(result.costEstimated).toBe(method === "integrated_power" ? 0 : 5);
  },
);
it("missing tariffs leave cost explicitly partial without discarding known energy", () => {
  const result = scopedEnergy(
    [
      {
        ...base,
        method: "integrated_power",
        tariffs: [{ start: 0, end: 600, price: 4 }],
      },
    ],
    { start: 0, end: 1200 },
    1200,
  );
  expect(result).toMatchObject({
    known: 1,
    costKnown: 2,
    unpricedKwh: 0.5,
    costUnknownS: 600,
  });
  expect(
    scopedEnergy([{ ...base, price: null }], { start: 0, end: 1200 }, 1200),
  ).toMatchObject({
    known: 1,
    costKnown: 0,
    unpricedKwh: 1,
    costUnknownS: 1200,
  });
});
it("unknown and recovered inputs preserve quality, actual-until and zero", () => {
  expect(
    scopedEnergy([{ ...base, kwh: null }], { start: 0, end: 1200 }, 1200),
  ).toMatchObject({ known: 0, unknownS: 1200, costUnknownS: 1200 });
  expect(
    scopedEnergy([{ ...base, kwh: 0 }], { start: 0, end: 1200 }, 1200),
  ).toMatchObject({ known: 0, unknownS: 0, costUnknownS: 0 });
  expect(
    scopedEnergy(
      [{ ...base, category: "recovered" }],
      { start: 0, end: 1200 },
      600,
    ),
  ).toMatchObject({ estimated: 0.5, known: 0, costEstimated: 2 });
  expect(
    scopedEnergy(
      [{ ...base, category: "recovered" }],
      { start: 0, end: 1200 },
      1200,
    ),
  ).toMatchObject({ known: 1, costKnown: 0, costEstimated: 4 });
  expect(
    scopedEnergy(
      [{ ...base, category: "unknown" }],
      { start: 0, end: 1200 },
      1200,
    ).entries[0]?.kwh,
  ).toBeNull();
  expect(
    scopedEnergy([base], { start: 1200, end: 1800 }, 1200).entries,
  ).toHaveLength(0);
  expect(scopedEnergy([base], { start: 0, end: 1200 }, -1).unknownS).toBe(0);
});
it.each([
  ["2026-03-29", 23],
  ["2026-10-25", 25],
] as const)(
  "Kyiv %s day accounts for %s UTC hours without duplicate counters",
  (date, hours) => {
    const day = kyivRange(date, date),
      midnight = day.end;
    expect(day.end - day.start).toBe(hours * 3600);
    const interval = { ...base, start: midnight - 600, end: midnight + 600 };
    const a = scopedEnergy([interval], day, midnight + 600),
      b = scopedEnergy(
        [interval],
        { start: midnight, end: midnight + 86400 },
        midnight + 600,
      );
    expect(a.estimated + b.estimated).toBe(1);
    expect(a.known + b.known).toBe(0);
  },
);
it.each(
  [
    [{ ...base, end: 0 }],
    [{ ...base, kwh: -1 }],
    [{ ...base, price: NaN }],
    [base, { ...base, start: 600 }],
    [
      {
        ...base,
        tariffs: [
          { start: 0, end: 700, price: 1 },
          { start: 600, end: 900, price: 2 },
        ],
      },
    ],
    [{ ...base, tariffs: [{ start: 0, end: 10, price: -1 }] }],
  ].map((intervals) => ({ intervals })),
)("conflicting metrology or tariff input fails closed: %j", ({ intervals }) => {
  expect(() =>
    scopedEnergy(intervals, { start: 0, end: 1200 }, 1200),
  ).toThrow();
});
it("invalid query scope fails closed", () => {
  expect(() => scopedEnergy([], { start: 1, end: 1 }, 1)).toThrow();
});
