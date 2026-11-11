export type Window = Readonly<{ start: number; end: number }>;
export type Action = "heat" | "stop_demand";
export type Quality =
  "valid" | "estimated" | "stale" | "missing" | "conflicting";
export interface StatusView {
  status_seq: number;
  boot_id: string;
  owner_epoch: number;
  actual: Action | null;
  desired: Action;
  mode: string;
  snapshot_id: string;
  snapshot_at: number;
  archive_pending: number;
  archive_lost: number;
  receipt_stage: string | null;
  physical_verified: false;
}
export interface APIReceipt {
  request_id: string;
  status:
    | "saved"
    | "denied"
    | "conflict"
    | "unavailable"
    | "accepted_fake"
    | "observed_fake";
  revision: number;
  persisted_revision: number | null;
  reason: string;
}
export interface Envelope<T> {
  version: [2, 0];
  type: string;
  data: T;
}
export interface VoltageSettings {
  min_voltage_v: number;
  max_voltage_v: number;
  hysteresis_v: number;
  stable_recovery_s: number;
  voltage_max_age_s: number;
}
export interface Settings extends Partial<VoltageSettings> {
  day: number;
  night: number;
  budget: number;
  windowStart: string;
  windowEnd: string;
  strategy: "comfort" | "balanced" | "economy";
  mode: "auto" | "observation";
  circulation: "auto" | "manual" | "stop";
  fan: number;
  scenario: 3 | 6 | 9;
  freshness: number;
  aiAdvice: boolean;
}
export interface Persisted {
  revision: number;
  values: Settings;
  lastRequest: string | null;
}
export interface Point {
  at: number;
  value: number | null;
  quality?: Quality;
  // Qualified historical coverage, not the operational freshness threshold.
  coverage?: { source: string; from: number };
  gap?: { start: number; end: number; seconds: number; count: number };
}
export interface ForecastProof {
  reference: number;
  issued: number;
  received: number;
  coverage: Window;
  frozen: boolean;
}
export interface Forecast extends ForecastProof {
  id: string;
  model: number;
  plan: string;
  source: string;
  points: readonly Point[];
  energy: number | null;
  scope: Window | null;
}
export interface Energy {
  actualUntil?: number;
  reference: number | null;
  known: number;
  estimated: number | null;
  unknownS: number;
  scope: Window | null;
  projected: number | null;
}
export interface EnergyInterval {
  start: number;
  end: number;
  kwh: number | null;
  category: "confirmed" | "derived" | "estimated" | "recovered" | "unknown";
  price: number | null;
  method?: "counter_difference" | "integrated_power" | "prorated_estimate";
  tariffs?: readonly { start: number; end: number; price: number }[];
}
export type Priority = "safety" | "manual" | "quality" | "comfort" | "budget";
export interface Notice {
  priority: Priority;
  text: string;
}
export type Scenario =
  | "normal"
  | "heating"
  | "device-stop"
  | "zero"
  | "stale"
  | "missing"
  | "offline"
  | "safety"
  | "manual"
  | "grid-off"
  | "false-ack"
  | "overspend"
  | "missing-original"
  | "anomaly"
  | "fire"
  | "empty"
  | "dense-history"
  | "energy-error"
  | "temperature-error"
  | "future-history"
  | "revoked"
  | "recovering"
  | "long-copy";
export type VoltageStatus =
  "LOW" | "HIGH" | "MISSING_OR_STALE" | "STABILIZING" | "NORMAL";
