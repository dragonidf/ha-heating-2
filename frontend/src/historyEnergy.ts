import type { EnergyInterval, Window } from "./types";
// Mirrors WP2A energy.clip / dated_cost. Partial counter allocation is an
// estimate, never a new measurement. Inputs are immutable, non-overlapping slices.
export function scopedEnergy(
  source: readonly EnergyInterval[],
  scope: Window,
  now: number,
) {
  if (
    ![scope.start, scope.end, now].every(Number.isFinite) ||
    scope.start >= scope.end
  )
    throw Error("Некоректний період енергії");
  const until = Math.max(scope.start, Math.min(scope.end, now));
  let previousEnd = -Infinity;
  const entries = [...source]
    .sort((a, b) => a.start - b.start)
    .flatMap((i) => {
      if (
        ![i.start, i.end].every(Number.isFinite) ||
        i.end <= i.start ||
        i.start < previousEnd ||
        (i.kwh !== null && (!Number.isFinite(i.kwh) || i.kwh < 0)) ||
        (i.price !== null && (!Number.isFinite(i.price) || i.price < 0))
      )
        throw Error("Перекривні або некоректні інтервали");
      previousEnd = i.end;
      const start = Math.max(i.start, scope.start),
        end = Math.min(i.end, until);
      if (start >= end) return [];
      const partial = start !== i.start || end !== i.end;
      const estimated =
        i.category === "estimated" ||
        (partial &&
          (i.method !== "integrated_power" || i.category === "recovered"));
      const kwh =
        i.category === "unknown" || i.kwh === null
          ? null
          : (i.kwh * (end - start)) / (i.end - i.start);
      const category =
        kwh === null ? "unknown" : estimated ? "estimated" : i.category;
      const method = estimated && partial ? "prorated_estimate" : i.method;
      const tariffs = i.tariffs
        ? [...i.tariffs].sort((a, b) => a.start - b.start)
        : i.price === null
          ? []
          : [{ start: i.start, end: i.end, price: i.price }];
      let tariffEnd = -Infinity,
        pricedS = 0,
        costKnown = 0,
        costEstimated = 0,
        costKnownS = 0,
        costEstimatedS = 0;
      for (const t of tariffs) {
        if (
          ![t.start, t.end, t.price].every(Number.isFinite) ||
          t.end <= t.start ||
          t.start < tariffEnd ||
          t.price < 0
        )
          throw Error("Конфлікт тарифів");
        tariffEnd = t.end;
        const seconds = Math.max(
          0,
          Math.min(end, t.end) - Math.max(start, t.start),
        );
        pricedS += seconds;
        if (kwh !== null) {
          const value = ((kwh * seconds) / (end - start)) * t.price;
          if (
            estimated ||
            category === "recovered" ||
            (i.method !== "integrated_power" && seconds < end - start)
          ) {
            costEstimated += value;
            costEstimatedS += seconds;
          } else {
            costKnown += value;
            costKnownS += seconds;
          }
        }
      }
      return [
        {
          ...i,
          start,
          end,
          kwh,
          category,
          method,
          costKnown,
          costEstimated,
          costKnownS,
          costEstimatedS,
          unpricedKwh: kwh === null ? 0 : kwh * (1 - pricedS / (end - start)),
          costUnknownS: kwh === null ? end - start : end - start - pricedS,
        },
      ];
    });
  const known = entries
    .filter((i) => i.category !== "estimated")
    .reduce((sum, i) => sum + (i.kwh ?? 0), 0);
  const estimated = entries
    .filter((i) => i.category === "estimated")
    .reduce((sum, i) => sum + (i.kwh ?? 0), 0);
  const observedS = entries
    .filter((i) => i.kwh !== null && i.category !== "estimated")
    .reduce((sum, i) => sum + i.end - i.start, 0);
  const coveredS = entries.reduce((sum, i) => sum + i.end - i.start, 0);
  return {
    entries,
    known,
    estimated,
    unknownS: Math.max(0, until - scope.start - observedS),
    costKnown: entries.reduce((sum, i) => sum + i.costKnown, 0),
    costEstimated: entries.reduce((sum, i) => sum + i.costEstimated, 0),
    unpricedKwh: entries.reduce((sum, i) => sum + i.unpricedKwh, 0),
    costUnknownS:
      Math.max(0, until - scope.start - coveredS) +
      entries.reduce((sum, i) => sum + i.costUnknownS, 0),
  };
}
