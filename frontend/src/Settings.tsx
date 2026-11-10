import { useState } from "react";
import { Card, Badge } from "./components";
import { validateSettings } from "./domain";
import type { OperatorAPI } from "./operator";
import type { SettingsController } from "./useSettings";
import type { Settings as Values } from "./types";
import { Diagnostics } from "./Diagnostics";
import { voltageValues, voltageRanges, withVoltageSettings } from "./voltage";
import type { VoltageSettings } from "./types";
export function Settings({
  api,
  controller,
  modelOpen = false,
}: {
  api: OperatorAPI;
  controller: SettingsController;
  modelOpen?: boolean;
}) {
  const [search, setSearch] = useState("");
  const c = controller,
    s = c.draft;
  const errors = validateSettings(s);
  const locked = !api.canChange() || c.pending || !c.saved;
  const edit = <K extends keyof Values>(key: K, value: Values[K]) =>
    c.edit({ ...s, [key]: value });
  const changed =
    !!c.saved && JSON.stringify(s) !== JSON.stringify(c.saved.values);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Ваш комфорт, прозорі правила</p>
          <h1>Налаштування</h1>
        </div>
        <Badge>Лише симуляція</Badge>
      </div>
      <Card
        title="Комфорт і розклад"
        aside={
          <span className="helper">Версія {c.saved?.revision ?? "—"}</span>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void c.save();
          }}
        >
          <fieldset disabled={locked}>
            <legend className="sr-only">Основні налаштування симуляції</legend>
            <div className="form-grid">
              <label>
                Температура вдень ·°C
                <input
                  name="day"
                  type="number"
                  min="16"
                  max="26"
                  step="0.5"
                  value={s.day}
                  onChange={(e) => edit("day", e.target.valueAsNumber)}
                />
                <span className="helper">Комфортна ціль, не уставка котла</span>
              </label>
              <label>
                Температура під час сну ·°C
                <input
                  name="night"
                  type="number"
                  min="16"
                  max="26"
                  step="0.5"
                  value={s.night}
                  onChange={(e) => edit("night", e.target.valueAsNumber)}
                />
                <span className="helper">Не вище денної</span>
              </label>
              <label>
                Дозволене вікно · початок
                <input
                  type="time"
                  value={s.windowStart}
                  onChange={(e) => edit("windowStart", e.target.value)}
                />
              </label>
              <label>
                Дозволене вікно · кінець
                <input
                  type="time"
                  value={s.windowEnd}
                  onChange={(e) => edit("windowEnd", e.target.value)}
                />
              </label>
              <label>
                Стратегія
                <select
                  value={s.strategy}
                  onChange={(e) =>
                    edit("strategy", e.target.value as Values["strategy"])
                  }
                >
                  <option value="comfort">Комфорт</option>
                  <option value="balanced">Баланс</option>
                  <option value="economy">Економія</option>
                </select>
              </label>
              <label>
                М’який бюджет на місяць ·кВт·год
                <input
                  type="number"
                  min="0"
                  max="2000"
                  value={s.budget}
                  onChange={(e) => edit("budget", e.target.valueAsNumber)}
                />
              </label>
              <label>
                Режим симуляції
                <select
                  value={s.mode}
                  onChange={(e) =>
                    edit("mode", e.target.value as Values["mode"])
                  }
                >
                  <option value="auto">Автоматичний розрахунок</option>
                  <option value="observation">Спостереження</option>
                </select>
                <span className="helper">Жодної команди обладнанню</span>
              </label>
              <label>
                Циркуляція
                <select
                  value={s.circulation}
                  onChange={(e) =>
                    edit("circulation", e.target.value as Values["circulation"])
                  }
                >
                  <option value="auto">Авто за потребою</option>
                  <option value="manual">Ручний запит симуляції</option>
                  <option value="stop">Зняти автоматичний запит</option>
                </select>
              </label>
            </div>
          </fieldset>
          {api.native && (
            <fieldset disabled={locked}>
              <legend>Вхідна напруга мережі · синтетичні межі</legend>
              <p>
                Захист запиту нагріву використовує три фази вхідного лічильника
                Zigbee2MQTT input 220. Це не напруга на клемах котла.
                Налаштування не змінюють апаратний захист KWS, насос або
                OEM-захисти.
              </p>
              {s.min_voltage_v === undefined && (
                <p className="helper">
                  Показано синтетичні типові межі. Сервер має підтвердити їх
                  міграцію або нове збереження.
                </p>
              )}
              <div className="form-grid">
                {(
                  [
                    ["min_voltage_v", "Мінімальна вхідна напруга · В"],
                    ["max_voltage_v", "Максимальна вхідна напруга · В"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      type="number"
                      name={key}
                      min={voltageRanges[key][0]}
                      max={voltageRanges[key][1]}
                      step="any"
                      value={voltageValues(s)[key]}
                      onChange={(e) =>
                        c.edit(
                          withVoltageSettings(s, key, e.target.valueAsNumber),
                        )
                      }
                    />
                  </label>
                ))}
              </div>
              <details>
                <summary>Експертні межі відновлення напруги</summary>
                <div className="form-grid">
                  {(
                    [
                      ["hysteresis_v", "Гістерезис напруги · В"],
                      ["stable_recovery_s", "Стабільне відновлення · с"],
                      ["voltage_max_age_s", "Граничний вік звіту напруги · с"],
                    ] as [keyof VoltageSettings, string][]
                  ).map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <input
                        type="number"
                        name={key}
                        min={voltageRanges[key][0]}
                        max={voltageRanges[key][1]}
                        step="any"
                        value={voltageValues(s)[key]}
                        onChange={(e) =>
                          c.edit(
                            withVoltageSettings(s, key, e.target.valueAsNumber),
                          )
                        }
                      />
                    </label>
                  ))}
                </div>
              </details>
              <p className="helper">
                Значення рівно на мінімумі або максимумі не порушують зовнішню
                межу. Після блокування потрібні всі три свіжі фази в межах
                мінімум + гістерезис … максимум − гістерезис протягом усього
                стабільного періоду. Повертається лише допустимість запиту;
                автоматичного нагріву чи скасування ручної паузи немає.
              </p>
            </fieldset>
          )}
          {errors.length > 0 && (
            <ul className="validation" role="alert">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          {c.conflict && (
            <div className="conflict" role="alert">
              <h3>Налаштування змінилися в іншому вікні</h3>
              <p>
                Чернетку збережено на екрані. Поточна версія
                {c.conflict.revision}, ваша{c.saved?.revision}. Після порівняння
                повторне збереження має бути явним.
              </p>
              <div className="table-scroll">
                <table>
                  <caption>
                    Усі параметри: основа, ваша чернетка та нова версія
                  </caption>
                  <thead>
                    <tr>
                      <th>Параметр</th>
                      <th>Основа</th>
                      <th>Чернетка</th>
                      <th>Нова версія</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.differences.map((f) => (
                      <tr key={JSON.stringify(f.path)}>
                        <th scope="row">{fieldLabel(f.path)}</th>
                        <td>{display(f.base)}</td>
                        <td>{display(f.local)}</td>
                        <td>
                          {display(f.remote)}
                          {f.collision ? " · потрібен вибір" : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button type="button" onClick={c.rebase}>
                Взяти нову версію за основу, зберегти чернетку
              </button>
            </div>
          )}
          {c.collisions.length > 0 && (
            <div className="conflict" role="alert">
              <h3>Оберіть значення кожного спільного редагування</h3>
              {c.collisions.map((f) => (
                <fieldset key={JSON.stringify(f.path)} disabled={c.pending}>
                  <legend>{fieldLabel(f.path)}</legend>
                  <p>
                    Основа: {display(f.base)} · ваша чернетка:{" "}
                    {display(f.local)} · нова версія: {display(f.remote)}
                  </p>
                  <button
                    type="button"
                    onClick={() => c.resolve(f.path, "local")}
                  >
                    Залишити моє: {fieldLabel(f.path)}
                  </button>
                  <button
                    type="button"
                    onClick={() => c.resolve(f.path, "remote")}
                  >
                    Прийняти нове: {fieldLabel(f.path)}
                  </button>
                </fieldset>
              ))}
            </div>
          )}
          <div className="save-bar">
            <span className="helper">
              {changed
                ? "Є незбережені зміни"
                : "Чернетка відповідає збереженому стану"}
            </span>
            <div className="button-row">
              <button type="button" onClick={c.undo} disabled={c.pending}>
                Повернути чернетку
              </button>
              <button type="button" onClick={c.cancel} disabled={c.pending}>
                Скасувати
              </button>
              <button
                className="primary"
                disabled={
                  locked ||
                  errors.length > 0 ||
                  !changed ||
                  !!c.conflict ||
                  c.collisions.length > 0
                }
                type="submit"
              >
                {c.pending ? "Перевіряємо запис…" : "Зберегти симуляцію"}
              </button>
            </div>
          </div>
          <p className="feedback" role="status">
            {c.message}
          </p>
          {c.error && (
            <button type="button" onClick={() => void c.load()}>
              Перечитати збережений стан
            </button>
          )}
        </form>
      </Card>
      <Card title="Експертні параметри">
        <label>
          Знайти параметр
          <input
            type="search"
            value={search}
            placeholder="Модель, датчики, калібрування…"
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        {(!search || /датч|тополог|калібр|потуж|свіж|фізич/i.test(search)) && (
          <details>
            <summary>Датчики, свіжість і фізичний профіль</summary>
            <p>
              Фізична схема й калібрування не підтверджені. Профіль не перемикає
              ТЕНи; потрібна окрема перевірка обладнання.
            </p>
            <div className="form-grid">
              <label>
                Розрахунковий сценарій потужності
                <select
                  disabled={locked}
                  value={s.scenario}
                  onChange={(e) =>
                    edit(
                      "scenario",
                      Number(e.target.value) as Values["scenario"],
                    )
                  }
                >
                  <option value="3">3кВт · непідтверджений сценарій</option>
                  <option value="6">6кВт · непідтверджений сценарій</option>
                  <option value="9">9кВт · непідтверджений сценарій</option>
                </select>
              </label>
              <label>
                Гранична давність ·с
                <input
                  disabled={locked}
                  type="number"
                  min="5"
                  max="300"
                  value={s.freshness}
                  onChange={(e) => edit("freshness", e.target.valueAsNumber)}
                />
              </label>
            </div>
            <p className="helper">
              Синтетичні джерела: кімната, зворотка, мережа. Реальних entity ID,
              адрес і токенів немає. Баланс не включає перекривні групи двічі.
            </p>
          </details>
        )}
        {(!search || /модел|діагност|навчан|ai|безпек/i.test(search)) && (
          <Diagnostics api={api} open={modelOpen} />
        )}
        <details>
          <summary>Поради AI й fail-safe</summary>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={s.aiAdvice}
              disabled={locked}
              onChange={(e) => edit("aiAdvice", e.target.checked)}
            />
            Показувати синтетичні пояснення
          </label>
          <p>
            Порада не може змінювати захисти, модель чи видавати команди. При
            невідомому результаті повторний нагрів не запускається.
          </p>
        </details>
      </Card>
    </>
  );
}
function display(value: unknown): string {
  return value === undefined
    ? "Відсутнє"
    : typeof value === "string"
      ? value
      : JSON.stringify(value);
}
function fieldLabel(path: string[]): string {
  const labels: Record<string, string> = {
    day: "Денна ціль",
    night: "Ціль сну",
    budget: "Бюджет",
    windowStart: "Початок вікна",
    windowEnd: "Кінець вікна",
    strategy: "Стратегія",
    mode: "Режим",
    circulation: "Циркуляція",
    fan: "Запит вентилятора",
    scenario: "Сценарій потужності",
    freshness: "Давність даних",
    aiAdvice: "Пояснення AI",
    min_voltage_v: "Мінімальна вхідна напруга",
    max_voltage_v: "Максимальна вхідна напруга",
    hysteresis_v: "Гістерезис напруги",
    stable_recovery_s: "Стабільне відновлення",
    voltage_max_age_s: "Граничний вік звіту напруги",
  };
  return path.length === 1 ? (labels[path[0]!] ?? path[0]!) : path.join(" / ");
}
