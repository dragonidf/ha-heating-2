import { finite, object, persisted, readStatus } from "./contracts";
import type { OperatorView } from "./operator";
import type { EnergyInterval, HistoryPage, Point, Snapshot } from "./types";
const integer = (v: unknown): v is number =>
  Number.isSafeInteger(v) && (v as number) >= 0;
const text = (v: unknown): v is string =>
  typeof v === "string" && v.length > 0 && v.length <= 1024;
const quality = (v: unknown) =>
  ["valid", "estimated", "stale", "missing", "conflicting"].includes(
    v as string,
  );
export function bounded(v: unknown, bytes = 262144): unknown {
  if (new TextEncoder().encode(JSON.stringify(v)).byteLength > bytes)
    throw Error("Завеликий пакет");
  return v;
}
export function readSnapshot(value: unknown): Snapshot {
  const s = object(bounded(value)),
    room = object(s.room),
    fan = object(s.fan),
    shot = object(s.oneShot),
    diag = object(s.diagnostics);
  const status = readStatus({
    version: [2, 0],
    type: "StatusView",
    data: s.status,
  });
  if (
    s.version !== 1 ||
    !integer(s.seq) ||
    !integer(s.generation) ||
    !finite(s.now) ||
    s.now < 0 ||
    typeof s.connected !== "boolean" ||
    typeof s.permitted !== "boolean" ||
    !(room.value === null || finite(room.value)) ||
    !finite(room.observed) ||
    !quality(room.quality) ||
    ![true, false, null].includes(s.grid as null) ||
    !Array.isArray(s.notices) ||
    s.notices.length > 64 ||
    !s.notices.every((v: unknown) => {
      const n = object(v);
      return (
        ["safety", "manual", "quality", "comfort", "budget"].includes(
          n.priority as string,
        ) && text(n.text)
      );
    }) ||
    !text(fan.phase) ||
    ![fan.requested, fan.actual].every((v) => v === null || finite(v)) ||
    typeof fan.night !== "boolean" ||
    typeof fan.fire !== "boolean" ||
    ![
      "inactive",
      "armed",
      "cancelled",
      "expired",
      "consumed",
      "unknown_outcome",
    ].includes(shot.state as string) ||
    !(shot.expires === null || finite(shot.expires)) ||
    !integer(shot.gridEpoch) ||
    !(diag.loopLagMs === null || finite(diag.loopLagMs)) ||
    ![diag.persistence, diag.worker, diag.source].every(text)
  )
    throw Error("Недовірений стан Home Assistant");
  return structuredClone({ ...s, status } as unknown as Snapshot);
}
export function readPoints(value: unknown, limit = 100000): readonly Point[] {
  if (!Array.isArray(value) || value.length > limit)
    throw Error("Некоректний архів");
  for (const raw of value) {
    const p = object(raw);
    if (
      !finite(p.at) ||
      !(p.value === null || finite(p.value)) ||
      (p.quality !== undefined && !quality(p.quality))
    )
      throw Error("Некоректна точка");
    if (p.coverage !== undefined) {
      const c = object(p.coverage);
      if (!text(c.source) || !finite(c.from) || c.from > p.at)
        throw Error("Некоректне покриття");
    }
  }
  return structuredClone(value as Point[]);
}
export function readPage(value: unknown): HistoryPage {
  const p = object(bounded(value, 65536));
  const rows = readPoints(p.rows, 256);
  if (!integer(p.watermark)) throw Error("Некоректний архів");
  if (p.cursor !== null) {
    const c = object(p.cursor);
    if (!integer(c.offset) || !text(c.scope) || c.watermark !== p.watermark)
      throw Error("Некоректний курсор");
  }
  return {
    rows,
    cursor: p.cursor as HistoryPage["cursor"],
    watermark: p.watermark,
  };
}
export function readEnergy(value: unknown): readonly EnergyInterval[] {
  bounded(value);
  if (!Array.isArray(value) || value.length > 4096)
    throw Error("Некоректна енергія");
  for (const raw of value) {
    const e = object(raw);
    if (
      !finite(e.start) ||
      !finite(e.end) ||
      e.start >= e.end ||
      !(e.kwh === null || (finite(e.kwh) && e.kwh >= 0)) ||
      !(e.price === null || (finite(e.price) && e.price >= 0)) ||
      !["confirmed", "derived", "estimated", "recovered", "unknown"].includes(
        e.category as string,
      ) ||
      (e.method !== undefined &&
        ![
          "counter_difference",
          "integrated_power",
          "prorated_estimate",
        ].includes(e.method as string))
    )
      throw Error("Некоректна енергія");
    if (
      e.tariffs !== undefined &&
      (!Array.isArray(e.tariffs) ||
        !e.tariffs.every((v: unknown) => {
          const t = object(v);
          return (
            finite(t.start) &&
            finite(t.end) &&
            t.start < t.end &&
            finite(t.price) &&
            t.price >= 0
          );
        }))
    )
      throw Error("Некоректний тариф");
  }
  return structuredClone(value as EnergyInterval[]);
}
export function readModel(value: unknown) {
  const m = object(value);
  if (
    !integer(m.revision) ||
    typeof m.candidate !== "boolean" ||
    typeof m.frozen !== "boolean"
  )
    throw Error("Некоректна модель");
  return { revision: m.revision, candidate: m.candidate, frozen: m.frozen };
}
export function readOverview(
  value: unknown,
): OperatorView & { model: ReturnType<typeof readModel>; enabled: boolean } {
  const o = object(bounded(value)),
    f = object(o.original),
    e = object(o.cycleEnergy),
    coverage = object(f.coverage);
  const scope = (v: unknown) => {
    const w = object(v);
    return finite(w.start) && finite(w.end) && w.start < w.end;
  };
  if (
    o.physical_authority !== false ||
    typeof o.enabled !== "boolean" ||
    !Array.isArray(o.gates) ||
    o.gates.join() !== "B01,B02,B03,B04,B05,B06,B07,B08" ||
    ![f.id, f.plan, f.source].every(text) ||
    ![f.reference, f.issued, f.received, coverage.start, coverage.end].every(
      finite,
    ) ||
    typeof f.frozen !== "boolean" ||
    !integer(f.model) ||
    !(f.energy === null || finite(f.energy)) ||
    !(f.scope === null || scope(f.scope)) ||
    ![e.reference, e.estimated, e.projected].every(
      (v) => v === null || finite(v),
    ) ||
    !finite(e.known) ||
    e.known < 0 ||
    !finite(e.unknownS) ||
    e.unknownS < 0 ||
    !(e.scope === null || scope(e.scope)) ||
    !(e.actualUntil === undefined || finite(e.actualUntil)) ||
    !Array.isArray(o.timeline) ||
    o.timeline.length > 4096 ||
    !o.timeline.every((v: unknown) => {
      const t = object(v);
      return (
        finite(t.start) &&
        finite(t.end) &&
        t.start < t.end &&
        ["heat", "outage", "fire"].includes(t.kind as string)
      );
    }) ||
    !Array.isArray(o.metrics) ||
    o.metrics.length > 64 ||
    !o.metrics.every((v: unknown) => {
      const m = object(v);
      return (
        [m.hours, m.days, m.samples].every(integer) &&
        [m.mae, m.p90].every((v) => v === null || (finite(v) && v >= 0)) &&
        typeof m.qualified === "boolean"
      );
    })
  )
    throw Error("Некоректний огляд");
  readPoints(f.points, 865);
  readPoints(o.latest, 4096);
  return structuredClone({
    ...o,
    actual: [],
    model: readModel(o.model),
  } as unknown as OperatorView & {
    model: ReturnType<typeof readModel>;
    enabled: boolean;
  });
}
export function validSettings(value: unknown): boolean {
  try {
    persisted({ revision: 1, values: value, lastRequest: null });
    return true;
  } catch {
    return false;
  }
}
