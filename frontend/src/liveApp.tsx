/** Native three-tab live application; no DemoAPI or simulated persistence. */
import { useRef, useState, useSyncExternalStore } from "react";
import { Icon, Badge } from "./components";
import { LiveHome, LiveHistory, LiveSettings } from "./livePages";
import type { LiveHAAPI } from "./liveHA";

export function LiveApp({ api }: { api: LiveHAAPI }) {
  const state = useSyncExternalStore(api.feed.subscribe, () => api.feed.value);
  const [tab, setTab] = useState<"home" | "history" | "settings">("home");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const main = useRef<HTMLElement>(null);
  const navigate = (next: typeof tab) => {
    setTab(next);
    requestAnimationFrame(() => main.current?.focus());
  };
  return (
    <div className="app" data-theme={theme}>
      <a
        className="skip-link"
        href="#live-main"
        onClick={(e) => {
          e.preventDefault();
          main.current?.focus();
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
          <Badge tone="control">Реальні дані · native HA · керування OFF</Badge>
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
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} />
        </button>
      </header>
      <div className="connection-bar">
        <span>
          {state.connected
            ? "Home Assistant · реальні датчики"
            : "Немає зв'язку · останні показники"}
        </span>
        <span>Новий контролер: native backend · physical OFF</span>
      </div>
      <main id="live-main" ref={main} tabIndex={-1}>
        {api.dataErrors.map((msg) => (
          <p key={msg} className="helper">
            {msg}
          </p>
        ))}
        {tab === "home" ? (
          <LiveHome api={api} state={state} />
        ) : tab === "history" ? (
          <LiveHistory api={api} />
        ) : (
          <LiveSettings api={api} />
        )}
      </main>
    </div>
  );
}
