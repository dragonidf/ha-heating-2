import { useState } from "react";
import { Card, Badge, Chart, Dialog, Icon } from "./components";
import { fmt, time, dateTime, prioritize, energySummary } from "./domain";
import type { Snapshot } from "./types";
import { operatorView, type OperatorAPI } from "./operator";
import type { SettingsController } from "./useSettings";
export function Home({
  state,
  api,
  settings,
  onHistory,
}: {
  state: Snapshot;
  api: OperatorAPI;
  settings: SettingsController;
  onHistory: () => void;
}) {
  const [controlMessage, setControlMessage] = useState("");
  const { actual, latest, cycleEnergy, timeline } = operatorView(api);
  const current = settings.saved?.values;
  const alert = prioritize(state.notices);
  const budget = {
    ...cycleEnergy,
    known: api.scenario === "overspend" ? 20.2 : cycleEnergy.known,
  };
  const sum = energySummary(budget);
  const permitted = api.canChange() && !settings.pending && !!settings.saved;
  const hasDraft =
    settings.dirtyPaths.length > 0 ||
    !!settings.conflict ||
    settings.collisions.length > 0;
  const room = state.room.quality === "valid" ? state.room.value : null;
  const intent = (kind: "pause" | "resume" | "arm" | "cancel") =>
    void Promise.resolve(api.control(kind, api.session)).then(
      (receipt) => setControlMessage(receipt.reason),
      () => setControlMessage("Запит не підтверджено. Перечитайте стан."),
    );
  return (
    <>
      <h1 className="sr-only">Дім</h1>
      <section className="comfort card" aria-labelledby="comfort-title">
        <div className="comfort-main">
          <div className="eyebrow" id="comfort-title">
            Комфорт удома <Badge>демодані</Badge>
          </div>
          <div className="room-value">
            {fmt(room)}
            <span>°C</span>
          </div>
          <p className="hero-caption">
            {room === null
              ? `Останній придатний вимір: ${fmt(state.room.value)}°C · ${dateTime(state.room.observed)}`
              : room < (current?.night ?? 20.5)
                ? "Потрібне тепло. Запланований нагрів умовний."
                : "Тепла достатньо. Нічний комфорт."}
          </p>
        </div>
        <div className="target">
          <span className="muted">Бажана температура · сон</span>
          <div className="stepper">
            <button
              aria-label="Зменшити ціль на0,5 °C у симуляції"
              disabled={
                !permitted || hasDraft || !current || current.night <= 16
              }
              onClick={() =>
                current &&
                void settings.save({ ...current, night: current.night - 0.5 })
              }
            >
              −
            </button>
            <strong>
              {fmt(current?.night ?? null)}
              <small>°C</small>
            </strong>
            <button
              aria-label="Збільшити ціль на0,5 °C у симуляції"
              disabled={
                !permitted ||
                hasDraft ||
                !current ||
                current.night >= current.day
              }
              onClick={() =>
                current &&
                void settings.save({ ...current, night: current.night + 0.5 })
              }
            >
              +
            </button>
          </div>
          <span className="helper">
            {hasDraft
              ? "Спочатку збережіть або скасуйте чернетку в налаштуваннях"
              : "Зміна лише в симуляції"}
          </span>
        </div>
        <div className="action-strip">
          <div>
            <span className="status-dot" />
            <strong>Фізичний стан котла — невідомий</strong>
            <span className="helper">
              {state.status.actual === "heat"
                ? "Симулятор спостерігає нагрів; це не фізичний доказ."
                : state.status.actual === "stop_demand"
                  ? "Симулятор повідомляє STOP; це не фізична перевірка зупинки."
                  : state.status.receipt_stage
                    ? "Fake ACK не підтверджує нагрів чи зупинку."
                    : "Запит контролера: очікування. Наступний сеанс о 05:00."}
            </span>
          </div>
          <button
            disabled={
              !(state.status.mode === "MANUAL_PAUSE"
                ? api.canChange()
                : (api.canStop?.() ?? api.canChange()))
            }
            onClick={() =>
              intent(state.status.mode === "MANUAL_PAUSE" ? "resume" : "pause")
            }
          >
            {state.status.mode === "MANUAL_PAUSE"
              ? "Продовжити в симуляції"
              : "Пауза симуляції"}
          </button>
        </div>
        <div className="desired-row">
          <span>
            Запит:{" "}
            {state.status.desired === "heat" ? "нагрів" : "не подавати тепло"}
          </span>
          <span>
            {state.status.mode === "MANUAL_PAUSE"
              ? "Автоматика на паузі"
              : state.status.mode === "SAFE_HOLD"
                ? "Захисне утримання"
                : state.status.mode === "SHADOW"
                  ? "Спостереження · запити нагріву заблоковані"
                  : "План умовний"}
          </span>
        </div>
      </section>
      {alert && (
        <aside className={`notice ${alert.priority}`} role="alert">
          <Icon name="info" />
          <div>
            <strong>
              {alert.priority === "safety" ? "Потребує уваги" : "Важливо зараз"}
            </strong>
            <p>{alert.text}</p>
          </div>
        </aside>
      )}
      {(settings.message || controlMessage) && (
        <p className="feedback" role="status">
          {controlMessage || settings.message}
        </p>
      )}
      <div className="home-grid">
        <div className="home-main">
          <Card
            title="Наступні 24 години"
            aside={<Badge tone="prediction">Умовний прогноз</Badge>}
          >
            <Chart
              actual={actual.filter((p) => p.at >= state.now - 6 * 3600)}
              forecast={latest}
              scope={{ start: state.now - 6 * 3600, end: state.now + 86400 }}
              now={state.now}
              label="Прогноз температури"
              events={
                state.fan.fire
                  ? [
                      ...timeline,
                      {
                        start: state.now - 3600,
                        end: state.now + 3600,
                        kind: "fire",
                      },
                    ]
                  : timeline
              }
            />
            <div className="session-list">
              <div>
                <Icon name="moon" />
                <p>
                  <strong>05:00–05:40</strong>
                  <span>Ранковий прогрів · потрібно40 хв</span>
                </p>
                <Badge tone="heating">План</Badge>
              </div>
              <div>
                <Icon name="sun" />
                <p>
                  <strong>До 07:00 · {fmt(21.5)}°C</strong>
                  <span>30 хв безперервно за наявної потреби й дозволів</span>
                </p>
              </div>
            </div>
            <p className="helper">
              Графік електрики на завтра ще не підтверджений. Безпека може
              перервати сеанс.
            </p>
          </Card>
        </div>
        <div className="home-side">
          <Card
            title="Цикл до 07:00"
            aside={<span className="helper">04 листопада</span>}
          >
            <div className="energy-grid">
              <div>
                <span>Початковий план</span>
                <strong>
                  {fmt(budget.reference)}
                  <small>кВт·год</small>
                </strong>
              </div>
              <div>
                <span>Відомий факт</span>
                <strong>
                  {fmt(budget.known)}
                  <small>кВт·год</small>
                </strong>
              </div>
              <div>
                <span>Очікуємо</span>
                <strong className="warning-text">
                  {fmt(budget.projected)}
                  <small>кВт·год</small>
                </strong>
              </div>
            </div>
            <div className="energy-meter" aria-hidden="true">
              <span
                style={{
                  width: `${Math.min(100, (budget.known / (budget.reference ?? 1)) * 100)}%`,
                }}
              />
            </div>
            <p className="helper">
              {budget.scope && (
                <span>
                  {time(budget.scope.start)}–{time(budget.scope.end)} Kyiv ·
                  факт до {time(budget.actualUntil ?? state.now)}
                </span>
              )}
              <br />
              Прогалини:18 хв · оцінено {fmt(budget.estimated)}кВт·год окремо
            </p>
            <p className="budget-note">
              {sum.remaining !== null && sum.remaining < 0
                ? `Щонайменше${fmt(-sum.remaining)}кВт·год понад план`
                : `Очікуване перевищення: ${fmt(sum.overrun)}кВт·год`}
            </p>
            <button className="text-button" onClick={onHistory}>
              Переглянути облік
              <Icon name="arrow" />
            </button>
          </Card>
          <Card title="Камін і циркуляція" aside={<Icon name="fire" />}>
            <div className="fan-row">
              <div>
                <strong>{state.fan.phase}</strong>
                <p className="helper">
                  {state.fan.fire
                    ? "Запит каміна збережено після нічного таймера"
                    : "Нічний короткий запит ·15 хв"}
                </p>
              </div>
              <Badge tone={state.fan.fire ? "heating" : "muted"}>
                {state.fan.requested === null ? "—" : state.fan.requested}%
                запит
              </Badge>
            </div>
            <Dialog title="Циркуляція · симуляція" trigger="Швидкість і деталі">
              <p>
                Фізична швидкість невідома. Ручний режим вентилятора незалежний
                від паузи котла; завершення нічного таймера не скасовує запит
                каміна.
              </p>
              <label>
                Бажана швидкість
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={settings.draft.fan}
                  disabled={!permitted}
                  onChange={(e) =>
                    settings.edit({
                      ...settings.draft,
                      fan: Number(e.target.value),
                    })
                  }
                />
                <output>{settings.draft.fan}%</output>
              </label>
              <button
                disabled={!permitted}
                onClick={() => void settings.save()}
              >
                Зберегти симуляцію
              </button>
              <details>
                <summary>Теплові фактори</summary>
                <p>
                  Рекуператор: невідомо. Витяжка: невідомо. Лише читання; стан
                  реле не є витратою повітря.
                </p>
              </details>
            </Dialog>
          </Card>
        </div>
      </div>
      <details className="card compact-details">
        <summary>
          Одноразовий запит після відновлення живлення · симуляція
        </summary>
        <p>
          Нагрів після наступного відновлення живлення. Це окремий одноразовий
          запит, без глобального обмеження всіх сеансів.
        </p>
        <p>
          Стан:{" "}
          <strong>
            {
              {
                inactive: "не активний",
                armed: "очікує живлення",
                cancelled: "скасований",
                expired: "прострочений",
                consumed: "спожитий",
                unknown_outcome: "результат невідомий",
              }[state.oneShot.state]
            }
          </strong>{" "}
          · епоха мережі{state.oneShot.gridEpoch}
          {state.oneShot.expires && ` · до${time(state.oneShot.expires)}`}
        </p>
        <div className="button-row">
          <button
            disabled={!permitted || state.oneShot.state === "unknown_outcome"}
            onClick={() => intent("arm")}
          >
            Запланувати один раз у симуляції
          </button>
          <button
            disabled={!permitted || state.oneShot.state !== "armed"}
            onClick={() => intent("cancel")}
          >
            Скасувати запит
          </button>
        </div>
      </details>
    </>
  );
}
