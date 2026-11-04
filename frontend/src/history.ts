import type { HistoryCursor, HistoryPage, Point, Window } from "./types";
export const HISTORY_LIMIT = 4096;
export const RAW_LIMIT = 100_000;
const BINS = 800; // first / last / min / max / explicit-null per UTC bin.
export function connected(previous: Point, next: Point): boolean {
  return (
    previous.value !== null &&
    next.value !== null &&
    (!previous.quality || previous.quality === "valid") &&
    (!next.quality || next.quality === "valid") &&
    !!previous.coverage?.source &&
    previous.coverage.source === next.coverage?.source &&
    Number.isFinite(next.coverage.from) &&
    next.coverage.from <= previous.at &&
    next.at > previous.at
  );
}
export function qualifyCadence(
  points: readonly Point[],
  policy: { source: string; cadenceS: number; qualified: boolean },
): Point[] {
  return points.map((p, i) => {
    const previous = points[i - 1];
    const valid = (v: Point) =>
      v.value !== null && (!v.quality || v.quality === "valid");
    const from =
      previous &&
      valid(previous) &&
      valid(p) &&
      p.at > previous.at &&
      p.at - previous.at <= policy.cadenceS
        ? previous.at
        : p.at;
    const { coverage: _coverage, ...raw } = p;
    return policy.qualified &&
      policy.source &&
      Number.isFinite(policy.cadenceS) &&
      policy.cadenceS > 0 &&
      valid(p)
      ? { ...raw, coverage: { source: policy.source, from } }
      : raw;
  });
}
export function readHistory(
  read: (
    scope: Window,
    cursor: HistoryCursor | null,
    limit: number,
  ) => HistoryPage,
  scope: Window,
  now: number,
) {
  if (
    ![scope.start, scope.end, now].every(Number.isFinite) ||
    scope.start >= scope.end
  )
    throw Error("Некоректний період");
  const bins = new Map<number, Point[]>();
  let cursor: HistoryCursor | null = null,
    watermark: number | undefined;
  let count = 0,
    previous: Point | undefined,
    runStart = 0;
  let coveredS = 0,
    gapCount = 0;
  const until = Math.max(scope.start, Math.min(scope.end, now));
  function retain(p: Point) {
    const key = Math.min(
      BINS - 1,
      Math.floor(((p.at - scope.start) / (scope.end - scope.start)) * BINS),
    );
    const candidates = [...(bins.get(key) ?? []), p].sort(
      (a, b) => a.at - b.at,
    );
    const values = candidates.filter((v) => v.value !== null);
    const selected = [
      candidates[0],
      candidates.at(-1),
      candidates.find((v) => v.value === null),
      values.reduce<Point | undefined>(
        (a, b) => (!a || b.value! < a.value! ? b : a),
        undefined,
      ),
      values.reduce<Point | undefined>(
        (a, b) => (!a || b.value! > a.value! ? b : a),
        undefined,
      ),
    ];
    bins.set(key, [
      ...new Map(
        selected.filter((v): v is Point => !!v).map((v) => [v.at, v]),
      ).values(),
    ]);
  }
  do {
    const page = read(scope, cursor, 128);
    if (
      page.rows.length > 128 ||
      new TextEncoder().encode(JSON.stringify(page)).byteLength > 65536 ||
      !Number.isSafeInteger(page.watermark) ||
      page.watermark < 0 ||
      (watermark !== undefined && watermark !== page.watermark)
    )
      throw Error("Непослідовний архів");
    watermark = page.watermark;
    for (const raw of page.rows) {
      if (
        ++count > RAW_LIMIT ||
        !Number.isFinite(raw.at) ||
        raw.at < scope.start ||
        raw.at >= scope.end ||
        (previous && raw.at <= previous.at) ||
        (raw.value !== null && !Number.isFinite(raw.value))
      )
        throw Error("Некоректний або завеликий архів");
      const observation: Point =
        raw.quality && raw.quality !== "valid" ? { ...raw, value: null } : raw;
      let p: Point = { ...observation };
      if (previous && connected(previous, raw)) {
        coveredS += Math.max(
          0,
          Math.min(raw.at, until) - Math.min(previous.at, until),
        );
        p = {
          ...observation,
          coverage: { source: raw.coverage!.source, from: runStart },
        };
      } else {
        runStart = raw.at;
        if (previous && raw.at > previous.at) {
          gapCount++;
          const start = previous.at,
            end = raw.at;
          retain({
            at: start + (end - start) / 2,
            value: null,
            gap: { start, end, seconds: end - start, count: 1 },
          });
        }
        if (raw.coverage)
          p = {
            ...observation,
            coverage: { source: raw.coverage.source, from: raw.at },
          };
      }
      retain(p);
      previous = raw;
    }
    if (
      page.cursor &&
      (page.cursor.scope !== `${scope.start}:${scope.end}` ||
        page.cursor.watermark !== watermark ||
        page.cursor.offset !== (cursor?.offset ?? 0) + page.rows.length ||
        !page.rows.length)
    )
      throw Error("Курсор не просувається");
    cursor = page.cursor;
  } while (cursor);
  const rows = [...bins.values()].flat().sort((a, b) => a.at - b.at);
  return {
    rows,
    rawCount: count,
    watermark,
    unknownS: Math.max(0, until - scope.start - coveredS),
    gapCount,
  };
}
