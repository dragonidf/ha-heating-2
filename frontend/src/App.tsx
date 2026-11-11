import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Home } from "./Home";
import { History } from "./History";
import { Settings } from "./Settings";
import { DemoAPI } from "./mock";
import { LiveHAAPI } from "./liveHA";
import { LiveHome, LiveHistory, LiveSettings } from "./livePages";
import { BrowserStore } from "./storage";
import { useSettings } from "./useSettings";
import { Icon, Badge } from "./components";
import { scenarios } from "./fixtures";
import { dateTime } from "./domain";
import type { Scenario } from "./types";
import type { OperatorAPI } from "./operator";
export function App({
  api = new DemoAPI(new BrowserStore()),
}: {
  api?: OperatorAPI;
}) {
  return <OperatorApp api={api} />;
}
function OperatorApp({ api }: { api: OperatorAPI }) {
  const demo = api instanceof DemoAPI ? api : null;
  const live = api instanceof LiveHAAPI ? api : null;
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!demo) return;
    const offline = () => demo.setScenario("offline");
    window.addEventListener("offline", offline);
    if (!navigator.onLine) offline();
    return () => window.removeEventListener("offline", offline);
  }, [api, demo]);
  const state = useSyncExternalStore(api.feed.subscribe, () => api.feed.value);
  const controller = useSettings(api);
  const [tab, setTab] = useState<"home" | "history" | "settings">("home"),
    [modelOpen, setModelOpen] = useState(false),
    [theme, setTheme] = useState("dark"),
    [driverMessage, setDriverMessage] = useState(""),
    [connectionMessage, setConnectionMessage] = useState("");
  const reconnect = async () => {
    setConnectionMessage("");
    try {
      await api.reconnect();
    } catch {
      setConnectionMessage(
        "Зв’язок не відновлено. Останні дані лише для читання.",
      );
    }
  };
  const navigate = (next: typeof tab, model = false) => {
    setTab(next);
    setModelOpen(model);
    requestAnimationFrame(() => {
      mainRef.current?.focus();
    });
  };
  const model = () => navigate("settings", true);
  return (
    <div className="app" data-theme={theme}>
      <a
        className="skip-link"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          mainRef.current?.focus();
        }}
      >
        До основного вмісту
      </a>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="fire" />
          </div>
          <div>
            <strong>
              Heating<span>AI</span>
            </strong>
            <span className="brand-caption">Комфорт під контролем</span>
          </div>
          <Badge tone="control">{live ? "Реальні HA-дані · без керування" : "Симуляція"}</Badge>
        </div>
        <nav className="main-nav" aria-label="Основні вкладки">
          {(
            [
              ["home", "Дім"],
              ["history", "Історія"],
              ["settings", "Налаштування"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              aria-current={tab === id ? "page" : undefined}
              onClick={() => navigate(id)}
            >
              <Icon name={id} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <button
          className="theme-button"
          aria-label={
            theme === "dark" ? "Увімкнути світлу тему" : "Увімкнути темну тему"
          }
          onClick={() => setTheme((v) => (v === "dark" ? "light" : "dark"))}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} />
        </button>
      </header>
      <div className="connection-bar">
        <span>
          {state.connected
            ? api.native
              ? live ? "Home Assistant · реальні датчики" : "Home Assistant · ізольована симуляція"
              : "Локальна симуляція"
            : "Немає зв’язку · останні дані"}
        </span>
        <span>{dateTime(state.status.snapshot_at)}</span>
        {!state.connected && (
          <button onClick={() => void reconnect()}>{live ? "Оновити дані" : "Відновити симуляцію"}</button>
        )}
      </div>
      <main id="main" ref={mainRef} tabIndex={-1}>
        {connectionMessage && <p role="alert">{connectionMessage}</p>}
        {api.dataErrors?.map((error) => (
          <p role="alert" key={error}>
            {error}
          </p>
        ))}
        {!live && api.native && !state.permitted && (
          <div className="notice safety" role="status">
            Лише читання. Симуляція вимкнена або немає дозволу адміністратора.
            Фізичне керування заблоковане. G1/B01–B08 BLOCKED.
          </div>
        )}
        {!live && controller.error && (
          <div className="notice safety" role="alert">
            <p>Збережені налаштування не прочитані. Зміни заблоковано.</p>
            <button onClick={() => void controller.load()}>
              Повторити читання
            </button>
          </div>
        )}
        {live ? (
          tab === "home" ? <LiveHome api={live} state={state} /> :
          tab === "history" ? <LiveHistory /> : <LiveSettings api={live} />
        ) : tab === "home" ? (
          <Home
            state={state}
            api={api}
            settings={controller}
            onHistory={() => navigate("history")}
          />
        ) : tab === "history" ? (
          <History api={api} state={state} onModel={model} />
        ) : (
          <Settings api={api} controller={controller} modelOpen={modelOpen} />
        )}
      </main>
      <footer>
        {demo && (
          <details className="simulation-lab">
            <summary>Сценарії демо · синтетичні дані</summary>
            <p>
              Ці перемикачі змінюють лише локальні fixtures. Немає підключення
              до будинку чи обладнання.
            </p>
            <div className="form-grid">
              <label>
                Сценарій
                <select
                  aria-label="Сценарій"
                  value={demo.scenario}
                  onChange={(e) => {
                    demo.setScenario(e.target.value as Scenario);
                    setDriverMessage("");
                  }}
                >
                  {Object.entries(scenarios).map(([v, label]) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Відмова запису
                <select
                  aria-label="Відмова запису"
                  value={demo.fault}
                  onChange={(e) => {
                    demo.fault = e.target.value as DemoAPI["fault"];
                    setDriverMessage(
                      `Відмова: ${e.target.selectedOptions[0]?.text}`,
                    );
                  }}
                >
                  <option value="none">Немає</option>
                  <option value="write">Запис недоступний</option>
                  <option value="readback">Не підтверджено читання</option>
                  <option value="timeout">Перевищення часу</option>
                </select>
              </label>
            </div>
            <div className="button-row">
              <button
                onClick={() => {
                  api.feed.accept({ ...state, seq: state.seq + 2 });
                  setDriverMessage(
                    "Прогалина послідовності: потрібен новий повний стан",
                  );
                }}
              >
                Пропустити подію
              </button>
              <button
                onClick={() => {
                  api.feed.accept({ ...state, seq: state.seq - 1 });
                  setDriverMessage("Стару подію відкинуто");
                }}
              >
                Надіслати стару подію
              </button>
              <button onClick={() => void reconnect()}>
                Новий повний стан
              </button>
              <button
                onClick={() => {
                  const other = new DemoAPI(new BrowserStore(), 0);
                  void other
                    .settings()
                    .then((p) =>
                      other.save(
                        "synthetic.other." + crypto.randomUUID(),
                        p.revision,
                        { ...p.values, day: p.values.day === 23 ? 22 : 23 },
                        other.session,
                      ),
                    )
                    .then(() =>
                      setDriverMessage(
                        "Інше синтетичне вікно зберегло нову версію. Поточну чернетку не змінено.",
                      ),
                    )
                    .catch(() =>
                      setDriverMessage("Інше вікно не підтвердило запис."),
                    );
                }}
              >
                Інше вікно зберігає
              </button>
            </div>
            <div className="button-row">
              <button
                onClick={() =>
                  setDriverMessage(demo.control("consume", demo.session).reason)
                }
              >
                Спожити одноразовий запит у симуляції
              </button>
              <button
                onClick={() =>
                  setDriverMessage(demo.control("expire", demo.session).reason)
                }
              >
                Синтетичне прострочення запиту
              </button>
            </div>
            <p role="status">{driverMessage}</p>
          </details>
        )}
        <p>
          Heating AI 2.0 ·{" "}
          {api.native ? "ізольований Home Assistant" : "офлайн-демо"} · без
          фізичного керування
        </p>
      </footer>
    </div>
  );
}
