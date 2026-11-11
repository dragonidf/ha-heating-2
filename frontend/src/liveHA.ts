/** Use only real HA frontend states. No demo data and no actuator transport. */
import { SnapshotFeed } from "./mock";
import { emptyView } from "./operator";
import type { OperatorAPI, Control, ModelAction } from "./operator";
import type {
  APIReceipt,
  HistoryPage,
  Persisted,
  Settings,
  Snapshot,
  Window,
} from "./types";

export interface LiveState {
  state: string;
  last_changed?: string;
  last_reported?: string;
  attributes: Record<string, unknown>;
}
export interface LiveHass {
  states: Record<string, LiveState | undefined>;
  connected?: boolean;
}
export type BaseBindings = Record<
  | "thermostat"
  | "room"
  | "grid"
  | "voltage_l1"
  | "voltage_l2"
  | "voltage_l3"
  | "kws_l1"
  | "kws_l2"
  | "kws_l3"
  | "kws_energy",
  string
>;
export type FanBindingRole =
  | "fireplace" | "circulation" | "fan_mode"
  | "fan_night" | "fan_standard" | "fan_intense"
  | "fan_backup" | "fan_control" | "recuperator" | "bath";
export type LiveBindings = BaseBindings & Partial<Record<FanBindingRole, string>>;
export const optionalRoles: FanBindingRole[] = [
  "fireplace", "circulation", "fan_mode",
  "fan_night", "fan_standard", "fan_intense",
  "fan_backup", "fan_control", "recuperator", "bath",
];
export interface LiveTelemetry {
  origin: "ha_last_known";
  room: number | null;
  thermostatMode: string | null;
  thermostatSetpoint: number | null;
  grid: boolean | null;
  voltages: (number | null)[];
  kws: (number | null)[];
  kwsTotal: number | null;
  kwsEnergy: number | null;
  lastReported: Record<string, string | null>;
  fireplaceC: number | null;
  fireplaceDeltaC: number | null;
  fanActual: "on" | "off" | null;
  fanPercent: number | null;
  fanMode: string | null;
  fanSpeeds: (number | null)[];
  fanBackupVerified: boolean | null;
  fanControlEnabled: boolean | null;
  ventilation: { recuperator: boolean | null; bath: boolean | null };
}
const roles: (keyof LiveBindings)[] = [
  "thermostat",
  "room",
  "grid",
  "voltage_l1",
  "voltage_l2",
  "voltage_l3",
  "kws_l1",
  "kws_l2",
  "kws_l3",
  "kws_energy",
];
function number(state: LiveState | undefined, unit: string, max: number) {
  if (!state || state.attributes.unit_of_measurement !== unit) return null;
  const value = Number(state.state);
  return state.state.trim() !== "" &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= max
    ? value
    : null;
}
function blank(): Snapshot {
  const now = Date.now() / 1000;
  return {
    version: 1,
    seq: 0,
    generation: 1,
    now,
    connected: false,
    permitted: false,
    status: {
      status_seq: 0,
      boot_id: "real-shadow",
      owner_epoch: 0,
      actual: null,
      desired: "stop_demand",
      mode: "SHADOW",
      snapshot_id: "real-shadow-0",
      snapshot_at: now,
      archive_pending: 0,
      archive_lost: 0,
      receipt_stage: null,
      physical_verified: false,
    },
    room: { value: null, observed: 0, quality: "missing" },
    grid: null,
    notices: [
      {
        priority: "manual",
        text: "Спостереження без керування. Старий контролер не змінено.",
      },
    ],
    fan: {
      phase: "unknown",
      requested: null,
      actual: null,
      night: false,
      fire: false,
    },
    oneShot: { state: "unknown_outcome", expires: null, gridEpoch: 0 },
    diagnostics: {
      loopLagMs: null,
      persistence: "not_migrated",
      worker: "not_connected",
      source: "ha_states",
    },
  };
}
export class LiveHAAPI implements OperatorAPI {
  readonly native = true;
  readonly live = true;
  readonly session = Object.freeze({ role: "read_only_live" });
  readonly feed = new SnapshotFeed(blank());
  readonly model = { revision: 0, candidate: false, frozen: true };
  readonly view = emptyView(Date.now() / 1000);
  readonly dataErrors = [
    "Архів, планувальник та налаштування Heating AI 2.0 ще не перенесені.",
  ];
  readonly scenario = undefined;
  telemetry: LiveTelemetry = {
    origin: "ha_last_known",
    room: null,
    thermostatMode: null,
    thermostatSetpoint: null,
    grid: null,
    voltages: [null, null, null],
    kws: [null, null, null],
    kwsTotal: null,
    kwsEnergy: null,
    lastReported: {},
    fireplaceC: null, fireplaceDeltaC: null,
    fanActual: null, fanPercent: null, fanMode: null,
    fanSpeeds: [null, null, null], fanBackupVerified: null, fanControlEnabled: null,
    ventilation: { recuperator: null, bath: null },
  };
  constructor(
    private readonly bindings: LiveBindings,
    hass: LiveHass,
  ) {
    if (
      roles.some((role) => typeof bindings[role] !== "string") ||
      Object.keys(bindings).some((role) => ![...roles, ...optionalRoles].includes(role as keyof LiveBindings)) ||
      new Set(Object.values(bindings)).size !== Object.keys(bindings).length ||
      roles.some(
        (role) =>
          typeof bindings[role] !== "string" || !bindings[role].includes("."),
      )
    ) {
      throw Error("Невалідна прив'язка до реальних сутностей HA");
    }
    this.updateHass(hass);
  }
  updateHass(hass: LiveHass) {
    const s = (role: keyof LiveBindings) => {
      const entityId = this.bindings[role];
      return entityId ? hass.states?.[entityId] : undefined;
    };
    const stamp = (state?: LiveState) =>
      state?.last_reported ?? state?.last_changed ?? null;
    const now = Date.now() / 1000;
    const room = number(s("room"), "°C", 65);
    const observed = Date.parse(stamp(s("room")) ?? "") / 1000;
    const gridState = s("grid")?.state;
    const grid =
      gridState === "Наявна мережа"
        ? true
        : gridState === "Відсутня мережа"
          ? false
          : null;
    const binary = (role: FanBindingRole) => {
      const value = s(role)?.state;
      return value === "on" ? true : value === "off" ? false : null;
    };
    const fireplaceC = number(s("fireplace"), "°C", 65);
    const fanActualRaw = s("circulation")?.state;
    const fanActual = fanActualRaw === "on" || fanActualRaw === "off" ? fanActualRaw : null;
    const fanPctRaw = s("circulation")?.attributes.percentage;
    const fanPercent = typeof fanPctRaw === "number" && Number.isFinite(fanPctRaw) && fanPctRaw >= 0 && fanPctRaw <= 100 ? fanPctRaw : null;
    const fanMode = s("fan_mode")?.state ?? null;
    const fanSpeeds = (["fan_night", "fan_standard", "fan_intense"] as const).map((role) => number(s(role), "%", 100));
    const voltageRoles = ["voltage_l1", "voltage_l2", "voltage_l3"] as const;
    const kwsRoles = ["kws_l1", "kws_l2", "kws_l3"] as const;
    const volts = voltageRoles.map((role) => number(s(role), "V", 400));
    const power = kwsRoles.map((role) => number(s(role), "kW", 12));
    const kwsTotal = power.every((v) => v !== null)
      ? Math.round(power.reduce<number>((sum, v) => sum + (v ?? 0), 0) * 1000) /
        1000
      : null;
    const thermostat = s("thermostat");
    const target = thermostat?.attributes.temperature;
    this.telemetry = {
      origin: "ha_last_known",
      room,
      thermostatMode: thermostat?.state ?? null,
      thermostatSetpoint:
        typeof target === "number" && Number.isFinite(target) ? target : null,
      grid,
      voltages: volts,
      kws: power,
      kwsTotal,
      kwsEnergy: number(s("kws_energy"), "kWh", 1e9),
      lastReported: Object.fromEntries(
        [...roles, ...optionalRoles].map((role) => [role, stamp(s(role))]),
      ),
      fireplaceC,
      fireplaceDeltaC: fireplaceC !== null && room !== null ? Math.round((fireplaceC - room) * 100) / 100 : null,
      fanActual,
      fanPercent,
      fanMode,
      fanSpeeds,
      fanBackupVerified: binary("fan_backup"),
      fanControlEnabled: binary("fan_control"),
      ventilation: { recuperator: binary("recuperator"), bath: binary("bath") },
    };
    const before = this.feed.value;
    const quality =
      room === null
        ? "missing"
        : Number.isFinite(observed) &&
            now - observed >= 0 &&
            now - observed <= 4 * 3600
          ? "valid"
          : "stale";
    const notices: Snapshot["notices"] =
      grid !== true
        ? [
            {
              priority: "safety",
              text:
                grid === false
                  ? "Електромережа відсутня за основним хелпером."
                  : "Статус електромережі не підтверджений.",
            },
          ]
        : [
            {
              priority: "manual",
              text: "Режим спостереження: новий контролер не керує термостатом.",
            },
          ];
    const next: Snapshot = {
      ...before,
      seq: before.seq + 1,
      now,
      connected: hass.connected !== false,
      permitted: false,
      status: {
        ...before.status,
        status_seq: before.status.status_seq + 1,
        snapshot_at: now,
        snapshot_id: "real-shadow-" + (before.seq + 1),
      },
      room: {
        value: room,
        observed: Number.isFinite(observed) ? observed : 0,
        quality,
      },
      grid,
      notices,
    };
    this.feed.reset(next);
  }
  canChange() {
    return false;
  }
  canStop() {
    return false;
  }
  requestId() {
    return "read-only-live";
  }
  async settings(): Promise<Persisted> {
    throw Error("Реальні налаштування ще не імпортовано — жодних демозначень");
  }
  async save(
    _id: string,
    _expected: number,
    _values: Settings,
    _session: object,
  ): Promise<APIReceipt> {
    throw Error("Доступ до запису закрито");
  }
  control(_kind: Control, _session: object): APIReceipt {
    return {
      request_id: "live",
      status: "denied",
      revision: 0,
      persisted_revision: null,
      reason: "Немає права керування в режимі спостереження",
    };
  }
  modelAction(_kind: ModelAction, _session: object) {
    return "Навчання не підключено до live-даних";
  }
  history(_range: Window): HistoryPage {
    throw Error("Історію ще не імпортовано");
  }
  energyHistory() {
    return [];
  }
  reconnect() {
    return Promise.resolve();
  }
}
