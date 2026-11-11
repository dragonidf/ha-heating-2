/** Actual HA observations in the approved three-tab shell. No fake history. */
import { useEffect, useMemo, useState } from "react";
import type { Point, Snapshot } from "./types";
import type { LiveHAAPI } from "./liveHA";
import { Card, Chart } from "./components";
import { fmt, kyivRange, shiftDate } from "./domain";

const kw = (v: number | null) => (v === null ? "—" : v.toFixed(2) + " кВт");
const volt = (v: number | null) => (v === null ? "—" : v.toFixed(1) + " В");
function Moment({ value }: { value: string | null }) {
  if (!value) return <>немає даних</>;
  const d = new Date(value);
  return (
    <>
      {Number.isFinite(d.valueOf())
        ? d.toLocaleString("uk-UA")
        : "невідомий час"}
    </>
  );
}
export function LiveHome({ api, state }: { api: LiveHAAPI; state: Snapshot }) {
  const t = api.telemetry;
  return (
    <>
      <h1 className="sr-only">Дім</h1>
      <section className="comfort card" aria-label="Дані кімнати">
        <div className="comfort-main">
          <p className="eyebrow">Температура вітальні · фактичний стан HA</p>
          <div className="room-value">
            {state.room.quality === "valid" ? fmt(t.room) : "—"}
            <span>°C</span>
          </div>
          <p className="hero-caption">
            {t.room === null
              ? "Датчик недоступний"
              : state.room.quality === "valid"
                ? "Останній стан датчика в Home Assistant"
                : "Значення застаріле — для керування непридатне"}
          </p>
          <span className="helper">
            Останнє повідомлення: <Moment value={t.lastReported.room ?? null} />
          </span>
        </div>
        <div className="target">
          <span className="muted">Термостат котла</span>
          <strong>
            {t.thermostatSetpoint === null
              ? "—"
              : t.thermostatSetpoint.toFixed(1) + " °C"}
          </strong>
          <span className="helper">
            Режим: {t.thermostatMode ?? "невідомо"} · це не кімнатна ціль
          </span>
        </div>
      </section>
      <div className="notice safety" role="status">
        Новий контролер: спостереження. Фізичні команди заборонені, старий
        Heating AI продовжує керування.
      </div>
      <Card title="Електромережа та вхідна напруга">
        <p>
          <strong>
            {t.grid === true
              ? "Наявна мережа"
              : t.grid === false
                ? "Відсутня мережа"
                : "Статус мережі невідомий"}
          </strong>
        </p>
        <p className="helper">
          Статус — лише за існуючим хелпером. Напруги нижче є останніми
          значеннями лічильника.
        </p>
        <p>
          L1: {volt(t.voltages[0] ?? null)} · L2: {volt(t.voltages[1] ?? null)}{" "}
          · L3: {volt(t.voltages[2] ?? null)}
        </p>
      </Card>
      <Card title="KWS · котел">
        <p>
          <strong>Сумарна активна потужність: {kw(t.kwsTotal)}</strong>
        </p>
        <p>
          L1: {kw(t.kws[0] ?? null)} · L2: {kw(t.kws[1] ?? null)} · L3:{" "}
          {kw(t.kws[2] ?? null)}
        </p>
        <p>
          Накопичувальна енергія:{" "}
          {t.kwsEnergy === null ? "—" : t.kwsEnergy.toFixed(2) + " кВт·год"}
        </p>
        <p className="helper">
          Останні показники Tuya Local. Нуль, що не змінюється, — не помилка.
          Дані KWS не підтверджують фізичний стан контактів термостата.
        </p>
      </Card>
      <Card title="Зворотна лінія котла">
        <p>Зовнішній щуп: {t.returnC === null ? "—" : t.returnC.toFixed(1) + " °C"}</p>
        <p className="helper">Останнє значення HA. Поки не кваліфіковано як незалежний safety-доказ.</p>
      </Card>
      <Card title="Камін та циркуляція">
        <p>
          Температура біля каміна:{" "}
          {t.fireplaceC === null ? "—" : t.fireplaceC.toFixed(1) + " °C"}
          {" · "}
          Перепад до вітальні:{" "}
          {t.fireplaceDeltaC === null
            ? "—"
            : t.fireplaceDeltaC.toFixed(1) + " °C"}
        </p>
        <p>
          Циркуляція:{" "}
          {t.fanActual === "on"
            ? "увімкнена"
            : t.fanActual === "off"
              ? "вимкнена"
              : "невідомо"}
          {" · "}
          Швидкість:{" "}
          {t.fanPercent === null ? "—" : t.fanPercent.toFixed(0) + "%"}
        </p>
        <p>
          Режим: {t.fanMode ?? "невідомий"}
          {" · "}
          Ніч / день / інтенсивно:{" "}
          {t.fanSpeeds
            .map((x) => (x === null ? "—" : x.toFixed(0) + "%"))
            .join(" / ")}
        </p>
        <p className="helper">
          Ручний режим «Зупинити» зберігає пріоритет. На етапі SHADOW новий
          контролер не вмикає вентилятор, навіть коли біля каміна тепліше.
          Резервне живлення потребує незалежного підтвердження.
        </p>
        <p>
          Рекуператор:{" "}
          {t.ventilation.recuperator === null
            ? "невідомо"
            : t.ventilation.recuperator
              ? "увімкнено"
              : "вимкнено"}
          {" · "}
          Витяжка ванної:{" "}
          {t.ventilation.bath === null
            ? "невідомо"
            : t.ventilation.bath
              ? "увімкнено"
              : "вимкнено"}
        </p>
      </Card>
      <Card title="План нагріву">
        <p>
          Обчислення Heating AI 2.0 поки не підключене до реальних прогнозів та
          історії.
        </p>
        <p className="helper">
          Майбутні сеанси, графік і прогноз економії не підміняються
          демонстраційними даними.
        </p>
      </Card>
    </>
  );
}
function todayKyiv(): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Kyiv",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = (key: string) => parts.find((item) => item.type === key)?.value;
  return [value("year"), value("month"), value("day")].join("-");
}
type HistoryWindow = { start: number; end: number };
type RecorderHistory = {
  loading: boolean;
  error: string | null;
  points: Point[];
};
export function LiveHistory({ api }: { api: LiveHAAPI }) {
  const [days, setDays] = useState<1 | 7 | 30>(7);
  const scope = useMemo<HistoryWindow>(() => {
    const now = Date.now() / 1000;
    return {
      start:
        days === 1
          ? now - 86400
          : kyivRange(shiftDate(todayKyiv(), 1 - days), todayKyiv()).start,
      end: now,
    };
  }, [days]);
  const [history, setHistory] = useState<RecorderHistory>({
    loading: true,
    error: null,
    points: [],
  });
  useEffect(() => {
    let active = true;
    setHistory({ loading: true, error: null, points: [] });
    void api.loadRoomHistory(scope).then(
      (points) => {
        if (active) setHistory({ loading: false, error: null, points });
      },
      () => {
        if (active) {
          setHistory({
            loading: false,
            error: "Неможливо прочитати реальну історію HA Recorder. Спробуйте коротший період.",
            points: [],
          });
        }
      },
    );
    return () => {
      active = false;
    };
  }, [api, scope]);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Реальні виміри · HA Recorder</p>
          <h1>Історія</h1>
        </div>
      </div>
      <Card title="Температура вітальні · факт">
        <div className="segmented" aria-label="Період історії">
          {([
            [1, "24 год"],
            [7, "7 днів"],
            [30, "30 днів"],
          ] as const).map(([length, label]) => (
            <button
              key={length}
              aria-pressed={days === length}
              onClick={() => setDays(length)}
            >
              {label}
            </button>
          ))}
        </div>
        {history.loading ? (
          <p role="status">Читаємо фактичні записи Recorder…</p>
        ) : history.error ? (
          <p role="alert">{history.error}</p>
        ) : history.points.length === 0 ? (
          <p>За цей період HA Recorder не має підтверджених записів температури.</p>
        ) : (
          <>
            <Chart
              actual={history.points}
              scope={scope}
              now={scope.end}
              label="Історія фактичної температури HA"
              original={[]}
              forecast={[]}
              initialLatest={false}
              forecastLabel="Прогноз не імпортовано"
              events={[]}
              tracks={false}
              comfort={false}
            />
            <p className="helper">
              Записи HA: {history.points.length}. Розриви між повідомленнями
              понад 90 хв не з’єднуємо. Це історія станів HA, а не незалежне
              підтвердження фізичного вимірювання.
            </p>
          </>
        )}
      </Card>
      <Card title="Міграцію історії не завершено">
        <p>
          Завчасні 12-годинні прогнози старого Heating AI, архів його рішень і
          енергобюджет ще не перенесено. Показані вище дані Recorder не замінюють
          незмінних оригінальних прогнозів.
        </p>
      </Card>
    </>
  );
}
export function LiveSettings({ api }: { api: LiveHAAPI }) {
  const t = api.telemetry;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Спостереження · без фізичного керування</p>
          <h1>Налаштування</h1>
        </div>
      </div>
      <Card title="Стан підключення">
        <p>
          Підключення: Home Assistant, 10 базових сутностей і додаткові джерела
          каміна/циркуляції за наявності.
        </p>
        <p>Керування: вимкнене. Реєстрація команд термостату: відсутня.</p>
        <p>
          Термостат: {t.thermostatMode ?? "невідомий режим"}; уставка пристрою{" "}
          {t.thermostatSetpoint === null
            ? "—"
            : t.thermostatSetpoint.toFixed(1) + " °C"}
          .
        </p>
      </Card>
      <Card title="Налаштування та модель">
        <p>
          Ціль температури вдень/уночі, графік, модель і one-shot ще не
          імпортовано.
        </p>
        <p className="helper">
          Поля залишаються недоступними, доки перехід зі старої системи не
          підтверджений. Жодних початкових демонстраційних значень не
          записується.
        </p>
      </Card>
    </>
  );
}
