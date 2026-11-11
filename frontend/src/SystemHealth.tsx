import { dateTime } from "./domain";
import type { SystemHealthView } from "./types";
const actions: Record<string, string> = {
  NORMAL: "Плановий режим",
  AUTO_PROPOSED: "Запропоновано резервний AUTO",
  HEAT_PROPOSED: "Запропоновано повернення HEAT",
  RECOVERING: "Перевіряємо відновлення",
  ELECTRICAL_INHIBIT: "Нагрів заблокований електрозахистом",
  WAITING: "Очікування даних",
  BLOCKED: "STOP або недоступний власник/контролер",
};
export function SystemHealth({ health }: { health: SystemHealthView }) {
  const f = health.source_freshness;
  const ceiling = health.thermostat_ceiling;
  const temperature = (v: number | null) =>
    v === null ? "невідомо" : `${v}°C`;
  const age = (v: number | null) =>
    v === null ? "давність невідома" : `${Math.floor(v)} с`;
  const quality = (v: string) =>
    v === "OK"
      ? "OK"
      : v === "OFFLINE"
        ? "Проблема: джерело недоступне"
        : "Очікування даних";
  const problems = health.components.filter((c) => c.status === "PROBLEM");
  const waiting = health.components.filter((c) => c.status === "WAITING");
  const highest =
    problems.find((c) => c.key === "utility") ??
    problems.find((c) => c.key === "controller") ??
    problems[0] ??
    waiting.find((c) => c.key === "utility") ??
    waiting[0];
  return (
    <section className="card" aria-label="Стан системи">
      {highest && (
        <p role={problems.length ? "alert" : "status"}>
          {highest.label}: {highest.reason}
        </p>
      )}
      <details>
        <summary>
          <strong>Стан системи</strong> · OK{" "}
          {health.components.length - problems.length - waiting.length} ·
          Проблема {problems.length} · Очікування {waiting.length}
        </summary>
        <ul>
          {health.components.map((c) => (
            <li key={c.key}>
              <strong>{c.label}</strong>:{" "}
              {c.status === "PROBLEM"
                ? "Проблема"
                : c.status === "WAITING"
                  ? "Очікування"
                  : "OK"}{" "}
              · {c.reason} ·{" "}
              {c.age_s === null
                ? "Давність невідома"
                : `${Math.floor(c.age_s)} с`}{" "}
              · {actions[c.fallback_action] ?? "Дія не підтверджена"}
            </li>
          ))}
        </ul>
        {f && (
          <div aria-label="Достовірність джерел">
            <p>
              Активність пристрою T&H: {quality(f.device_quality)} ·{" "}
              {age(f.device_age_s)}
            </p>
            <p>
              Реальний вимір вітальні: {quality(f.temperature_quality)} ·{" "}
              {age(f.temperature_age_s)}
            </p>
            <p>
              Зовнішній щуп обратки: {quality(f.return_quality)} ·{" "}
              {age(f.return_age_s)} · лише допоміжне джерело
              {f.return_veto ? "; вето нагріву" : ""}
            </p>
            <p>
              Поріг активності {f.activity_window_s} с — лише попередження.
              Вологість не оновлює температуру.
            </p>
          </div>
        )}
        {f?.measurement_authorization_age_s !== undefined && (
          <p>
            Дозвіл виміру: {f.measurement_authorization_age_s} с · стабілізація:{" "}
            {f.recovery_dwell_s} с ·
            {f.recovery_policy_ready
              ? "політика симуляції придатна"
              : "відновлення BLOCKED"}
            . Фізичні команди вимкнені.
          </p>
        )}
        {health.passive_sources?.map((p) => (
          <p key={p.role}>
            Пасивне джерело{" "}
            {
              {
                temperature: "Вітальня",
                humidity: "Вологість T&H",
                return_water: "Щуп обратки",
              }[p.role]
            }
            : {p.available ? p.value : "недоступне"} · запис HA:{" "}
            {dateTime(p.last_reported)} · оновлення: {dateTime(p.last_updated)}{" "}
            · зміна значення: {dateTime(p.last_changed)}. Фізичний вимір
            BLOCKED; запис HA не є виміром пристрою.
          </p>
        ))}
        {ceiling && (
          <div aria-label="Резервний максимум термостата">
            <strong>Резервний максимум термостата</strong>
            <p>
              Активна верхня межа вітальні: {temperature(ceiling.room_upper_c)}{" "}
              · режим:{" "}
              {{
                day: "День",
                night: "Ніч",
                allowed_hours: "Дозволені години",
                override: "Ефективне перевизначення",
              }[ceiling.source_mode ?? ""] ??
                ceiling.source_mode ??
                "невідомо"}
            </p>
            <p>
              Запас: {temperature(ceiling.reserve_margin_c)} · розрахункова
              межа: {temperature(ceiling.ceiling_raw_c)} · допустимий максимум
              setpoint: {temperature(ceiling.proposed_ceiling_c)}
            </p>
            <p>
              Запропонований setpoint:{" "}
              {temperature(ceiling.proposed_setpoint_c)} · фізичне застосування
              та ACK не підтверджені.
            </p>
            <p>
              {ceiling.thermostat_fresh
                ? "Свіжість термостата підтверджена в симуляції"
                : "Очікуємо свіжі дані термостата"}{" "}
              ·
              {ceiling.action === "withdraw_demand"
                ? "Запропоновано зняття запиту нагріву"
                : ceiling.action === "request_heat"
                  ? "Запит планувальника обмежений резервним максимумом"
                  : "Нагрів не підтверджений"}
            </p>
            {ceiling.reason === "room_target_or_upper_reached" && (
              <p>Досягнута ціль вітальні.</p>
            )}
            {ceiling.thermostat_mode === "AUTO" && (
              <p>Тижневий AUTO не підкоряється цій межі ручного HEAT.</p>
            )}
          </div>
        )}
        <p>
          Дії лише запропоновані в симуляції. Фізичний стан не підтверджений.
        </p>
      </details>
      {(health.last_notice ?? health.notification) && (
        <p role="status">
          Останнє повідомлення: {health.last_notice ?? health.notification}
        </p>
      )}
    </section>
  );
}
