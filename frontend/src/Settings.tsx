import { useState } from "react";
import { Card, Badge } from "./components";
import { validateSettings, fmt } from "./domain";
import type { DemoAPI } from "./mock";
import type { SettingsController } from "./useSettings";
import type { Settings as Values } from "./types";
import { Diagnostics } from "./Diagnostics";
export function Settings({
  api,
  controller,
  modelOpen = false,
}: {
  api: DemoAPI;
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
              <dl>
                <dt>Денна ціль: збережено / чернетка</dt>
                <dd>
                  {fmt(c.conflict.values.day)} / {fmt(s.day)}°C
                </dd>
                <dt>Бюджет: збережено / чернетка</dt>
                <dd>
                  {fmt(c.conflict.values.budget)} / {fmt(s.budget)}
                </dd>
              </dl>
              <button type="button" onClick={c.rebase}>
                Взяти нову версію за основу, зберегти чернетку
              </button>
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
                  locked || errors.length > 0 || !changed || !!c.conflict
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
