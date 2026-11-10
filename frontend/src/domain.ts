import { validateVoltageSettings } from "./voltage";
import type {
  Energy,
  ForecastProof,
  Notice,
  Point,
  Settings,
  Window,
} from "./types";
import { connected } from "./history";
export const TZ = "Europe/Kyiv";
export const fmt = (v: number | null, digits = 1) =>
  v === null
    ? "—"
    : v.toLocaleString("uk-UA", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
export const time = (at: number) =>
  new Intl.DateTimeFormat("uk-UA", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
  }).format(at * 1000);
export const dateTime = (at: number) =>
  new Intl.DateTimeFormat("uk-UA", {
    timeZone: TZ,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(at * 1000);
export function originalEligible(p: ForecastProof): boolean {
  return (
    [p.reference, p.issued, p.received, p.coverage.start, p.coverage.end].every(
      Number.isFinite,
    ) &&
    p.frozen &&
    p.issued <= p.received &&
    p.issued <= p.reference - 43200 &&
    p.received <= p.reference - 43200 &&
    p.coverage.start <= p.reference &&
    p.coverage.end >= p.reference
  );
}
export function prioritize(notices: readonly Notice[]): Notice | null {
  const order = ["safety", "manual", "quality", "comfort", "budget"];
  return (
    [...notices].sort(
      (a, b) => order.indexOf(a.priority) - order.indexOf(b.priority),
    )[0] ?? null
  );
}
export function energySummary(e: Energy) {
  const reference = e.scope ? e.reference : null;
  return {
    remaining: reference === null ? null : reference - e.known,
    overrun:
      reference === null || e.projected === null
        ? null
        : Math.max(0, e.projected - reference),
    complete: e.unknownS === 0,
  };
}
function dateParts(date: string): number[] {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw Error("Вкажіть календарну дату");
  const p = date.split("-").map(Number);
  const [y = 0, m = 0, d = 0] = p;
  if (new Date(Date.UTC(y, m - 1, d)).toISOString().slice(0, 10) !== date)
    throw Error("Некоректна дата");
  return p;
}
function midnight(date: string): number {
  const [y = 0, m = 0, d = 0] = dateParts(date);
  const desired = Date.UTC(y, m - 1, d) / 1000;
  let guess = desired;
  for (let i = 0; i < 3; i++) {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: TZ,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(guess * 1000);
    const field = (name: string) =>
      Number(parts.find((p) => p.type === name)?.value);
    const local =
      Date.UTC(
        field("year"),
        field("month") - 1,
        field("day"),
        field("hour"),
        field("minute"),
      ) / 1000;
    guess += desired - local;
  }
  return guess;
}
export function shiftDate(date: string, days: number): string {
  const [y = 0, m = 0, d = 0] = dateParts(date);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}
export function kyivRange(first: string, last: string): Window {
  const start = midnight(first),
    end = midnight(shiftDate(last, 1));
  const calendarDays =
    (Date.parse(last + "T00:00:00Z") - Date.parse(first + "T00:00:00Z")) /
      86400000 +
    1;
  if (start >= end || calendarDays > 31)
    throw Error("Оберіть період до 31 календарного дня");
  return { start, end };
}
export function segments(
  points: readonly Point[],
  requireCoverage = false,
): Point[][] {
  const result: Point[][] = [];
  let run: Point[] = [];
  for (const p of points) {
    if (p.value === null) {
      if (run.length) result.push(run);
      run = [];
    } else {
      if (requireCoverage && run.length && !connected(run.at(-1)!, p)) {
        result.push(run);
        run = [];
      }
      run.push(p);
    }
  }
  if (run.length) result.push(run);
  return result;
}
export function decimate(points: readonly Point[], target = 256): Point[] {
  if (points.length > 4096 || target < 8) throw Error("Завелика серія");
  if (points.length <= target) return [...points];
  const selected = new Map<number, Point>();
  for (const p of points) if (p.value === null) selected.set(p.at, p);
  for (const run of segments(points)) {
    const bucket = Math.max(1, Math.ceil(points.length / target) * 4);
    for (let i = 0; i < run.length; i += bucket) {
      const part = run.slice(i, i + bucket);
      const ordered = [...part].sort((a, b) => (a.value ?? 0) - (b.value ?? 0));
      for (const p of [part[0], part.at(-1), ordered[0], ordered.at(-1)])
        if (p) selected.set(p.at, p);
    }
  }
  return [...selected.values()].sort((a, b) => a.at - b.at);
}
export function validateSettings(s: Settings): string[] {
  const errors: string[] = validateVoltageSettings(s);
  for (const [key, label] of [
    ["day", "День"],
    ["night", "Сон"],
  ] as const) {
    if (
      !Number.isFinite(s[key]) ||
      s[key] < 16 ||
      s[key] > 26 ||
      !Number.isInteger(s[key] * 2)
    )
      errors.push(`${label}:16–26°C із кроком0,5`);
  }
  if (s.night > s.day) errors.push("Ціль сну не може бути вищою за денну");
  if (!Number.isFinite(s.budget) || s.budget < 0 || s.budget > 2000)
    errors.push("Бюджет:0–2000кВт·год");
  if (
    !/^([01]\d|2[0-3]):[0-5]\d$/.test(s.windowStart) ||
    !/^([01]\d|2[0-3]):[0-5]\d$/.test(s.windowEnd) ||
    s.windowStart === s.windowEnd
  )
    errors.push("Вкажіть різні початок і кінець вікна");
  if (
    !["comfort", "balanced", "economy"].includes(s.strategy) ||
    !["auto", "observation"].includes(s.mode) ||
    !["auto", "manual", "stop"].includes(s.circulation) ||
    ![3, 6, 9].includes(s.scenario) ||
    typeof s.aiAdvice !== "boolean"
  )
    errors.push("Невідомий режим");
  if (
    !Number.isFinite(s.fan) ||
    s.fan < 0 ||
    s.fan > 100 ||
    !Number.isInteger(s.fan)
  )
    errors.push("Циркуляція:0–100%");
  if (!Number.isFinite(s.freshness) || s.freshness < 5 || s.freshness > 300)
    errors.push("Свіжість:5–300с");
  return errors;
}
export function windowContains(scope: Window | null, range: Window): boolean {
  return !!scope && scope.start === range.start && scope.end === range.end;
}

export async function withDeadline<T>(work: Promise<T>, ms = 2000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      work,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(Error("Час очікування вичерпано")), ms);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}
