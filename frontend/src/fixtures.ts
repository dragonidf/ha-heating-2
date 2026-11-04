import wireFixtures from "./contracts.fixture.json";
import { readForecast, readBudget, readStatus } from "./contracts";
import { qualifyCadence } from "./history";
import type {
  Settings,
  Snapshot,
  Scenario,
  Point,
  Forecast,
  EnergyInterval,
  ModelMetric,
  Energy,
} from "./types";
export const NOW = Date.parse("2026-11-04T00:00:00Z") / 1000;
export const defaults: Settings = {
  day: 21.5,
  night: 20.5,
  budget: 650,
  windowStart: "23:00",
  windowEnd: "07:00",
  strategy: "balanced",
  mode: "auto",
  circulation: "auto",
  fan: 42,
  scenario: 6,
  freshness: 30,
  aiAdvice: false,
};
export const scenarios: Record<Scenario, string> = {
  normal: "Звичайний день",
  heating: "Синтетичний нагрів",
  "device-stop": "Fake STOP при запиті нагріву",
  zero: "Відомий нуль температури",
  stale: "Застарілі дані",
  missing: "Немає виміру",
  offline: "Немає зв’язку",
  safety: "Захисна зупинка",
  manual: "Ручне втручання",
  "grid-off": "Немає електрики",
  "false-ack": "ACK без фізичного доказу",
  overspend: "Перевищення бюджету",
  "missing-original": "Прогноз отримано запізно",
  anomaly: "Конфлікт лічильника",
  fire: "Камін і нічна циркуляція",
  empty: "Порожня історія",
  "dense-history": "Щільна історія та межі обліку",
  "energy-error": "Помилка лише архіву енергії",
  "temperature-error": "Помилка лише температурної історії",
  "future-history": "Майбутні та некваліфіковані виміри",
  revoked: "Доступ відкликано",
  recovering: "Відновлення стану",
  "long-copy": "Довгий український текст",
};
export function snapshot(
  scenario: Scenario = "normal",
  seq = 1,
  generation = 1,
): Snapshot {
  const s: Snapshot = {
    version: 1,
    seq,
    generation,
    now: NOW,
    connected: true,
    permitted: true,
    status: { ...readStatus(wireFixtures.status), status_seq: seq },
    room: { value: 21.8, observed: NOW, quality: "valid" },
    grid: true,
    notices: [],
    fan: {
      phase: "Спокій",
      requested: 0,
      actual: null,
      night: true,
      fire: false,
    },
    oneShot: { state: "inactive", expires: null, gridEpoch: 4 },
    diagnostics: {
      loopLagMs: 8,
      persistence: "ok",
      worker: "ready",
      source: "valid",
    },
  };
  if (scenario === "heating") {
    s.status.actual = "heat";
    s.status.desired = "heat";
    s.status.receipt_stage = "device_echoed";
  }
  if (scenario === "device-stop") {
    s.status.actual = "stop_demand";
    s.status.desired = "heat";
    s.status.receipt_stage = "device_echoed";
    s.notices.push({
      priority: "quality",
      text: "Симулятор повідомляє STOP при запиті нагріву. Фізичну дію не підтверджено.",
    });
  }
  if (scenario === "zero") {
    s.room.value = 0;
    s.notices.push({
      priority: "comfort",
      text: "0°C — відомий синтетичний вимір, не відсутність даних. Потрібне тепло; фактичні дозволи невідомі.",
    });
  }
  if (scenario === "stale") {
    s.room.quality = "stale";
    s.room.observed -= 2100;
    s.notices.push({
      priority: "quality",
      text: "Вимір кімнати застарів. Нові запити призупинено.",
    });
  }
  if (scenario === "missing") {
    s.room.value = null;
    s.room.quality = "missing";
    s.notices.push({
      priority: "quality",
      text: "Немає свіжого виміру кімнати. Температура невідома.",
    });
  }
  if (scenario === "offline") {
    s.connected = false;
    s.status.snapshot_at -= 1800;
    s.notices.push({
      priority: "quality",
      text: "Зв’язок втрачено. Показуємо останні дані; керування недоступне.",
    });
  }
  if (scenario === "safety") {
    s.status.mode = "SAFE_HOLD";
    s.notices.push(
      {
        priority: "safety",
        text: "Захисна зупинка: перевищення допустимої температури. Фізичну зупинку не підтверджено.",
      },
      { priority: "budget", text: "Бюджет перевищено" },
    );
  }
  if (scenario === "manual") {
    s.status.mode = "MANUAL_PAUSE";
    s.status.actual = "heat";
    s.status.receipt_stage = "device_echoed";
    s.notices.push({
      priority: "manual",
      text: "Автоматика на паузі після зміни термостата.",
    });
  }
  if (scenario === "grid-off") {
    s.grid = false;
    s.notices.push({
      priority: "quality",
      text: "Електрики немає. Котел очікує відновлення; майбутній графік умовний.",
    });
  }
  if (scenario === "false-ack") {
    s.status.desired = "heat";
    s.status.receipt_stage = "ha_acknowledged";
    s.notices.push({
      priority: "quality",
      text: "Запит прийнято симулятором. Фізичне виконання не підтверджене.",
    });
  }
  if (scenario === "overspend")
    s.notices.push({
      priority: "budget",
      text: "Відомий факт уже перевищує план. Через прогалини повна сума невідома.",
    });
  if (scenario === "anomaly") {
    s.notices.push({
      priority: "quality",
      text: "Конфлікт вимірів потужності. Від’ємний баланс не перетворено на нуль.",
    });
    s.diagnostics.source = "conflicting";
    s.grid = null;
  }
  if (scenario === "fire") {
    s.fan = {
      phase: "Активне горіння",
      requested: 42,
      actual: null,
      night: true,
      fire: true,
    };
    s.notices.push({
      priority: "comfort",
      text: "Камін додає тепло. Нічна циркуляція не скасовує запит каміна.",
    });
  }
  if (scenario === "revoked") {
    s.permitted = false;
    s.notices.push({
      priority: "manual",
      text: "Доступ відкликано. Перегляд доступний, зміни заблоковані.",
    });
  }
  if (scenario === "recovering") {
    s.status.mode = "RECOVERING";
    s.diagnostics.persistence = "reconciling";
    s.notices.push({
      priority: "quality",
      text: "Відновлюємо стан. Старі запити нагріву не повторюються.",
    });
    s.oneShot.state = "unknown_outcome";
  }
  if (scenario === "long-copy")
    s.notices.push({
      priority: "quality",
      text: "Не вдалося підтвердити актуальність температури в найвіддаленішій кімнаті після відновлення зв’язку. Збережено попередні налаштування; автоматичні запити залишаються призупиненими до отримання нових перевірених даних.",
    });
  return s;
}
export const actual: readonly Point[] = Object.freeze(
  qualifyCadence(
    Array.from({ length: 745 }, (_, i) =>
      Object.freeze({
        at: NOW - (744 - i) * 3600,
        value:
          i % 103 === 0 || i % 103 === 1
            ? null
            : Math.round(
                (21.1 + 0.7 * Math.sin(i / 7) + 0.2 * Math.cos(i / 3)) * 10,
              ) / 10,
      }),
    ),
    { source: "synthetic.hourly.v1", cadenceS: 3600, qualified: true },
  ).map((p) =>
    Object.freeze({
      ...p,
      ...(p.coverage ? { coverage: Object.freeze(p.coverage) } : {}),
    }),
  ),
);
export const latest: readonly Point[] = Object.freeze(
  Array.from({ length: 25 }, (_, i) =>
    Object.freeze({
      at: NOW + i * 3600,
      value: Math.round((21.4 + 0.6 * Math.sin((i + 5) / 5)) * 10) / 10,
    }),
  ),
);
export const denseActual: readonly Point[] = Object.freeze(
  qualifyCadence(
    Array.from({ length: 31 * 288 + 1 }, (_, i) => ({
      at: NOW - 31 * 86400 + i * 300,
      value:
        i >= 4200 && i <= 4224
          ? null
          : i === 5001
            ? 26
            : i === 5002
              ? 16
              : 21 + Math.sin(i / 30),
    })),
    { source: "synthetic.five-minute.v1", cadenceS: 300, qualified: true },
  ).map((p) =>
    Object.freeze({
      ...p,
      ...(p.coverage ? { coverage: Object.freeze(p.coverage) } : {}),
    }),
  ),
);
export const boundaryIntervals: readonly EnergyInterval[] = Object.freeze([
  Object.freeze({
    start: NOW - 7800,
    end: NOW - 6600,
    kwh: 1,
    category: "confirmed",
    method: "counter_difference",
    price: null,
    tariffs: Object.freeze([
      Object.freeze({ start: NOW - 7800, end: NOW - 7200, price: 4 }),
      Object.freeze({ start: NOW - 7200, end: NOW - 6600, price: 6 }),
    ]),
  }),
]);
export const futureActual: readonly Point[] = Object.freeze(
  qualifyCadence(
    [
      { at: NOW - 3600, value: 20, quality: "valid" },
      { at: NOW - 1800, value: 77, quality: "estimated" },
      { at: NOW, value: 0, quality: "valid" },
      { at: NOW + 1, value: 88, quality: "valid" },
      { at: NOW + 3600, value: 99, quality: "valid" },
    ],
    { source: "synthetic.future-clock", cadenceS: 3600, qualified: true },
  ).map((p) =>
    Object.freeze({
      ...p,
      ...(p.coverage ? { coverage: Object.freeze(p.coverage) } : {}),
    }),
  ),
);
const frozenForecast = readForecast(
  wireFixtures.original,
  wireFixtures.original_source,
);
export const original: Forecast = Object.freeze({
  ...frozenForecast,
  points: Object.freeze(frozenForecast.points.map((p) => Object.freeze(p))),
  coverage: Object.freeze(frozenForecast.coverage),
  scope: frozenForecast.scope ? Object.freeze(frozenForecast.scope) : null,
});
export const cycleEnergy: Energy = {
  ...readBudget(wireFixtures.budget),
  estimated: 0.7,
};
export const intervals: readonly EnergyInterval[] = Object.freeze(
  Array.from({ length: 48 }, (_, i) => ({
    start: NOW - (48 - i) * 3600,
    end: NOW - (47 - i) * 3600,
    kwh: i % 13 === 0 ? null : i % 7 === 0 ? 0 : 0.35 + 0.08 * Math.sin(i),
    category:
      i % 13 === 0
        ? ("unknown" as const)
        : i % 11 === 0
          ? ("estimated" as const)
          : i % 17 === 0
            ? ("recovered" as const)
            : i % 3 === 0
              ? ("confirmed" as const)
              : ("derived" as const),
    price: i % 19 === 0 ? null : i % 24 < 7 ? 2.16 : 4.32,
  })),
);
export const metrics: readonly ModelMetric[] = Object.freeze(
  [1, 3, 6, 12, 24, 36, 48].map((hours, i) => ({
    hours,
    days: i < 3 ? 8 : i < 5 ? 3 : 0,
    samples: i < 3 ? 64 : i < 5 ? 12 : 0,
    mae: i < 3 ? 0.18 + i * 0.03 : i < 5 ? 0.4 : null,
    p90: i < 3 ? 0.35 : null,
    qualified: i < 3,
  })),
);

export const timeline: readonly import("./types").Track[] = Object.freeze([
  { start: NOW - 4 * 3600, end: NOW - 3.5 * 3600, kind: "heat" },
  { start: NOW + 3 * 3600, end: NOW + 3 * 3600 + 2400, kind: "heat" },
  { start: NOW + 8 * 3600, end: NOW + 10 * 3600, kind: "outage" },
  { start: NOW + 16 * 3600, end: NOW + 17 * 3600, kind: "heat" },
]);
