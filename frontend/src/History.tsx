import { useMemo, useState } from "react";
import { Card, Chart, Badge } from "./components";
import { original, latest, NOW, timeline } from "./fixtures";
import {
  kyivRange,
  shiftDate,
  originalEligible,
  fmt,
  dateTime,
} from "./domain";
import type { DemoAPI } from "./mock";
import type { Snapshot } from "./types";
import { readHistory } from "./history";
import { scopedEnergy } from "./historyEnergy";
export function History({
  api,
  state,
  onModel,
}: {
  api: DemoAPI;
  state: Snapshot;
  onModel: () => void;
}) {
  const [first, setFirst] = useState("2026-10-29"),
    [last, setLast] = useState("2026-11-04"),
    [metric, setMetric] = useState("temperature");
  let error = "",
    range = { start: NOW - 7 * 86400, end: NOW };
  try {
    range = kyivRange(first, last);
  } catch (e) {
    error = e instanceof Error ? e.message : "Некоректний період";
  }
  const history = useMemo(() => {
    try {
      return {
        ...readHistory(api.history.bind(api), range, state.now),
        error: "",
      };
    } catch (e) {
      return {
        rows: [],
        rawCount: 0,
        unknownS: 0,
        gapCount: 0,
        error: `Історію не вдалося прочитати. ${e instanceof Error ? e.message : "Помилка джерела"}. Повторіть запит або скоротіть період.`,
      };
    }
  }, [api, api.scenario, range.start, range.end, state.now]);
  const { rows } = history;
  if (history.error) error = history.error;
  const source =
    api.scenario === "missing-original"
      ? { ...original, received: original.reference - 3600 }
      : original;
  const eligible = originalEligible(source);
  const hasOriginal =
    eligible &&
    source.coverage.start < range.end &&
    source.coverage.end >= range.start;
  let energy;
  try {
    energy = scopedEnergy(api.energyHistory(), range, state.now);
  } catch {
    error = "Інтервали енергії або тарифи суперечливі. Підсумок недоступний.";
    energy = scopedEnergy([], range, state.now);
  }
  const { entries, known, estimated, unknownS, costKnown: priced } = energy;
  const energyPoints = entries.map((i) => ({
    at: i.start,
    value:
      metric === "cost"
        ? i.costKnownS > 0
          ? i.costKnown
          : null
        : i.category === "estimated"
          ? null
          : i.kwh,
  }));
  const estimatedPoints = entries.map((i) => ({
    at: i.start,
    value:
      metric === "cost"
        ? i.costEstimatedS > 0
          ? i.costEstimated
          : null
        : i.category === "estimated"
          ? i.kwh
          : null,
  }));
  const preset = (days: number) => {
    setFirst(shiftDate("2026-11-04", 1 - days));
    setLast("2026-11-04");
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Збережені виміри й порівняння</p>
          <h1>Історія</h1>
        </div>
        <button className="text-button" onClick={onModel}>
          Точність прогнозу
          <IconArrow />
        </button>
      </div>
      <Card title="Період і показник">
        <div className="range-bar">
          <div className="segmented" aria-label="Календарний період">
            <button onClick={() => preset(1)}>24 год</button>
            <button onClick={() => preset(7)}>7 днів</button>
            <button onClick={() => preset(30)}>30 днів</button>
          </div>
          <label>
            Від
            <input
              type="date"
              value={first}
              onChange={(e) => {
                setFirst(e.target.value);
              }}
            />
          </label>
          <label>
            До
            <input
              type="date"
              value={last}
              onChange={(e) => {
                setLast(e.target.value);
              }}
            />
          </label>
          <label>
            Показник
            <select
              aria-label="Показник"
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            >
              <option value="temperature">Температура ·°C</option>
              <option value="energy">Енергія ·кВт·год</option>
              <option value="cost">Вартість ·грн</option>
            </select>
          </label>
        </div>
        <p className="helper">
          Календар Europe/Kyiv ·{fmt((range.end - range.start) / 3600, 0)}год за
          UTC. Перехід часу може дати23 або 25 год на добу.
        </p>
        {!state.connected && (
          <p className="warning-text">
            Кешована синтетична історія · зв’язку немає
          </p>
        )}
        {error ? (
          <p role="alert">{error}</p>
        ) : metric === "temperature" ? (
          <>
            {!hasOriginal && (
              <p className="empty-note">
                Немає завчасного прогнозу на цей період. Показуємо тільки
                доступний факт.
              </p>
            )}
            {rows.length === 0 ? (
              <div className="empty-state">
                <h3>За ці дати немає збережених вимірів</h3>
                <p>Оберіть інший період. Відсутність даних не означає нуль.</p>
              </div>
            ) : (
              <Chart
                actual={rows}
                original={hasOriginal ? source.points : []}
                forecast={latest}
                now={state.now}
                scope={range}
                initialLatest={false}
                label="Історія температури"
                events={timeline}
              />
            )}
            <p className="helper">
              Увесь період: {history.rawCount} вихідних вимірів, {rows.length}{" "}
              точок огляду · сторінка до 128 · максимум4096 точок. Невідоме
              покриття: {fmt(history.unknownS / 60, 0)} хв · розривів:{" "}
              {history.gapCount}. Розриви не заповнюються.
            </p>
            <details>
              <summary>Докази завчасного прогнозу</summary>
              <dl className="diagnostic-list">
                <dt>Незмінний оригінал</dt>
                <dd>
                  {hasOriginal
                    ? "Є синтетичні докази"
                    : "MISSING · не відновлюється заднім числом"}
                </dd>
                <dt>Початок циклу</dt>
                <dd>{dateTime(source.reference)}</dd>
                <dt>Час випуску</dt>
                <dd>{dateTime(source.issued)}</dd>
                <dt>Архів отримав</dt>
                <dd>{dateTime(source.received)}</dd>
                <dt>Фактичне випередження отримання</dt>
                <dd>
                  {fmt((source.reference - source.received) / 3600)}год ·
                  потрібно≥12 год
                </dd>
                <dt>Модель / план</dt>
                <dd>
                  v{source.model} ·{source.plan}
                </dd>
                <dt>Джерело</dt>
                <dd>{source.source}</dd>
              </dl>
              <p>
                Новий прогноз не замінює оригінал; факт доступний незалежно від
                довжини прогнозу.
              </p>
            </details>
          </>
        ) : (
          <>
            <div className="energy-grid">
              <div>
                <span>Відомий факт</span>
                <strong>
                  {fmt(metric === "cost" ? priced : known)}
                  <small>{metric === "cost" ? "грн" : "кВт·год"}</small>
                </strong>
              </div>
              <div>
                <span>Оцінки окремо</span>
                <strong>
                  {fmt(metric === "cost" ? energy.costEstimated : estimated)}
                  <small>{metric === "cost" ? "грн" : "кВт·год"}</small>
                </strong>
              </div>
              <div>
                <span>Невідоме покриття</span>
                <strong>
                  {fmt(
                    (metric === "cost" ? energy.costUnknownS : unknownS) / 60,
                    0,
                  )}
                  <small>хв</small>
                </strong>
              </div>
            </div>
            {metric === "cost" && (
              <p className="helper">
                Вартість часткова за наявності пропусків тарифу. Енергія без
                тарифу: {fmt(energy.unpricedKwh, 3)} кВт·год. Відновлені та
                пропорційно розподілені суми — оцінки.
              </p>
            )}
            <Chart
              actual={energyPoints}
              forecast={estimatedPoints}
              scope={range}
              now={state.now}
              unit={metric === "cost" ? "грн" : "кВт·год"}
              forecastLabel="Оцінки"
              label={metric === "cost" ? "Історія вартості" : "Історія енергії"}
              comfort={false}
              tracks={false}
            />
            <p className="helper">
              Денний/7-денний облік не порівнюється з нічним циклом. Початковий
              цикловий бюджет доступний на вкладці «Дім» у власному періоді.
            </p>
            <div className="table-scroll">
              <table>
                <caption>
                  Якість інтервалів · синтетичні тарифи за часом
                </caption>
                <thead>
                  <tr>
                    <th>Початок</th>
                    <th>Енергія</th>
                    <th>Якість</th>
                    <th>грн/кВт·год</th>
                    <th>Метод / межа інтервалу</th>
                    <th>Вартість: факт / оцінка</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.slice(0, 48).map((i) => (
                    <tr key={i.start}>
                      <th scope="row">{dateTime(i.start)}</th>
                      <td>{fmt(i.kwh, 3)}</td>
                      <td>
                        {
                          {
                            confirmed: "Підтверджено",
                            derived: "Розраховано",
                            estimated: "Оцінка",
                            recovered: "Відновлено за доказом",
                            unknown: "Невідомо",
                          }[i.category]
                        }
                      </td>
                      <td>
                        {i.tariffs
                          ? "За датованими інтервалами"
                          : fmt(i.price, 2)}
                      </td>
                      <td>
                        {i.method
                          ? {
                              counter_difference: "Різниця лічильника",
                              integrated_power: "Інтегрування потужності",
                              prorated_estimate: "Пропорційна оцінка",
                            }[i.method]
                          : "Сукупний інтервал"}{" "}
                        · до {dateTime(i.end)}
                      </td>
                      <td>
                        {fmt(i.costKnown)} / {fmt(i.costEstimated)} грн
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Немає тарифу — немає підтвердженої вартості. Прогалини та оцінки
              не перетворюються на заощадження.
            </p>
          </>
        )}
      </Card>
      <Card
        title="Наскільки надійний прогноз?"
        aside={<Badge tone="warning">24 год ще перевіряється</Badge>}
      >
        <p>
          Короткий горизонт не доводить точність на добу. Для24 год є лише3
          незалежні дні, а не7.
        </p>
        <button className="text-button" onClick={onModel}>
          Модель і діагностика
          <IconArrow />
        </button>
      </Card>
    </>
  );
}
function IconArrow() {
  return <span aria-hidden="true">↗</span>;
}
