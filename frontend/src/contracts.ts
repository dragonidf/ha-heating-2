import { voltageKeys } from "./voltage";
import type { APIReceipt, StatusView, Persisted } from "./types";
import { validateSettings } from "./domain";
export function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== "object" || Array.isArray(v))
    throw Error("Некоректний об’єкт");
  return v as Record<string, unknown>;
}
export function finite(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}
function integer(v: unknown): v is number {
  return finite(v) && Number.isInteger(v) && v >= 0;
}
function envelope(v: unknown, type: string) {
  if (JSON.stringify(v).length > 262144) throw Error("Завеликий пакет");
  const o = object(v);
  if (
    Object.keys(o).sort().join() !== "data,type,version" ||
    !Array.isArray(o.version) ||
    o.version.join() !== "2,0" ||
    o.type !== type
  )
    throw Error("Несумісна версія контракту");
  return object(o.data);
}
export function readStatus(v: unknown): StatusView {
  const d = envelope(v, "StatusView");
  if (
    !["status_seq", "owner_epoch", "archive_pending", "archive_lost"].every(
      (k) => integer(d[k]),
    ) ||
    !finite(d.snapshot_at) ||
    d.snapshot_at < 0 ||
    !["boot_id", "mode", "snapshot_id"].every(
      (k) => typeof d[k] === "string" && d[k].length > 0 && d[k].length <= 256,
    ) ||
    ![null, "heat", "stop_demand"].includes(d.actual as null) ||
    !["heat", "stop_demand"].includes(d.desired as string) ||
    ![
      null,
      "requested",
      "prepared",
      "sent",
      "ha_acknowledged",
      "device_echoed",
      "external_physical_evidence",
      "failed",
      "unknown",
    ].includes(d.receipt_stage as null) ||
    d.physical_verified !== false ||
    Object.keys(d).length !== 12
  )
    throw Error("Недовірений fake status");
  return d as unknown as StatusView;
}
export function readReceipt(v: unknown): APIReceipt {
  const d = envelope(v, "APIReceipt");
  if (
    typeof d.request_id !== "string" ||
    typeof d.reason !== "string" ||
    !integer(d.revision) ||
    ![
      "saved",
      "denied",
      "conflict",
      "unavailable",
      "accepted_fake",
      "observed_fake",
    ].includes(d.status as string) ||
    !(d.persisted_revision === null || integer(d.persisted_revision)) ||
    (d.status === "saved") !== (d.persisted_revision !== null) ||
    Object.keys(d).length !== 5
  )
    throw Error("Недовірене підтвердження");
  return d as unknown as APIReceipt;
}
export function persisted(v: unknown): Persisted {
  const d = object(v);
  const s = object(d.values);
  if (
    !integer(d.revision) ||
    d.revision < 1 ||
    !(d.lastRequest === null || typeof d.lastRequest === "string") ||
    Object.keys(d).length !== 3 ||
    Object.keys(s).sort().join() !==
      [
        "day",
        "night",
        "budget",
        "windowStart",
        "windowEnd",
        "strategy",
        "mode",
        "circulation",
        "fan",
        "scenario",
        "freshness",
        "aiAdvice",
        ...(voltageKeys.some((key) => Object.hasOwn(s, key))
          ? voltageKeys
          : []),
      ]
        .sort()
        .join() ||
    validateSettings(s as unknown as Persisted["values"]).length
  )
    throw Error("Збережені дані пошкоджені");
  return structuredClone(d as unknown as Persisted);
}

export function readForecast(
  frozen: unknown,
  source: unknown,
): import("./types").Forecast {
  const f = envelope(frozen, "ForecastRecord"),
    s = envelope(source, "ForecastRecord");
  const curve = object(f.curve);
  if (
    f.role !== "original" ||
    s.role !== "latest" ||
    f.cycle_id !== s.cycle_id ||
    f.reference !== s.reference ||
    JSON.stringify(f.curve) !== JSON.stringify(s.curve) ||
    !finite(f.reference) ||
    !finite(curve.issued) ||
    !finite(s.recorded_at) ||
    !integer(curve.model_revision) ||
    typeof curve.plan_id !== "string" ||
    typeof curve.identity !== "string" ||
    !Array.isArray(curve.points) ||
    curve.points.length < 1 ||
    curve.points.length > 865
  )
    throw Error("Немає узгодженого незмінного оригіналу");
  const points = curve.points.map((p: unknown) => {
    if (!Array.isArray(p) || p.length !== 2 || !finite(p[0]))
      throw Error("Некоректна точка");
    const interval = object(p[1]);
    if (
      !finite(interval.low) ||
      !finite(interval.high) ||
      interval.low > interval.high
    )
      throw Error("Некоректний інтервал");
    return { at: p[0], value: (interval.low + interval.high) / 2 };
  });
  const first = points[0]!,
    last = points[points.length - 1]!;
  const scope = f.energy_scope === null ? null : object(f.energy_scope);
  if (
    scope &&
    (!finite(scope.start) ||
      !finite(scope.end) ||
      scope.start !== f.reference ||
      scope.end <= scope.start)
  )
    throw Error("Неправильний період енергії");
  return {
    id: curve.identity,
    reference: f.reference,
    issued: curve.issued,
    received: s.recorded_at,
    coverage: { start: first.at, end: last.at },
    frozen: true,
    model: curve.model_revision,
    plan: curve.plan_id,
    source: s.identity as string,
    points,
    energy: finite(f.planned_kwh) ? f.planned_kwh : null,
    scope: scope
      ? { start: scope.start as number, end: scope.end as number }
      : null,
  };
}
export function readBudget(value: unknown): import("./types").Energy {
  const b = envelope(value, "BudgetReceipt");
  const scope = b.scope === null ? null : object(b.scope);
  if (
    !finite(b.known_spent_kwh) ||
    b.known_spent_kwh < 0 ||
    !finite(b.unknown_s) ||
    b.unknown_s < 0 ||
    !finite(b.latest_projected_kwh) ||
    b.latest_projected_kwh < 0 ||
    !(
      b.reference_kwh === null ||
      (finite(b.reference_kwh) && b.reference_kwh >= 0)
    ) ||
    (b.reference_kwh !== null && !scope) ||
    (scope &&
      (!finite(scope.start) || !finite(scope.end) || scope.end <= scope.start))
  )
    throw Error("Неправильний бюджет або період");
  return {
    actualUntil: finite(b.actual_until) ? b.actual_until : undefined,
    reference: b.reference_kwh,
    known: b.known_spent_kwh,
    estimated: null,
    unknownS: b.unknown_s,
    projected: b.latest_projected_kwh,
    scope: scope
      ? { start: scope.start as number, end: scope.end as number }
      : null,
  };
}
