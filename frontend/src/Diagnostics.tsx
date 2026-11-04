import { useState } from "react";
import { operatorView, type OperatorAPI } from "./operator";
import { fmt, dateTime } from "./domain";
import { Badge } from "./components";
export function Diagnostics({
  api,
  open = false,
}: {
  api: OperatorAPI;
  open?: boolean;
}) {
  const [message, setMessage] = useState("");
  const { metrics } = operatorView(api);
  const m = api.model;
  const state = api.feed.value;
  const action = (kind: "train" | "promote" | "rollback" | "freeze") =>
    void Promise.resolve(api.modelAction(kind, api.session)).then(
      setMessage,
      () => setMessage("Операцію не підтверджено"),
    );
  return (
    <details open={open || undefined} className="model-details">
      <summary>Модель і діагностика</summary>
      <div className="model-overview">
        <div>
          <span className="eyebrow">Двостанна теплова модель</span>
          <h3>
            {m.revision ? `Champion v${m.revision}` : "Модель недоступна"}
          </h3>
          <p>
            Температура кімнати + запас тепла. Зворотка — непрямий індикатор, не
            температура поверхні підлоги.
          </p>
        </div>
        <Badge tone="warning">Фізична точність не доведена</Badge>
      </div>
      <div className="table-scroll">
        <table>
          <caption>Синтетичні метрики за горизонтом</caption>
          <thead>
            <tr>
              <th>Горизонт</th>
              <th>Незалежні дні</th>
              <th>Виміри</th>
              <th>MAE ·°C</th>
              <th>P90 ·°C</th>
              <th>Статус доказів</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((r) => (
              <tr key={r.hours}>
                <th scope="row">{r.hours}год</th>
                <td>{r.days}</td>
                <td>{r.samples}</td>
                <td>{fmt(r.mae, 2)}</td>
                <td>{fmt(r.p90, 2)}</td>
                <td>
                  {r.qualified
                    ? "Кваліфікований синтетичний приклад"
                    : "Перевіряється · недостатньо даних"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        Готовність базової моделі не доводить точність на24/48 год. Ціль0,3 °C
        не є обіцянкою; короткий MAE не замінює незалежний holdout.
      </p>
      <h3>Champion / challenger</h3>
      <p>
        {m.candidate
          ? "Кваліфікований синтетичний кандидат:7 train-днів,3 holdout-дні, перевірені межі та пікові помилки."
          : "Кандидат очікує даних; автоматичного підвищення немає."}{" "}
        {m.frozen
          ? "Навчання заморожено."
          : "Навчання дозволене лише в симуляції."}
      </p>
      <div className="button-row">
        <button
          disabled={!api.canChange() || m.frozen}
          onClick={() => action("train")}
        >
          Перевірити синтетичного кандидата
        </button>
        <button
          disabled={!api.canChange() || !m.candidate || m.frozen}
          onClick={() => action("promote")}
        >
          Прийняти кандидата в симуляції
        </button>
        <button
          disabled={!api.canChange() || m.revision === 3}
          onClick={() => action("rollback")}
        >
          Відкотити модель у симуляції
        </button>
        <button disabled={!api.canChange()} onClick={() => action("freeze")}>
          {m.frozen ? "Дозволити навчання" : "Заморозити навчання"}
        </button>
      </div>
      <p role="status">{message}</p>
      <p className="helper">
        Фіксований навчальний приклад, без реального fit чи застосування до
        контролера. Rollback не змінює історію або лічильники. Локальні
        навчальні слоти:10:00 та 20:45 Kyiv; зовнішні звіти не отримують прав
        запису.
      </p>
      <h3>Здоров’я окремих контурів</h3>
      <dl className="diagnostic-list">
        <dt>Вимір кімнати</dt>
        <dd>
          {state.room.quality} ·{dateTime(state.room.observed)}
        </dd>
        <dt>Синтетичний цикл</dt>
        <dd>
          {state.diagnostics.loopLagMs === null
            ? "Невідомо"
            : `${state.diagnostics.loopLagMs}мс`}{" "}
          · не замір N100
        </dd>
        <dt>Збереження</dt>
        <dd>{state.diagnostics.persistence}</dd>
        <dt>Планувальник</dt>
        <dd>{state.diagnostics.worker}</dd>
        <dt>Джерела</dt>
        <dd>{state.diagnostics.source}</dd>
        <dt>Архів: черга / втрачено</dt>
        <dd>
          {state.status.archive_pending} / {state.status.archive_lost}
        </dd>
        <dt>Власник / епоха</dt>
        <dd>Синтетичний ·{state.status.owner_epoch}</dd>
        <dt>Команда</dt>
        <dd>{state.status.receipt_stage ?? "Немає підтвердження"}</dd>
        <dt>Фізична дія</dt>
        <dd>Не перевірена</dd>
      </dl>
      <details>
        <summary>Докази відновлення енергії та безпека</summary>
        <p>
          Recovery потребує адміністратора, попереднього перегляду, незалежних
          показів лічильника, хешу доказу й точної резервної копії на
          ізольованому стенді. UI не створює енергію й не запускає імпорт.
        </p>
        <p>
          G1/B01–B08 BLOCKED. Реальна топологія, калібрування, автори команд та
          OEM-поведінка не підтверджені. Захист і STOP не залежать від відкритої
          сторінки. Причини та поля цього розділу санітизовані й обмежені.
        </p>
      </details>
    </details>
  );
}