export type Phase = "L1" | "L2" | "L3";
export interface VoltageView {
  status: VoltageStatus;
  eligible: boolean;
  affected_phases: Phase[];
  reason: string;
  ages: Record<Phase, number | null>;
  phases: {
    phase: Phase;
    voltage_v: number | null;
    age_s: number | null;
    online: boolean | null;
    qualified: boolean;
  }[];
  limits: VoltageSettings;
  source_role: "grid_input_voltage";
  source_provider: "zigbee2mqtt_input220";
  physical_authority: false;
  scope: "synthetic_only";
}
export interface PowerView {
  source_role: "boiler_power_energy";
  source_provider: "tuya_local_kws";
  cloud_duplicate_policy: "excluded_no_fallback";
  stage: "OFF" | "PUMP_ONLY" | "~3kW" | "~6kW" | "~9kW" | "UNKNOWN";
  total_active_w: number | null;
  total_imported_kwh: number | null;
  phases: { phase: Phase; active_w: number | null; age_s: number | null }[];
  reason: string;
  physical_authority: false;
  physical_heat: null;
  scope: "synthetic_only";
}
export interface Snapshot {
  system_health?: SystemHealthView;
  power?: PowerView;
  voltage?: VoltageView;
  demand_eligible?: boolean;
  version: 1;
  seq: number;
  generation: number;
  now: number;
  connected: boolean;
  permitted: boolean;
  status: StatusView;
  room: { value: number | null; observed: number; quality: Quality };
  grid: boolean | null;
  notices: Notice[];
  fan: {
    phase: string;
    requested: number | null;
    actual: number | null;
    night: boolean;
    fire: boolean;
  };
  oneShot: {
    state:
      | "inactive"
      | "armed"
      | "cancelled"
      | "expired"
      | "consumed"
      | "unknown_outcome";
    expires: number | null;
    gridEpoch: number;
  };
  diagnostics: {
    loopLagMs: number | null;
    persistence: string;
    worker: string;
    source: string;
  };
}
export interface HistoryCursor {
  offset: number;
  scope: string;
  watermark: number;
}
export interface HistoryPage {
  rows: readonly Point[];
  cursor: HistoryCursor | null;
  watermark: number;
}
export interface ModelMetric {
  hours: number;
  days: number;
  samples: number;
  mae: number | null;
  p90: number | null;
  qualified: boolean;
}

export interface Track {
  start: number;
  end: number;
  kind: "heat" | "outage" | "fire";
}

export interface SourceFreshnessView {
  activity_provenance?: "ha_state_write" | "synthetic_raw_report" | "unknown";
  measurement_authorization_age_s?: number;
  recovery_dwell_s?: number;
  recovery_policy_ready?: boolean;
  physical_commands_enabled?: false;
  living_device_last_activity: number | null;
  living_temperature_last_observed: number | null;
  return_water_last_observed: number | null;
  device_age_s: number | null;
  temperature_age_s: number | null;
  return_age_s: number | null;
  activity_window_s: number;
  device_quality: "OK" | "UNKNOWN" | "DEGRADED";
  temperature_quality: "OK" | "UNKNOWN" | "STALE" | "OFFLINE";
  return_quality: "OK" | "UNKNOWN" | "STALE";
  return_veto: boolean;
  failure_confirmed: boolean;
  physical_authority: false;
  scope: "synthetic_only";
}
export interface SystemHealthView {
  passive_sources?: readonly {
    role: "temperature" | "humidity" | "return_water";
    value: number | null;
    last_reported: number;
    last_updated: number;
    last_changed: number;
    available: boolean;
    origin: "ha_state_write";
    physical_measurement: "BLOCKED";
    physical_commands_enabled: false;
  }[];
  source_freshness?: SourceFreshnessView;
  components: readonly {
    key: string;
    label: string;
    status: "OK" | "PROBLEM" | "WAITING";
    reason: string;
    age_s: number | null;
    severity: string;
    checked_at: number;
    last_transition: number;
    physical_verified: false;
    fallback_action: string;
  }[];
  mode: string;
  notification: string | null;
  physical_verified: false;
  semantics: "proposed_only_no_device_ack";
  last_notice?: string | null;
  proposal?: {
    id: string;
    mode?: "AUTO" | "HEAT";
    action: string;
    stage: "proposed";
    physical_authority: false;
  } | null;
}
