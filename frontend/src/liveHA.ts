/** Use only real HA frontend states. No demo data and no actuator transport. */
import { SnapshotFeed } from "./mock";
import { fetchRoomRecorder } from "./liveRecorder";
import { emptyView } from "./operator";
import type { OperatorAPI, Control, ModelAction } from "./operator";
import type {
  APIReceipt,
  HistoryPage,
  Persisted,
  Settings,
  Snapshot,
  Window,
  Point,
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
  user?: { is_admin?: boolean };
  callWS?: (message: Record<string, unknown>) => Promise<unknown>;
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
  | "day_target"
  | "night_target"
  | "day_upper"
  | "night_upper"
  | "sleep_start"
  | "sleep_end"
  | "heating_start"
  | "heating_end"
  | "strategy"
  | "power_model"
  | "return_probe"
  | "weather_forecast"
  | "legacy_model"
  | "stored_heat"
  | "outage_calendar"
  | "fireplace"
  | "circulation"
  | "fan_mode"
  | "fan_night"
  | "fan_standard"
  | "fan_intense"
  | "fan_backup"
  | "fan_control"
  | "recuperator"
  | "bath";
export type LiveBindings = BaseBindings &
  Partial<Record<FanBindingRole, string>>;
export const optionalRoles: FanBindingRole[] = [
  "day_target",
  "night_target",
  "day_upper",
  "night_upper",
  "sleep_start",
  "sleep_end",
  "heating_start",
  "heating_end",
  "strategy",
  "power_model",
  "return_probe",
  "weather_forecast",
  "legacy_model",
  "stored_heat",
  "outage_calendar",
  "fireplace",
  "circulation",
  "fan_mode",
  "fan_night",
  "fan_standard",
  "fan_intense",
  "fan_backup",
  "fan_control",
  "recuperator",
  "bath",
];
export interface SourceSummary {
  weatherStatus: string;
  weatherHours: number;
  weatherHorizonEnd: number | null;
  weatherIssuedKnown: false;
  outageStatus: string;
  nextOutageAt: number | null;
  outagesUpcomingCount: number;
  gridForecastQualified: false;
}
export interface CoastSummary {
  status: string;
  min: number | null;
  end: number | null;
  hours: number;
  qualified: false;
}
export interface VirtualPlanSummary {
  status: "VIRTUAL_CONDITIONAL" | "BLOCKED_INPUTS";
  reason: string;
  powerKw: number | null;
  nominalEnergyKwh: number | null;
  projectedMinC: number | null;
  horizonHours: number;
  segmentCount: number;
  segments: { start: number; end: number }[];
  truncated: boolean;
  qualified: false;
  commandsSent: 0;
}
export interface LiveTelemetry {
  coast: CoastSummary;
  sources: SourceSummary;
  plan: VirtualPlanSummary;
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
  returnC: number | null;
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
function number(
  state: LiveState | undefined,
  unit: string,
  max: number,
  min = 0,
) {
  if (!state || state.attributes.unit_of_measurement !== unit) return null;
  const value = Number(state.state);
  return state.state.trim() !== "" &&
    Number.isFinite(value) &&
    value >= min &&
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

export interface NativeOverview {
  version: [2, 0];
  seq: number;
  boot_id: string;
  owner_epoch: number;
  settings: {
    revision: number;
    values: Record<string, string | number>;
    manual_pause: boolean;
    energy_fault: string | null;
    counter: number | null;
    model_frozen: boolean;
  };
  safety: {
    voltage_status: string;
    reason: string;
    ages: Record<string, number | null>;
  };
  controller: { mode: string; reason: string; actual_commands: number };
  model: {
    parameters: Record<string, number> | null;
    qualification: string;
    frozen: boolean;
  };
  one_shot: { state: string; expires: number | null };
  plan: {
    trajectory?: Point[];
    horizon_hours?: number;
    status?: string;
    reason?: string;
  } | null;
  fan: { percentage_proposed?: number | null; reason?: string } | null;
  journal: {
    revision: number;
    fenced: boolean;
    commands: Record<string, { stage: string }>;
  };
  active_limit: {
    band: string;
    target: number | null;
    upper: number | null;
    ceiling: number | null;
  };
  physical_commands_enabled: false;
  fault: string | null;
}
export interface NativeHistory {
  actual: Point[];
  energy: { start: number; end: number; kwh: number; category: string }[];
  original: unknown;
  original_status: string;
  source: string;
  truncated: boolean;
}

export class LiveHAAPI implements OperatorAPI {
  readonly native = true;
  readonly live = true;
  readonly session = Object.freeze({ role: "read_only_live" });
  readonly feed = new SnapshotFeed(blank());
  readonly model = { revision: 0, candidate: false, frozen: true };
  readonly view = emptyView(Date.now() / 1000);
  get dataErrors() {
    return this.backend
      ? []
      : [
          "Native backend ще не підтверджено; жодних демоданих або прав керування.",
        ];
  }
  readonly scenario = undefined;
  backend: NativeOverview | null = null;
  backendError: string | null = null;
  private nativeFlight = false;
  private closed = false;
  private currentHass: LiveHass;
  async nativeRequest(
    operation: string,
    payload: Record<string, unknown> = {},
  ): Promise<unknown> {
    if (
      this.closed ||
      !this.entryId ||
      !this.currentHass.callWS ||
      this.currentHass.connected === false
    )
      throw Error("Native backend недоступний");
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([
        this.currentHass.callWS({
          type: "heating_ai_v2/backend",
          entry_id: this.entryId,
          version: [2, 0],
          operation,
          payload,
        }),
        new Promise<never>((_, reject) => {
          timer = setTimeout(
            () =>
              reject(
                Error("Native backend timeout: результат не підтверджений"),
              ),
            8000,
          );
        }),
      ]);
    } finally {
      if (timer) clearTimeout(timer);
    }
  }
  async refreshBackend() {
    if (this.nativeFlight || this.closed || !this.entryId) return;
    this.nativeFlight = true;
    try {
      const result = await this.nativeRequest("snapshot");
      if (!result || typeof result !== "object")
        throw Error("Invalid native snapshot");
      const data = result as Partial<NativeOverview>;
      if (
        data.version?.join(".") !== "2.0" ||
        typeof data.seq !== "number" ||
        !data.settings ||
        !data.safety ||
        !data.controller ||
        !data.boot_id ||
        data.physical_commands_enabled !== false
      )
        throw Error("Invalid native contract");
      if (!this.closed) {
        this.backend = data as NativeOverview;
        this.backendError = null;
      }
    } catch {
      if (!this.closed)
        this.backendError =
          "Native backend недоступний — запис і керування заблоковані";
    } finally {
      this.nativeFlight = false;
      if (!this.closed)
        this.feed.reset({ ...this.feed.value, seq: this.feed.value.seq + 1 });
    }
  }
  get canWriteNative() {
    return (
      !!this.backend &&
      !this.backend.fault &&
      !this.backendError &&
      this.currentHass.user?.is_admin === true &&
      this.currentHass.connected !== false
    );
  }
  async mutateNative(
    operation: string,
    values: Record<string, string | number>,
    expected: number,
  ) {
    const backend = this.backend;
    if (!backend || !this.canWriteNative) throw Error("Запис недоступний");
    const result = await this.nativeRequest(operation, {
      values,
      expected_revision: expected,
      request_id: crypto.randomUUID(),
      boot_id: backend.boot_id,
      owner_epoch: backend.owner_epoch,
    });
    if (!result || typeof result !== "object" || !("status" in result))
      throw Error("Невалідна відповідь");
    await this.refreshBackend();
    return String(result.status);
  }
  async nativeHistory(range: Window): Promise<NativeHistory> {
    const data = await this.nativeRequest("history", { ...range });
    if (
      !data ||
      typeof data !== "object" ||
      !("actual" in data) ||
      !("energy" in data)
    )
      throw Error("Invalid archive response");
    return data as NativeHistory;
  }
  close() {
    this.closed = true;
  }

  telemetry: LiveTelemetry = {
    origin: "ha_last_known",
    plan: {
      status: "BLOCKED_INPUTS",
      reason: "planner_not_ready",
      powerKw: null,
      nominalEnergyKwh: null,
      projectedMinC: null,
      horizonHours: 0,
      segmentCount: 0,
      segments: [],
      truncated: false,
      qualified: false,
      commandsSent: 0,
    },
    coast: {
      status: "UNAVAILABLE",
      min: null,
      end: null,
      hours: 0,
      qualified: false,
    },
    sources: {
      weatherStatus: "UNKNOWN",
      weatherHours: 0,
      weatherHorizonEnd: null,
      weatherIssuedKnown: false,
      outageStatus: "UNKNOWN",
      nextOutageAt: null,
      outagesUpcomingCount: 0,
      gridForecastQualified: false,
    },
    room: null,
    thermostatMode: null,
    thermostatSetpoint: null,
    grid: null,
    voltages: [null, null, null],
    kws: [null, null, null],
    kwsTotal: null,
    kwsEnergy: null,
    lastReported: {},
    returnC: null,
    fireplaceC: null,
    fireplaceDeltaC: null,
    fanActual: null,
    fanPercent: null,
    fanMode: null,
    fanSpeeds: [null, null, null],
    fanBackupVerified: null,
    fanControlEnabled: null,
    ventilation: { recuperator: null, bath: null },
  };
  constructor(
    private readonly bindings: LiveBindings,
    hass: LiveHass,
    private readonly entryId?: string,
  ) {
    if (
      roles.some((role) => typeof bindings[role] !== "string") ||
      Object.keys(bindings).some(
        (role) =>
          ![...roles, ...optionalRoles].includes(role as keyof LiveBindings),
      ) ||
      new Set(Object.values(bindings)).size !== Object.keys(bindings).length ||
      roles.some(
        (role) =>
          typeof bindings[role] !== "string" || !bindings[role].includes("."),
      )
    ) {
      throw Error("Невалідна прив'язка до реальних сутностей HA");
    }
    this.currentHass = hass;
    this.updateHass(hass);
  }
  async loadRoomHistory(scope: { start: number; end: number }) {
    return fetchRoomRecorder(this.currentHass, this.bindings.room, scope);
  }
  updateHass(hass: LiveHass) {
    this.currentHass = hass;
    const s = (role: keyof LiveBindings) => {
      const entityId = this.bindings[role];
      return entityId ? hass.states?.[entityId] : undefined;
    };
    const stamp = (state?: LiveState) =>
      state?.last_reported ?? state?.last_changed ?? null;
    const now = Date.now() / 1000;
    const room = number(s("room"), "°C", 65, -30);
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
    const returnC = number(s("return_probe"), "°C", 110, -30);
    const fireplaceC = number(s("fireplace"), "°C", 65, -30);
    const fanActualRaw = s("circulation")?.state;
    const fanActual =
      fanActualRaw === "on" || fanActualRaw === "off" ? fanActualRaw : null;
    const fanPctRaw = s("circulation")?.attributes.percentage;
    const fanPercent =
      typeof fanPctRaw === "number" &&
      Number.isFinite(fanPctRaw) &&
      fanPctRaw >= 0 &&
      fanPctRaw <= 100
        ? fanPctRaw
        : null;
    const fanMode = s("fan_mode")?.state ?? null;
    const fanSpeeds = (
      ["fan_night", "fan_standard", "fan_intense"] as const
    ).map((role) => number(s(role), "%", 100));
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
    const statusAttrs = this.entryId
      ? Object.values(hass.states ?? {}).find(
          (v) => v?.attributes.v2_entry_id === this.entryId,
        )?.attributes
      : undefined;
    const summary = statusAttrs?.provider_summary ?? null;
    const p =
      summary && typeof summary === "object" && !Array.isArray(summary)
        ? (summary as Record<string, unknown>)
        : {};
    const safeCount = (x: unknown) =>
      typeof x === "number" && Number.isInteger(x) && x >= 0 && x <= 72 ? x : 0;
    const safeTime = (x: unknown) =>
      typeof x === "number" && Number.isFinite(x) && x > 0 ? x : null;
    const coastRaw = statusAttrs?.coast_preview ?? null;
    const coastValue =
      coastRaw && typeof coastRaw === "object" && !Array.isArray(coastRaw)
        ? (coastRaw as Record<string, unknown>)
        : {};
    const coastNumber = (x: unknown) =>
      typeof x === "number" && Number.isFinite(x) ? x : null;
    const coast: CoastSummary = {
      status:
        coastValue.status === "UNQUALIFIED_CONDITIONAL_COAST"
          ? "UNQUALIFIED_CONDITIONAL_COAST"
          : "UNAVAILABLE",
      min: coastNumber(coastValue.temperature_min_c),
      end: coastNumber(coastValue.temperature_end_c),
      hours: coastNumber(coastValue.hours_covered) ?? 0,
      qualified: false,
    };
    const candidate = statusAttrs?.virtual_plan;
    const planRaw =
      candidate && typeof candidate === "object" && !Array.isArray(candidate)
        ? (candidate as Record<string, unknown>)
        : {};
    const segmentsRaw = planRaw.segments;
    const segments = Array.isArray(segmentsRaw)
      ? segmentsRaw.slice(0, 12).flatMap((item) => {
          if (!item || typeof item !== "object") return [];
          const v = item as Record<string, unknown>;
          return typeof v.start === "number" &&
            typeof v.end === "number" &&
            Number.isFinite(v.start) &&
            Number.isFinite(v.end) &&
            v.start > 0 &&
            v.end > v.start &&
            v.conditional === true
            ? [{ start: v.start, end: v.end }]
            : [];
        })
      : [];
    const planStatus =
      planRaw.status === "VIRTUAL_CONDITIONAL"
        ? "VIRTUAL_CONDITIONAL"
        : "BLOCKED_INPUTS";
    const plan: VirtualPlanSummary = {
      status: planStatus,
      reason:
        typeof planRaw.reason === "string" && planRaw.reason.length < 128
          ? planRaw.reason
          : "planner_unavailable",
      powerKw: coastNumber(planRaw.scenario_power_kw),
      nominalEnergyKwh: coastNumber(planRaw.nominal_energy_kwh),
      projectedMinC: coastNumber(planRaw.projected_min_c),
      horizonHours: coastNumber(planRaw.horizon_hours) ?? 0,
      segmentCount:
        typeof planRaw.segment_count === "number" &&
        Number.isInteger(planRaw.segment_count) &&
        planRaw.segment_count >= 0 &&
        planRaw.segment_count <= 256
          ? planRaw.segment_count
          : 0,
      segments: planStatus === "VIRTUAL_CONDITIONAL" ? segments : [],
      truncated: planRaw.segments_truncated === true,
      qualified: false,
      commandsSent: 0,
    };
    const sources: SourceSummary = {
      weatherStatus:
        p.weather_status === "RECEIVED_ISSUED_UNKNOWN"
          ? "RECEIVED_ISSUED_UNKNOWN"
          : "UNKNOWN",
      weatherHours: safeCount(p.weather_hours_count),
      weatherHorizonEnd: safeTime(p.weather_horizon_end),
      weatherIssuedKnown: false,
      outageStatus:
        p.outage_status === "OUTAGE_EVENTS_ONLY"
          ? "OUTAGE_EVENTS_ONLY"
          : "UNKNOWN",
      nextOutageAt: safeTime(p.next_outage_at),
      outagesUpcomingCount: safeCount(p.outages_upcoming_count),
      gridForecastQualified: false,
    };
    this.telemetry = {
      origin: "ha_last_known",
      sources,
      coast,
      plan,
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
      returnC,
      fireplaceC,
      fireplaceDeltaC:
        fireplaceC !== null && room !== null
          ? Math.round((fireplaceC - room) * 100) / 100
          : null,
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
    void this.refreshBackend();
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
