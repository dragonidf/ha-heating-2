/** Bounded, authenticated read-only HA Recorder history. No synthetic fixtures. */
import type { Point } from "./types";

export interface RecorderHass {
  callWS?: (message: Record<string, unknown>) => Promise<unknown>;
}

const MAX_ROWS = 4096;
const MAX_DAYS = 30;
const MAX_GAP_S = 5400;

function rowTime(row: Record<string, unknown>): number | null {
  const raw = row.lu ?? row.lc ?? row.last_updated;
  const value =
    typeof raw === "number"
      ? raw
      : typeof raw === "string"
        ? Date.parse(raw) / 1000
        : NaN;
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function recorderPoints(
  response: unknown,
  entityId: string,
  scope: { start: number; end: number },
): Point[] {
  if (
    !response ||
    typeof response !== "object" ||
    Array.isArray(response) ||
    !Number.isFinite(scope.start) ||
    !Number.isFinite(scope.end) ||
    scope.start >= scope.end
  )
    throw Error("Невірна відповідь історії Home Assistant");
  const rows = (response as Record<string, unknown>)[entityId];
  if (rows === undefined) return [];
  if (!Array.isArray(rows) || rows.length > MAX_ROWS)
    throw Error("Забагато точок — оберіть коротший період");

  const raw: Point[] = [];
  for (const item of rows) {
    if (!item || typeof item !== "object" || Array.isArray(item))
      throw Error("Некоректний запис історії");
    const record = item as Record<string, unknown>;
    const at = rowTime(record);
    if (at === null || at < scope.start || at > scope.end) continue;
    const state = record.s ?? record.state;
    const parsed =
      typeof state === "string" && state.trim() !== "" ? Number(state) : NaN;
    const value =
      Number.isFinite(parsed) && parsed >= -30 && parsed <= 65 ? parsed : null;
    raw.push({ at, value });
  }
  raw.sort((a, b) => a.at - b.at);

  const points: Point[] = [];
  let previous: Point | undefined;
  for (const point of raw) {
    if (previous && point.at === previous.at) {
      points[points.length - 1] = point;
      previous = point;
      continue;
    }
    const continuous =
      previous?.value !== null &&
      previous?.value !== undefined &&
      point.value !== null &&
      point.at - previous.at <= MAX_GAP_S;
    points.push({
      ...point,
      coverage:
        point.value !== null
          ? {
              source: "ha_recorder_states_not_raw_samples",
              from: continuous ? previous!.at : point.at,
            }
          : undefined,
    });
    previous = point;
  }
  return points;
}

export async function fetchRoomRecorder(
  hass: RecorderHass,
  entityId: string,
  scope: { start: number; end: number },
): Promise<Point[]> {
  if (!hass.callWS) throw Error("Історія Recorder недоступна через HA");
  if (
    !entityId.startsWith("sensor.") ||
    ![scope.start, scope.end].every(Number.isFinite) ||
    scope.end <= scope.start ||
    scope.end > Date.now() / 1000 + 2 ||
    scope.end - scope.start > MAX_DAYS * 86400 + 93600
  )
    throw Error("Некоректний або завеликий період історії");
  const response = await hass.callWS({
    type: "history/history_during_period",
    start_time: new Date(scope.start * 1000).toISOString(),
    end_time: new Date(scope.end * 1000).toISOString(),
    entity_ids: [entityId],
    significant_changes_only: true,
    include_start_time_state: true,
    minimal_response: true,
    no_attributes: true,
  });
  return recorderPoints(response, entityId, scope);
}
