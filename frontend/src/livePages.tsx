/** Actual HA observations in the approved three-tab shell. No fake history. */
import { useEffect, useMemo, useState } from "react";
import type { Point, Snapshot } from "./types";
import type { LiveHAAPI, NativeHistory } from "./liveHA";
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
      <NativeStatus api={api} />
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
      <Card title="Погода та відключення · джерела прогнозу">
        <p>
          Погодинний прогноз:{" "}
          {t.sources.weatherStatus === "RECEIVED_ISSUED_UNKNOWN"
            ? t.sources.weatherHours + " точок"
            : "не завантажено"}
        </p>
        <p className="helper">
          Час випуску погодного прогнозу не підтверджено джерелом. Отримання
          прогнозу не доводить точність теплової моделі.
        </p>
        <p>
          Наступне оголошене відключення:{" "}
          {t.sources.nextOutageAt === null
            ? "невідомо"
            : new Date(t.sources.nextOutageAt * 1000).toLocaleString("uk-UA", {
                timeZone: "Europe/Kyiv",
              })}
        </p>
        <p className="helper">
          Календар містить лише оголошені відключення. Відсутність події не
          означає підтвердженої наявності електроенергії.
        </p>
      </Card>
      <Card title="Охолодження без нагріву · умовний сценарій">
        <p>
          {t.coast.status === "UNQUALIFIED_CONDITIONAL_COAST" &&
          t.coast.min !== null
            ? "Мінімум " +
              fmt(t.coast.min) +
              " °C за " +
              t.coast.hours.toFixed(1) +
              " год"
            : "Бракує даних погоди або моделі для сценарію"}
        </p>
        <p className="helper">
          Лише порівняльний розрахунок на старих коефіцієнтах за припущення
          повністю вимкненого котла, відсутності додаткового сонячного тепла,
          каміна й вентиляційних втрат. Це не робочий план і не прогноз
          гарантованої температури. Калібрування нової моделі не підтверджене.
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
        <p>
          Зовнішній щуп:{" "}
          {t.returnC === null ? "—" : t.returnC.toFixed(1) + " °C"}
        </p>
        <p className="helper">
          Останнє значення HA. Поки не кваліфіковано як незалежний safety-доказ.
        </p>
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
        {t.plan.status === "VIRTUAL_CONDITIONAL" ? (
          <>
            <p>
              <strong>
                Умовний сценарій на {t.plan.horizonHours.toFixed(1)} год
              </strong>
              {" · "}
              {t.plan.powerKw === null
                ? "режим котла невідомий"
                : "наявний режим " + t.plan.powerKw.toFixed(0) + " кВт"}
            </p>
            <p>
              Номінальна енергія за сценарієм:{" "}
              {t.plan.nominalEnergyKwh === null
                ? "—"
                : t.plan.nominalEnergyKwh.toFixed(2) + " кВт·год"}
              {" · "}
              Розрахунковий мінімум:{" "}
              {t.plan.projectedMinC === null
                ? "—"
                : t.plan.projectedMinC.toFixed(1) + " °C"}
            </p>
            <p>Можливих інтервалів: {t.plan.segmentCount}</p>
            {t.plan.segments.length > 0 && (
              <ul>
                {t.plan.segments.slice(0, 6).map((segment, index) => (
                  <li key={index}>
                    {new Date(segment.start * 1000).toLocaleString("uk-UA", {
                      timeZone: "Europe/Kyiv",
                      hour: "2-digit",
                      minute: "2-digit",
                      day: "2-digit",
                      month: "2-digit",
                    })}
                    {" – "}
                    {new Date(segment.end * 1000).toLocaleTimeString("uk-UA", {
                      timeZone: "Europe/Kyiv",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    {" · умовно"}
                  </li>
                ))}
              </ul>
            )}
            {t.plan.truncated && (
              <p className="helper">
                Показано лише найближчі інтервали, решта прихована.
              </p>
            )}
          </>
        ) : (
          <p>
            Умовний план недоступний: бракує актуальних даних, прив’язок
            налаштувань або допустимого погодного горизонту.
          </p>
        )}
        <p className="helper">
          Розрахунок використовує наявний оптимізатор, але стара теплова модель
          не пройшла кваліфікацію, а час випуску погоди й майбутня наявність
          мережі не підтверджені. Умовні сеанси не виконуються; енергія
          номінальна, не виміряна. Автоматичні команди заборонені.
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
  const [archive, setArchive] = useState<NativeHistory | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setArchive(null);
    setArchiveError(null);
    void api.nativeHistory(scope).then(
      (value) => {
        if (active) setArchive(value);
      },
      () => {
        if (active) setArchiveError("Native архів недоступний");
      },
    );
    return () => {
      active = false;
    };
  }, [api, scope]);
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
            error:
              "Неможливо прочитати реальну історію HA Recorder. Спробуйте коротший період.",
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
          {(
            [
              [1, "24 год"],
              [7, "7 днів"],
              [30, "30 днів"],
            ] as const
          ).map(([length, label]) => (
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
          <p>
            За цей період HA Recorder не має підтверджених записів температури.
          </p>
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
      <Card title="Енергія · один апаратний KWS-лічильник">
        {archiveError ? (
          <p role="alert">{archiveError}</p>
        ) : archive ? (
          <>
            <p>
              {archive.energy.reduce((sum, row) => sum + row.kwh, 0).toFixed(3)}{" "}
              кВт·год за повністю архівованими інтервалами
            </p>
            <p>
              Інтервалів: {archive.energy.length}. Різниця одного
              накопичувального лічильника, без подвійного інтегрування фаз.
            </p>
            <p>
              Оригінал прогнозу:{" "}
              {archive.original_status === "MISSING"
                ? "Відсутній: немає оригіналу, отриманого й збереженого за 12 год до порівняння"
                : "Наявний у незмінному архіві"}
            </p>
            {archive.truncated && <p>Дані обмежено: скоротіть період.</p>}
          </>
        ) : (
          <p role="status">Читання native архіву…</p>
        )}
      </Card>
      <Card title="Міграцію історії не завершено">
        <p>
          Завчасні 12-годинні прогнози старого Heating AI, архів його рішень і
          енергобюджет ще не перенесено. Показані вище дані Recorder не
          замінюють незмінних оригінальних прогнозів.
        </p>
      </Card>
    </>
  );
}
const labels: Record<string, string> = {
  day_target: "Денна ціль °C",
  night_target: "Нічна ціль °C",
  day_upper: "Денна верхня межа °C",
  night_upper: "Нічна верхня межа °C",
  sleep_start: "Початок ночі",
  sleep_end: "Кінець ночі",
  heating_start: "Початок дозволених годин",
  heating_end: "Кінець дозволених годин",
  strategy: "Стратегія",
  power_model: "Розрахункова потужність",
  fan_mode: "Режим циркуляції",
  fan_night: "Нічна швидкість %",
  fan_standard: "Денна швидкість %",
  fan_intense: "Інтенсивна швидкість %",
  min_voltage_v: "Мінімальна напруга V",
  max_voltage_v: "Максимальна напруга V",
  hysteresis_v: "Гістерезис V",
  stable_recovery_s: "Стабілізація, с",
  voltage_max_age_s: "Вік напруги, с",
  room_max_age_s: "Вік виміру вітальні, с",
  energy_budget_kwh: "Бюджет циклу кВт·год (потребує повної історії)",
};
const selections: Record<string, string[]> = {
  strategy: [
    "Тільки в дозволені години",
    "Переважно вночі",
    "Комфорт протягом доби",
  ],
  power_model: ["fixed_3", "fixed_6", "fixed_9"],
  fan_mode: ["Авто", "Ручний запуск", "Зупинити"],
};
export function LiveSettings({ api }: { api: LiveHAAPI }) {
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const load = () => {
    if (!api.backend) return;
    setDraft(
      Object.fromEntries(
        Object.entries(api.backend.settings.values).map(([k, v]) => [
          k,
          String(v),
        ]),
      ),
    );
    setRevision(api.backend.settings.revision);
  };
  useEffect(() => {
    if (draft === null && api.backend) load();
  }, [api.backend, draft]);
  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const values = Object.fromEntries(
        Object.entries(draft ?? {})
          .filter(([, v]) => v !== "")
          .map(([k, v]) => [
            k,
            selections[k] || k.endsWith("_start") || k.endsWith("_end")
              ? v
              : Number(v),
          ]),
      );
      const status = await api.mutateNative("settings/save", values, revision);
      setMessage(
        status === "saved"
          ? "Збережено в SQLite з CAS і readback. Фізичне керування залишається вимкненим."
          : "Конфлікт версії: введені значення збережено у формі. Перечитайте сервер перед наступним записом.",
      );
      if (status === "saved") setRevision(revision + 1);
    } catch {
      setMessage(
        "Запис відхилено: перевірте дані, підключення та права адміністратора. Введені значення не втрачено.",
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <div className="page-heading">
        <h1>Налаштування</h1>
      </div>
      <NativeStatus api={api} />
      <Card title="Налаштування native контролера">
        <p>
          Початкові значення читаються з прив’язаних хелперів. Запис змінює лише
          новий контролер, не старі хелпери чи пристрої.
        </p>
        {!draft ? (
          <p role="status">Очікуємо backend…</p>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <fieldset disabled={!api.canWriteNative || saving}>
              <legend>Ревізія {revision} · без фізичного керування</legend>
              {Object.entries(labels).map(([key, label]) => (
                <label className="field" key={key}>
                  {label}
                  {selections[key] ? (
                    <select
                      value={draft[key] ?? ""}
                      onChange={(e) =>
                        setDraft({ ...draft, [key]: e.target.value })
                      }
                    >
                      <option value="">Не налаштовано</option>
                      {selections[key].map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={draft[key] ?? ""}
                      placeholder="Не налаштовано"
                      type={
                        key.endsWith("_start") || key.endsWith("_end")
                          ? "text"
                          : "number"
                      }
                      step="any"
                      onChange={(e) =>
                        setDraft({ ...draft, [key]: e.target.value })
                      }
                    />
                  )}
                </label>
              ))}
              <button type="submit">
                {saving ? "Зберігаємо…" : "Зберегти"}
              </button>
            </fieldset>
          </form>
        )}
        <button onClick={load} disabled={!api.backend || saving}>
          Перечитати сервер (замінити форму)
        </button>
        {message && <p role="status">{message}</p>}
      </Card>
      <Card title="Налаштування та модель">
        <p>
          {api.backend?.model.parameters
            ? "Наявні коефіцієнти зі старого контролера; кваліфікація не підтверджена."
            : "Реальний файл моделі / коефіцієнти недоступні. Демозначення не використовуються."}
        </p>
        {api.backend?.model.parameters && (
          <dl>
            {Object.entries(api.backend.model.parameters).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        )}
        <p>
          Champion/challenger не можна підвищити без достовірного навчального
          архіву та незалежної валідації. AI advice потребує налаштованого
          джерела; відповідь не вигадується.
        </p>
      </Card>
    </>
  );
}

function NativeStatus({ api }: { api: LiveHAAPI }) {
  const native = api.backend;
  const [message, setMessage] = useState<string | null>(null);
  const act = async (operation: string) => {
    if (!native) return;
    try {
      setMessage(
        await api.mutateNative(operation, {}, native.settings.revision),
      );
    } catch {
      setMessage("Операцію не підтверджено — керування заблоковане");
    }
  };
  return (
    <Card title="Стан системи · native backend">
      {api.backendError && <p role="alert">{api.backendError}</p>}
      {!native ? (
        <p>
          Очікування авторизованого backend. Дані датчиків нижче — лише останні
          стани HA.
        </p>
      ) : (
        <>
          <p>
            Ядро: {native.controller.mode} · {native.controller.reason}
          </p>
          <p>
            Напруга: {native.safety.voltage_status}. KWS supply-ready: не
            підтверджено.
          </p>
          <p>
            Режим {native.active_limit.band}: ціль{" "}
            {native.active_limit.target ?? "—"} °C, верхня межа{" "}
            {native.active_limit.upper ?? "—"} °C; резервний максимум{" "}
            {native.active_limit.ceiling ?? "—"} °C.
          </p>
          <p>
            SQLite-журнал: ревізія {native.journal.revision},{" "}
            {native.journal.fenced ? "fenced" : "без права керування"}.
            Надіслано команд: {native.controller.actual_commands}.
          </p>
          <p>
            Разовий нагрів: {native.one_shot.state}. Нове озброєння заблоковане
            без кваліфікованих джерел і ownership.
          </p>
          <p>
            Циркуляція: пропозиція {native.fan?.percentage_proposed ?? "—"} %,{" "}
            {native.fan?.reason ?? "немає даних"}; передача fan-writer не
            виконана.
          </p>
          {native.settings.energy_fault && (
            <p role="alert">Енергія: {native.settings.energy_fault}</p>
          )}
          {native.fault && <p role="alert">{native.fault}</p>}
          <button
            disabled={!api.canWriteNative}
            onClick={() => void act("pause")}
          >
            STOP нового контролера
          </button>
          <button
            disabled={!api.canWriteNative}
            onClick={() => void act("resume")}
          >
            Зняти ручну паузу (без запуску)
          </button>
          <button
            disabled={!api.canWriteNative}
            onClick={() => void act("cancel")}
          >
            Скасувати разовий запит
          </button>
          {message && <p role="status">{message}</p>}
          {(native.plan?.trajectory?.length ?? 0) > 0 && (
            <Chart
              actual={[]}
              original={[]}
              forecast={native.plan!.trajectory!}
              scope={{
                start: api.feed.value.now,
                end: api.feed.value.now + 86400,
              }}
              now={api.feed.value.now}
              label="Умовний 24-годинний прогноз погодженої теплової моделі"
              forecastLabel="Умовний прогноз, не фізичний факт"
              events={[]}
              tracks={false}
              comfort={false}
            />
          )}
        </>
      )}
      <p className="helper">
        Фізичні команди вимкнені. HA_ECHO не підтверджує сухі контакти. Старий
        контролер і захист KWS не змінюються.
      </p>
    </Card>
  );
}
