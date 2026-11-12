/** Heating AI 2.0 timeline: HA Recorder fact and explicitly conditional planner, never simulated data. */
import { useEffect, useMemo, useState } from "react";
import type { Point, Snapshot } from "./types";
import type { LiveHAAPI } from "./liveHA";

const HOUR = 3600;
const HISTORY_HOURS = 6;
const FUTURE_HOURS = 24;
const WIDTH = 920;
const LEFT = 54;
const RIGHT = 906;
const TOP = 26;
const BOTTOM = 252;
const kyiv = new Intl.DateTimeFormat("uk-UA", {
  timeZone: "Europe/Kyiv", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const clock = (at: number) => kyiv.format(new Date(at * 1000));
const temp = (v: number | null) => v === null ? "—" : v.toFixed(1).replace(".", ",") + "°";
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function timeOfDay(raw: unknown): number | null {
  if (typeof raw !== "string" || !/^(?:[01][0-9]|2[0-3]):[0-5][0-9]:00$/.test(raw)) return null;
  return Number(raw.slice(0, 2)) * 60 + Number(raw.slice(3, 5));
}
function targetAt(at: number, values: Record<string, string | number>): number | null {
  const day = values.day_target, night = values.night_target;
  const start = timeOfDay(values.sleep_start), end = timeOfDay(values.sleep_end);
  if (!finite(day) || !finite(night) || day < 10 || day > 32 || night < 10 || night > 32 ||
      start === null || end === null) return null;
  const parts = kyiv.formatToParts(new Date(at * 1000));
  const h = Number(parts.find(p => p.type === "hour")?.value);
  const m = Number(parts.find(p => p.type === "minute")?.value);
  const minute = h * 60 + m;
  const asleep = start === end ? false : start < end
    ? minute >= start && minute < end : minute >= start || minute < end;
  return asleep ? night : day;
}
function pathPieces(points: Point[], x: (t: number) => number, y: (v: number) => number, gap: number): string[] {
  const results: string[] = [];
  let current = "";
  let previous: number | null = null;
  for (const point of points) {
    if (point.value === null || !finite(point.value)) {
      if (current) results.push(current);
      current = ""; previous = null;
      continue;
    }
    const command = previous === null || point.at - previous > gap ? "M" : "L";
    if (command === "M" && current) results.push(current);
    current = (command === "M" ? "" : current + " ") +
      command + x(point.at).toFixed(2) + " " + y(point.value).toFixed(2);
    previous = point.at;
  }
  if (current) results.push(current);
  return results;
}
function targetStep(points: Point[], x: (t: number) => number, y: (v: number) => number): string {
  let path = "";
  let previous: Point | null = null;
  for (const p of points) {
    if (p.value === null || !finite(p.value)) { previous = null; continue; }
    if (previous === null) path += "M" + x(p.at).toFixed(2) + " " + y(p.value).toFixed(2);
    else path += " H" + x(p.at).toFixed(2) + " V" + y(p.value).toFixed(2);
    previous = p;
  }
  return path;
}
function nearest(series: Point[], at: number, maxGap: number): number | null {
  let best: Point | null = null;
  let gap = maxGap;
  for (const p of series) {
    const delta = Math.abs(p.at - at);
    if (delta <= gap && p.value !== null && finite(p.value)) {
      gap = delta; best = p;
    }
  }
  return best?.value ?? null;
}

export function LiveClimateTimeline({ api, state }: { api: LiveHAAPI; state: Snapshot }) {
  const [history, setHistory] = useState<Point[]>([]);
  const [recorderError, setRecorderError] = useState(false);
  const [cursor, setCursor] = useState<number | null>(null);
  const now = state.now;
  const start = now - HISTORY_HOURS * HOUR;
  const end = now + FUTURE_HOURS * HOUR;
  useEffect(() => {
    let alive = true;
    const load = () => {
      const endAt = Date.now() / 1000;
      void api.loadRoomHistory({ start: endAt - HISTORY_HOURS * HOUR, end: endAt }).then(
        points => { if (alive) { setHistory(points); setRecorderError(false); } },
        () => { if (alive) { setHistory([]); setRecorderError(true); } },
      );
    };
    load();
    const refresh = setInterval(load, 5 * 60 * 1000);
    return () => { alive = false; clearInterval(refresh); };
  }, [api]);

  const plan = api.telemetry.plan;
  const qualifiedShape = plan.status === "VIRTUAL_CONDITIONAL" &&
    finite(plan.computedAt) && now >= plan.computedAt &&
    now - plan.computedAt <= 5400 && plan.trajectory.length >= 2;
  const coast = api.telemetry.coast;
  const coastReady = !qualifiedShape &&
    coast.status === "UNQUALIFIED_CONDITIONAL_COAST" &&
    finite(coast.computedAt) && now >= coast.computedAt &&
    now - coast.computedAt <= 5400 && coast.trajectory.length >= 2;
  const forecast = useMemo(() =>
    (qualifiedShape ? plan.trajectory : coastReady ? coast.trajectory : [])
      .filter(p => finite(p.at) && finite(p.value) && p.at >= now - 600 && p.at <= end)
      .slice(0, 300),
    [qualifiedShape, coastReady, coast.trajectory, plan.trajectory, now, end]);
  const windows = qualifiedShape ? plan.segments.filter(s => s.start < end && s.end > now) : [];
  const settings = api.backend?.settings.values ?? {};
  const desired = useMemo(() => {
    const points: Point[] = [];
    for (let t = now; t <= end; t += 5 * 60) {
      points.push({ at: t, value: targetAt(t, settings) });
    }
    return points;
  }, [now, end, settings]);

  const actual = useMemo(() => {
    const valid = history.filter(p => finite(p.at) && p.at >= start && p.at <= now);
    if (state.room.quality === "valid" && finite(state.room.value) &&
        finite(state.room.observed) && state.room.observed >= start && state.room.observed <= now &&
        !valid.some(p => p.at === state.room.observed)) {
      valid.push({ at: state.room.observed, value: state.room.value });
    }
    return valid.sort((a, b) => a.at - b.at).slice(-2048);
  }, [history, state.room, now, start]);

  const plotted = [...actual, ...forecast, ...desired].map(p => p.value)
    .filter(finite);
  const min = plotted.length ? Math.floor((Math.min(...plotted) - 0.35) * 2) / 2 : 19;
  const max = plotted.length ? Math.ceil((Math.max(...plotted) + 0.35) * 2) / 2 : 23;
  const ymin = Math.min(min, 19);
  const ymax = Math.max(max, ymin + 1);
  const x = (at: number) => LEFT + (at - start) / (end - start) * (RIGHT - LEFT);
  const y = (value: number) => BOTTOM - (value - ymin) / (ymax - ymin) * (BOTTOM - TOP);
  const nearestHeat = windows.find(w => w.end > now);
  const selectedAt = cursor ?? now;
  const atHeat = windows.some(w => w.start <= selectedAt && selectedAt < w.end);
  const lastKnown = state.room.quality === "valid" ? state.room.value : null;

  return (
    <section className="card climate-timeline" aria-label="Температура: факт і умовний план на добу">
      <div className="timeline-head">
        <div>
          <p className="eyebrow">Дім · найближчі 24 години</p>
          <h2>Температура та план нагріву</h2>
        </div>
        <span className="timeline-mode">SHADOW · без команд</span>
      </div>
      <div className="timeline-metrics">
        <div><span>Зараз</span><strong>{temp(lastKnown)}</strong></div>
        <div><span>{qualifiedShape ? "Мінімум моделі" : "Без котла · мінімум"}</span><strong>{qualifiedShape ? temp(plan.projectedMinC) : coastReady ? temp(coast.min) : "—"}</strong></div>
        <div><span>Умовний нагрів</span><strong>{nearestHeat
          ? clock(Math.max(now, nearestHeat.start)) + "–" + clock(nearestHeat.end)
          : "план не сформовано"}</strong></div>
        <div><span>Енергія сценарію</span><strong>{qualifiedShape && plan.nominalEnergyKwh !== null
          ? plan.nominalEnergyKwh.toFixed(1).replace(".", ",") + " кВт·год" : "—"}</strong></div>
      </div>
      <div className="timeline-legend" aria-label="Позначення на графіку">
        <span><i className="timeline-key key-actual" />Виміряно HA</span>
        <span><i className={qualifiedShape ? "timeline-key key-forecast" : "timeline-key key-coast"} />{qualifiedShape ? "Умовний план" : "Без котла · сценарій"}</span>
        <span><i className="timeline-key key-target" />Ціль кімнати</span>
        <span><i className="timeline-key key-heat" />Можливий нагрів</span>
      </div>
      <div className="timeline-scroll" aria-label="Графік часу, прокрутка по горизонталі">
        <svg className="timeline-svg" viewBox="0 0 920 324" role="img"
          aria-label="Минулі вимірювання HA ліворуч, тепловий сценарій і можливі інтервали нагріву праворуч. Час Europe/Kyiv."
          onPointerDown={event => {
            const rect = event.currentTarget.getBoundingClientRect();
            const px = (event.clientX - rect.left) * WIDTH / rect.width;
            const at = start + Math.min(1, Math.max(0, (px - LEFT) / (RIGHT - LEFT))) * (end - start);
            setCursor(at);
          }}>
          {[0, 1, 2, 3, 4].map(i => {
            const value = ymin + i * (ymax - ymin) / 4;
            return <g key={i}>
              <line className="timeline-grid" x1={LEFT} x2={RIGHT} y1={y(value)} y2={y(value)} />
              <text x={LEFT - 9} y={y(value) + 4} textAnchor="end">{value.toFixed(1)}</text>
            </g>;
          })}
          {windows.map((w, i) => (
            <rect key={i} className="timeline-heat"
              x={x(Math.max(now, w.start))} y={TOP} width={Math.max(0, x(Math.min(end, w.end)) - x(Math.max(now, w.start)))}
              height={BOTTOM - TOP} />
          ))}
          <line className="timeline-now" x1={x(now)} x2={x(now)} y1={TOP} y2={BOTTOM + 8} />
          <text x={x(now) + 7} y={TOP - 8} className="timeline-now-label">Зараз</text>
          <path className="timeline-path timeline-target" d={targetStep(desired, x, y)} />
          {pathPieces(actual, x, y, 5400).map((path, i) =>
            <path key={"actual" + i} className="timeline-path timeline-actual" d={path} />)}
          {actual.length > 0 && actual[actual.length - 1]!.value !== null &&
            <circle className="timeline-last-actual" cx={x(actual[actual.length - 1]!.at)}
              cy={y(actual[actual.length - 1]!.value!)} r="4" />}
          {pathPieces(forecast, x, y, 1200).map((path, i) =>
            <path key={"forecast" + i} className={qualifiedShape ? "timeline-path timeline-forecast" : "timeline-path timeline-coast"} d={path} />)}
          {cursor !== null && cursor >= start && cursor <= end &&
            <line className="timeline-cursor" x1={x(cursor)} x2={x(cursor)} y1={TOP} y2={BOTTOM} />}
          {Array.from({length: 6}, (_, i) => start + i * 6 * HOUR).map(at =>
            <text key={at} x={x(at)} y={BOTTOM + 29} textAnchor="middle">{clock(at)}</text>)}
          <text x={LEFT} y={BOTTOM + 53} textAnchor="start">−6 год · факт</text>
          <text x={RIGHT} y={BOTTOM + 53} textAnchor="end">+24 год · сценарій</text>
        </svg>
      </div>
      <label className="timeline-inspect">
        Час: <strong>{clock(selectedAt)}</strong> · Факт {temp(nearest(actual, selectedAt, 15 * 60))}
        {" · "}{qualifiedShape ? "План" : "Без котла"} {qualifiedShape || coastReady ? temp(nearest(forecast, selectedAt, 10 * 60)) : "—"}
        {" · "}Ціль {temp(targetAt(selectedAt, settings))}
        {atHeat ? " · можливий нагрів" : ""}
        <input aria-label="Переглянути час на графіку" type="range" min={start} max={end}
          step={300} value={selectedAt} onChange={e => setCursor(Number(e.target.value))} />
      </label>
      {!qualifiedShape ? <p className={coastReady ? "timeline-caveat" : "timeline-empty"} role="status">
        {coastReady
          ? "Оптимізатор не сформував допустимого плану. Пунктир — лише умовне охолодження/інерція без котла, каміна та вентиляції; не прогноз фактичних команд."
          : "Немає актуального розрахунку. Відображено лише фактичні вимірювання та підтверджені цілі."}
      </p> : <p className="timeline-caveat">
        Пунктир — умовний сценарій на старій неперевіреній моделі. Виділені вікна НЕ виконуються.
        {plan.truncated ? " Показано лише частину інтервалів." : ""}
      </p>}
      {recorderError && <p className="timeline-caveat">Історія Recorder недоступна; показано лише поточний стан HA.</p>}
    </section>
  );
}
