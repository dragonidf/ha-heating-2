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
export interface Settings {
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
export interface Snapshot {
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
