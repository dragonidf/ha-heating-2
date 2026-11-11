import { finite, object, persisted, readStatus } from "./contracts";
import { validateVoltageSettings, voltageKeys } from "./voltage";
import type { VoltageView, PowerView } from "./types";
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
export function readVoltage(value: unknown): VoltageView {
  const v = object(value),
    ages = object(v.ages),
    limits = object(v.limits);
  const phases = ["L1", "L2", "L3"];
  const age = (value: unknown) =>
    value === null || (finite(value) && value >= 0);
  if (
    !["LOW", "HIGH", "MISSING_OR_STALE", "STABILIZING", "NORMAL"].includes(
      v.status as string,
    ) ||
    v.eligible !== (v.status === "NORMAL") ||
    !Array.isArray(v.affected_phases) ||
    new Set(v.affected_phases).size !== v.affected_phases.length ||
    !v.affected_phases.every((phase) => phases.includes(phase as string)) ||
    !text(v.reason) ||
    Object.keys(ages).sort().join() !== phases.join() ||
    !Object.values(ages).every(age) ||
    !Array.isArray(v.phases) ||
    v.phases.length !== 3 ||
    v.phases.some((raw: unknown, index: number) => {
      const p = object(raw);
      return (
        p.phase !== phases[index] ||
        !(p.voltage_v === null || (finite(p.voltage_v) && p.voltage_v >= 0)) ||
        !age(p.age_s) ||
        p.age_s !== ages[phases[index]!] ||
        ![null, true, false].includes(p.online as null) ||
        typeof p.qualified !== "boolean" ||
        (p.qualified &&
          (p.voltage_v === null || p.age_s === null || p.online !== true))
      );
    }) ||
    Object.keys(limits).sort().join() !== [...voltageKeys].sort().join() ||
    validateVoltageSettings(limits).length ||
    v.source_role !== "grid_input_voltage" ||
    v.source_provider !== "zigbee2mqtt_input220" ||
    v.physical_authority !== false ||
    v.scope !== "synthetic_only"
  )
    throw Error("Недовірений стан вхідної напруги");
  return structuredClone(v as unknown as VoltageView);
}
export function readPower(value: unknown): PowerView {
  const p = object(value),
    phases = ["L1", "L2", "L3"];
  const nonnegative = (v: unknown) => v === null || (finite(v) && v >= 0);
  if (
    p.source_role !== "boiler_power_energy" ||
    p.source_provider !== "tuya_local_kws" ||
    p.cloud_duplicate_policy !== "excluded_no_fallback" ||
    !["OFF", "PUMP_ONLY", "~3kW", "~6kW", "~9kW", "UNKNOWN"].includes(
      p.stage as string,
    ) ||
    (p.stage !== "UNKNOWN" && p.total_active_w === null) ||
    !nonnegative(p.total_active_w) ||
    !nonnegative(p.total_imported_kwh) ||
    !Array.isArray(p.phases) ||
    p.phases.length !== 3 ||
    p.phases.some((raw: unknown, index: number) => {
      const phase = object(raw);
      return (
        phase.phase !== phases[index] ||
        !nonnegative(phase.active_w) ||
        !nonnegative(phase.age_s)
      );
    }) ||
    !text(p.reason) ||
    p.physical_authority !== false ||
    p.physical_heat !== null ||
    p.scope !== "synthetic_only"
  )
    throw Error("Недовірені дані KWS Tuya Local");
  return structuredClone(p as unknown as PowerView);
}
function validateHealth(raw: unknown): void {
  const h = object(raw);
  if (
    h.physical_verified !== false ||
    h.semantics !== "proposed_only_no_device_ack" ||
    typeof h.mode !== "string" ||
    !(h.notification === null || typeof h.notification === "string") ||
    !Array.isArray(h.components) ||
    h.components.length !== 6
  )
    throw Error("Непридатна діагностика");
  if (h.proposal !== undefined && h.proposal !== null) {
    const p = object(h.proposal);
    if (
      p.physical_authority !== false ||
      p.stage !== "proposed" ||
      typeof p.id !== "string" ||
      typeof p.action !== "string" ||
      !(p.mode === undefined || p.mode === "AUTO" || p.mode === "HEAT")
    )
      throw Error("Непридатна пропозиція режиму");
  }
  const keys = new Set<string>();
  for (const raw of h.components) {
    const row = object(raw);
    if (
      typeof row.key !== "string" ||
      keys.has(row.key) ||
      ![
        "living_room",
        "fireplace",
        "thermostat",
        "utility",
        "kws",
        "controller",
      ].includes(row.key) ||
      typeof row.label !== "string" ||
      typeof row.reason !== "string" ||
      row.reason.length > 600 ||
      !["OK", "PROBLEM", "WAITING"].includes(row.status as string) ||
      !(row.age_s === null || (finite(row.age_s) && row.age_s >= 0)) ||
      !finite(row.checked_at) ||
      !finite(row.last_transition) ||
      row.physical_verified !== false ||
      typeof row.fallback_action !== "string"
    )
      throw Error("Непридатний компонент діагностики");
    keys.add(row.key);
  }
}

export function readSnapshot(value: unknown): Snapshot {
  const s = object(bounded(value)),
    room = object(s.room),
    fan = object(s.fan),
    shot = object(s.oneShot),
    diag = object(s.diagnostics);
  if (s.system_health !== undefined) validateHealth(s.system_health);
  if (s.power !== undefined) readPower(s.power);
  const voltage = s.voltage === undefined ? undefined : readVoltage(s.voltage);
  const status = readStatus({
    version: [2, 0],
    type: "StatusView",
    data: s.status,
  });
  if (
    (s.demand_eligible !== undefined &&
      (typeof s.demand_eligible !== "boolean" ||
        (s.demand_eligible === true && voltage?.eligible !== true))) ||
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
    f = o.original === null ? null : object(o.original),
    e = object(o.cycleEnergy);
  const scope = (v: unknown) => {
    const w = object(v);
    return finite(w.start) && finite(w.end) && w.start < w.end;
  };
  if (f !== null) {
    const coverage = object(f.coverage);
    if (
      ![f.id, f.plan, f.source].every(text) ||
      ![f.reference, f.issued, f.received, coverage.start, coverage.end].every(
        finite,
      ) ||
      typeof f.frozen !== "boolean" ||
      !integer(f.model) ||
      !(f.energy === null || finite(f.energy)) ||
      !(f.scope === null || scope(f.scope))
    )
      throw Error("Некоректний огляд");
    readPoints(f.points, 865);
  }
  if (
    o.physical_authority !== false ||
    typeof o.enabled !== "boolean" ||
    !Array.isArray(o.gates) ||
    o.gates.join() !== "B01,B02,B03,B04,B05,B06,B07,B08" ||
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
