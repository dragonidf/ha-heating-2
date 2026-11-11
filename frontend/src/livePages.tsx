/** Actual HA observations in the approved three-tab shell. No fake history. */
import type { Snapshot } from "./types";
import type { LiveHAAPI } from "./liveHA";
import { Card } from "./components";
import { fmt } from "./domain";

const kw = (v: number | null) => v === null ? "—" : v.toFixed(2) + " кВт";
const volt = (v: number | null) => v === null ? "—" : v.toFixed(1) + " В";
function Moment({ value }: { value: string | null }) {
  if (!value) return <>немає даних</>;
  const d = new Date(value);
  return <>{Number.isFinite(d.valueOf()) ? d.toLocaleString("uk-UA") : "невідомий час"}</>;
}
export function LiveHome({ api, state }: { api: LiveHAAPI; state: Snapshot }) {
  const t = api.telemetry;
  return (
    <>
      <h1 className="sr-only">Дім</h1>
      <section className="comfort card" aria-label="Дані кімнати">
        <div className="comfort-main">
          <p className="eyebrow">Температура вітальні · фактичний стан HA</p>
          <div className="room-value">{state.room.quality === "valid" ? fmt(t.room) : "—"}<span>°C</span></div>
          <p className="hero-caption">
            {t.room === null ? "Датчик недоступний" : state.room.quality === "valid"
              ? "Останній стан датчика в Home Assistant"
              : "Значення застаріле — для керування непридатне"}
          </p>
          <span className="helper">Останнє повідомлення: <Moment value={t.lastReported.room ?? null} /></span>
        </div>
        <div className="target">
          <span className="muted">Термостат котла</span>
          <strong>{t.thermostatSetpoint === null ? "—" : t.thermostatSetpoint.toFixed(1) + " °C"}</strong>
          <span className="helper">Режим: {t.thermostatMode ?? "невідомо"} · це не кімнатна ціль</span>
        </div>
      </section>
      <div className="notice safety" role="status">
        Новий контролер: спостереження. Фізичні команди заборонені, старий Heating AI продовжує керування.
      </div>
      <Card title="Електромережа та вхідна напруга">
        <p><strong>{t.grid === true ? "Наявна мережа" : t.grid === false ? "Відсутня мережа" : "Статус мережі невідомий"}</strong></p>
        <p className="helper">Статус — лише за існуючим хелпером. Напруги нижче є останніми значеннями лічильника.</p>
        <p>L1: {volt(t.voltages[0] ?? null)} · L2: {volt(t.voltages[1] ?? null)} · L3: {volt(t.voltages[2] ?? null)}</p>
      </Card>
      <Card title="KWS · котел">
        <p><strong>Сумарна активна потужність: {kw(t.kwsTotal)}</strong></p>
        <p>L1: {kw(t.kws[0] ?? null)} · L2: {kw(t.kws[1] ?? null)} · L3: {kw(t.kws[2] ?? null)}</p>
        <p>Накопичувальна енергія: {t.kwsEnergy === null ? "—" : t.kwsEnergy.toFixed(2) + " кВт·год"}</p>
        <p className="helper">Останні показники Tuya Local. Нуль, що не змінюється, — не помилка. Дані KWS не підтверджують фізичний стан контактів термостата.</p>
      </Card>
      <Card title="План нагріву">
        <p>Обчислення Heating AI 2.0 поки не підключене до реальних прогнозів та історії.</p>
        <p className="helper">Майбутні сеанси, графік і прогноз економії не підміняються демонстраційними даними.</p>
      </Card>
    </>
  );
}
export function LiveHistory() {
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">Оригінали, факт та енергобюджет</p><h1>Історія</h1></div></div>
      <Card title="Міграцію історії не завершено">
        <p>Реальні дані старого Heating AI та незмінні оригінальні прогнози ще не перенесені до нового архіву.</p>
        <p>До підтвердження безперервності лічильників і прогнозів тут не показуються фальшиві графіки, суми чи «економія».</p>
      </Card>
    </>
  );
}
export function LiveSettings({ api }: { api: LiveHAAPI }) {
  const t = api.telemetry;
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">Спостереження · без фізичного керування</p><h1>Налаштування</h1></div></div>
      <Card title="Стан підключення">
        <p>Підключення: Home Assistant, 10 наявних сутностей.</p>
        <p>Керування: вимкнене. Реєстрація команд термостату: відсутня.</p>
        <p>Термостат: {t.thermostatMode ?? "невідомий режим"}; уставка пристрою {t.thermostatSetpoint === null ? "—" : t.thermostatSetpoint.toFixed(1) + " °C"}.</p>
      </Card>
      <Card title="Налаштування та модель">
        <p>Ціль температури вдень/уночі, графік, модель і one-shot ще не імпортовано.</p>
        <p className="helper">Поля залишаються недоступними, доки перехід зі старої системи не підтверджений. Жодних початкових демонстраційних значень не записується.</p>
      </Card>
    </>
  );
}
