import { useState } from "react";
import type { Point, Window, Track } from "./types";
import { decimate, segments, time, fmt, dateTime } from "./domain";
export interface ChartProps {
  actual: readonly Point[];
  forecast?: readonly Point[];
  original?: readonly Point[];
  scope: Window;
  now: number;
  unit?: string;
  label: string;
  comfort?: boolean;
  tracks?: boolean;
  events?: readonly Track[];
  initialLatest?: boolean;
  forecastLabel?: string;
}
export function Chart({
  actual: inputActual,
  forecast = [],
  original = [],
  scope,
  now,
  unit = "°C",
  label,
  comfort = true,
  tracks = true,
  events = [],
  initialLatest = true,
  forecastLabel = "Поточний прогноз",
}: ChartProps) {
  const actual = inputActual.map((p) =>
    p.quality && p.quality !== "valid" ? { ...p, value: null } : p,
  );
  const [cursor, setCursor] = useState<number | null>(null);
  const [showLatest, setLatest] = useState(initialLatest);
  const [showTracks, setTracks] = useState(tracks);
  const [tableLimit, setTableLimit] = useState(24);
  const values = [...actual, ...forecast, ...original]
    .filter((p) => p.value !== null && p.at >= scope.start && p.at <= scope.end)
    .map((p) => p.value ?? 0);
  const min = unit === "°C" ? Math.min(19, ...values) - 0.2 : 0;
  const max =
    unit === "°C"
      ? Math.max(23, ...values) + 0.2
      : Math.max(1, ...values) * 1.1;
  const x = (at: number) =>
    48 + ((at - scope.start) / (scope.end - scope.start)) * 800;
  const y = (v: number) => 202 - ((v - min) / (max - min)) * 170;
  const points = actual.filter((p) => p.at >= scope.start && p.at <= scope.end);
  const cursorPoints = [
    ...new Set(
      [...points, ...original, ...forecast]
        .filter((p) => p.at >= scope.start && p.at <= scope.end)
        .map((p) => p.at),
    ),
  ]
    .sort((a, b) => a - b)
    .map((at) => ({
      at,
      value: points.find((p) => p.at === at)?.value ?? null,
    }));
  const selected = cursor === null ? null : cursorPoints[cursor];
  const curves = (series: readonly Point[], name: string) =>
    segments(
      decimate(series.filter((p) => p.at >= scope.start && p.at <= scope.end)),
      name === "actual",
    ).map((run, i) => (
      <g key={`${name}-${i}`}>
        <path
          className={`curve ${name}`}
          d={run
            .map(
              (p, j) =>
                `${j ? "L" : "M"}${x(p.at).toFixed(2)},${y(p.value ?? 0).toFixed(2)}`,
            )
            .join(" ")}
          data-series={name}
        />
        {run.length === 1 && (
          <circle
            cx={x(run[0]!.at)}
            cy={y(run[0]!.value!)}
            r="2.5"
            className={`sample ${name}`}
          />
        )}
      </g>
    ));
  return (
    <div className="chart-wrap">
      <div className="chart-legend">
        <span>
          <i className="line actual" />
          Факт
        </span>
        {original.length > 0 && (
          <span>
            <i className="line original" />
            Завчасний
          </span>
        )}
        <button
          aria-pressed={showLatest}
          onClick={() => setLatest(!showLatest)}
        >
          <i className="line latest" />
          {forecastLabel}
        </button>
        {tracks && (
          <button
            aria-pressed={showTracks}
            onClick={() => setTracks(!showTracks)}
          >
            План / події
          </button>
        )}
      </div>
      <svg
        className="chart"
        viewBox="0 0 880 255"
        role="img"
        aria-label={`${label}. ${unit}. Прогалини факту не з’єднано. Значення доступні в таблиці.`}
        onPointerDown={(e) => {
          if (!cursorPoints.length) return;
          const rect = e.currentTarget.getBoundingClientRect();
          const at =
            scope.start +
            ((((e.clientX - rect.left) / rect.width) * 880 - 48) / 800) *
              (scope.end - scope.start);
          let nearest = 0;
          cursorPoints.forEach((p, i) => {
            if (
              Math.abs(p.at - at) <
              Math.abs((cursorPoints[nearest]?.at ?? at) - at)
            )
              nearest = i;
          });
          setCursor(nearest);
        }}
      >
        {comfort && unit === "°C" && (
          <rect
            x="48"
            width="800"
            y={y(22)}
            height={y(20.5) - y(22)}
            className="comfort-band"
          />
        )}
        {[0, 1, 2, 3].map((i) => {
          const v = min + ((max - min) * i) / 3;
          return (
            <g key={i}>
              <line
                x1="48"
                x2="848"
                y1={y(v)}
                y2={y(v)}
                className="grid-line"
              />
              <text x="4" y={y(v) + 4}>
                {fmt(v, 1)}
              </text>
            </g>
          );
        })}
        {curves(actual, "actual")}
        {curves(original, "original")}
        {showLatest && curves(forecast, "latest")}
        {now >= scope.start && now <= scope.end && (
          <g>
            <line
              x1={x(now)}
              x2={x(now)}
              y1="20"
              y2="220"
              className="now-line"
            />
            <text x={x(now) + 8} y="18">
              Зараз
            </text>
          </g>
        )}
        {[0, 1, 2, 3, 4].map((i) => (
          <text
            key={i}
            x={48 + 200 * i}
            y="248"
            textAnchor={i === 4 ? "end" : "start"}
          >
            {time(scope.start + ((scope.end - scope.start) * i) / 4)}
          </text>
        ))}
        {tracks && showTracks && (
          <g aria-label="Синтетичні вікна нагріву, відключень і каміна">
            {events
              .filter((e) => e.start < scope.end && e.end > scope.start)
              .map((e, i) => (
                <path
                  key={i}
                  className={
                    e.kind === "outage" ? "outage-track" : "heat-track"
                  }
                  data-kind={e.kind}
                  d={`M${x(Math.max(e.start, scope.start))} ${e.kind === "heat" ? 216 : e.kind === "outage" ? 226 : 236}H${x(Math.min(e.end, scope.end))}`}
                />
              ))}
            <text x="28" y="220">
              Н
            </text>
            <text x="28" y="230">
              Е
            </text>
            <text x="28" y="240">
              К
            </text>
          </g>
        )}
        {selected && selected.value !== null && (
          <circle
            cx={x(selected.at)}
            cy={y(selected.value)}
            r="5"
            className="cursor-point"
          />
        )}
      </svg>
      {cursorPoints.length > 0 && (
        <label className="chart-cursor">
          Час на графіку
          <input
            aria-label={`Час: ${label}`}
            type="range"
            min="0"
            max={cursorPoints.length - 1}
            value={cursor ?? 0}
            onChange={(e) => setCursor(Number(e.target.value))}
          />
        </label>
      )}
      <p className="chart-readout" aria-live="polite">
        {selected
          ? `${dateTime(selected.at)} · Факт ${fmt(selected.value)} ${unit}${gapText(points.find((p) => p.at === selected.at))} · Завчасний ${fmt(original.find((p) => p.at === selected.at)?.value ?? null)} · ${forecastLabel} ${showLatest ? fmt(forecast.find((p) => p.at === selected.at)?.value ?? null) : "приховано"}`
          : `${unit} · Факт із прогалинами · план умовний`}
      </p>
      <details className="chart-table">
        <summary>Таблиця значень · без кольору</summary>
        <div className="table-scroll">
          <table>
            <caption>
              {label} · Europe/Kyiv · {unit}
            </caption>
            <thead>
              <tr>
                <th scope="col">Час</th>
                <th scope="col">Факт</th>
                <th scope="col">Завчасний</th>
                <th scope="col">{forecastLabel}</th>
              </tr>
            </thead>
            <tbody>
              {[
                ...new Set(
                  [...points, ...original, ...forecast]
                    .filter((p) => p.at >= scope.start && p.at <= scope.end)
                    .map((p) => p.at),
                ),
              ]
                .sort((a, b) => a - b)
                .slice(0, tableLimit)
                .map((at) => (
                  <tr key={at}>
                    <th scope="row">{dateTime(at)}</th>
                    <td>
                      {fmt(points.find((p) => p.at === at)?.value ?? null)}
                      {gapText(points.find((p) => p.at === at))}
                    </td>
                    <td>
                      {fmt(original.find((p) => p.at === at)?.value ?? null)}
                    </td>
                    <td>
                      {fmt(forecast.find((p) => p.at === at)?.value ?? null)}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        {tracks && (
          <ul>
            {events
              .filter((e) => e.start < scope.end && e.end > scope.start)
              .map((e, i) => (
                <li key={i}>
                  {e.kind === "heat"
                    ? "Н · план нагріву"
                    : e.kind === "outage"
                      ? "Е · умовне відключення"
                      : "К · синтетичний камін"}
                  : {dateTime(e.start)}–{dateTime(e.end)}
                </li>
              ))}
          </ul>
        )}
        <button
          onClick={() => setTableLimit((v) => Math.min(4096, v + 128))}
          disabled={tableLimit >= 4096}
        >
          Ще128 рядків
        </button>
      </details>
    </div>
  );
}

function gapText(point?: Point): string {
  return point?.gap
    ? ` · немає доказів покриття ${dateTime(point.gap.start)}–${dateTime(point.gap.end)} (${fmt(point.gap.seconds / 60, 0)} хв)`
    : "";
}
