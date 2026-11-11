import { describe, expect, it, vi } from "vitest";
import { fetchRoomRecorder, recorderPoints } from "../src/liveRecorder";

const entity = "sensor.room";
const scope = { start: 1_700_000_000, end: 1_700_100_000 };
const sample = (s: string, lu: number) => ({ s, lu });

describe("HA 2026 Recorder read-only history", () => {
  it("accepts only the requested source, preserves gaps, no phantom zero", () => {
    const points = recorderPoints({
      [entity]: [
        sample("21.1", scope.start + 100),
        sample("21.2", scope.start + 310),
        sample("unavailable", scope.start + 400),
        sample("22.4", scope.start + 600),
        sample("23.1", scope.start + 7000),
      ],
      "sensor.unrelated": [sample("999", scope.start + 100)],
    }, entity, scope);
    expect(points.map((p) => p.value)).toEqual([21.1, 21.2, null, 22.4, 23.1]);
    expect(points[1]?.coverage?.from).toBe(points[0]?.at);
    expect(points[3]?.coverage?.from).toBe(points[3]?.at);
    expect(points[4]?.coverage?.from).toBe(points[4]?.at);
    expect(points.every((p) => p.at <= scope.end)).toBe(true);
  });

  it("supports ISO timestamps and ignores future/out-of-window points", () => {
    const at = scope.start + 400;
    const rows = [
      { state: "20.1", last_updated: new Date(at * 1000).toISOString() },
      { s: "21.4", lu: scope.end + 3000 },
      { s: "99", lu: at + 300 },
    ];
    const values = recorderPoints({ [entity]: rows }, entity, scope);
    expect(values.map((p) => p.value)).toEqual([20.1, null]);
  });

  it("rejects wrong response schemas and an unbounded source", () => {
    expect(() => recorderPoints([], entity, scope)).toThrow();
    expect(() => recorderPoints({ [entity]: "error" }, entity, scope)).toThrow();
    expect(() => recorderPoints({
      [entity]: Array.from({ length: 4097 }, () => sample("21", scope.start)),
    }, entity, scope)).toThrow("Забагато");
  });

  it("sends a single authenticated read-only HA request", async () => {
    const now = Date.now() / 1000;
    const window = { start: now - 86400, end: now };
    const callWS = vi.fn(async (_request: Record<string, unknown>) => ({
      [entity]: [{ s: "21.5", lu: now - 600 }],
    }));
    const points = await fetchRoomRecorder({ callWS }, entity, window);
    expect(points).toHaveLength(1);
    expect(points[0]?.value).toBe(21.5);
    expect(callWS).toHaveBeenCalledOnce();
    const request = callWS.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(request.type).toBe("history/history_during_period");
    expect(request.entity_ids).toEqual([entity]);
    expect(request.no_attributes).toBe(true);
    expect(request.significant_changes_only).toBe(true);
    expect(request).not.toHaveProperty("service");
  });

  it("fails closed when recorder unavailable or period exceeds bound", async () => {
    const now = Date.now() / 1000;
    await expect(fetchRoomRecorder({}, entity, { start: now - 1000, end: now }))
      .rejects.toThrow();
    await expect(fetchRoomRecorder({ callWS: async () => ({}) }, entity, {
      start: now - 50 * 86400, end: now,
    })).rejects.toThrow("завеликий");
  });
});
