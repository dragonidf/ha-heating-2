import * as fixtures from "./fixtures";
import type { SnapshotFeed } from "./mock";
import type {
  APIReceipt,
  Energy,
  EnergyInterval,
  Forecast,
  HistoryCursor,
  HistoryPage,
  ModelMetric,
  Persisted,
  Point,
  Scenario,
  Settings,
  Track,
  Window,
} from "./types";
export type Control =
  "pause" | "resume" | "arm" | "cancel" | "expire" | "unknown" | "consume";
export type ModelAction = "train" | "promote" | "rollback" | "freeze";
export interface OperatorView {
  actual: readonly Point[];
  original: Forecast | null;
  latest: readonly Point[];
  cycleEnergy: Energy;
  timeline: readonly Track[];
  metrics: readonly ModelMetric[];
}
export interface OperatorAPI {
  readonly native?: boolean;
  readonly dataErrors?: readonly string[];
  readonly session: object;
  readonly feed: SnapshotFeed;
  readonly scenario?: Scenario;
  readonly view?: OperatorView;
  model: { revision: number; candidate: boolean; frozen: boolean };
  canChange(): boolean;
  canStop?(): boolean;
  settings(): Promise<Persisted>;
  requestId(): string;
  save(
    id: string,
    expected: number,
    values: Settings,
    session: object,
  ): Promise<APIReceipt>;
  control(kind: Control, session: object): APIReceipt | Promise<APIReceipt>;
  modelAction(kind: ModelAction, session: object): string | Promise<string>;
  history(
    range: Window,
    cursor?: HistoryCursor | null,
    limit?: number,
  ): HistoryPage;
  loadHistory?(range: Window): Promise<void>;
  energyHistory(): readonly EnergyInterval[];
  reconnect(): void | Promise<void>;
}

export function emptyView(now: number): OperatorView {
  return {
    actual: [],
    original: null,
    latest: [],
    timeline: [],
    metrics: [],
    cycleEnergy: {
      reference: null,
      known: 0,
      estimated: null,
      unknownS: 86400,
      scope: { start: now - 86400, end: now },
      projected: null,
    },
  };
}
export function operatorView(api: OperatorAPI): OperatorView {
  return api.view ?? (api.native ? emptyView(api.feed.value.now) : fixtures);
}
