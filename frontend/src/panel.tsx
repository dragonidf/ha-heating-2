import { createRoot, type Root } from "react-dom/client";
import { App } from "./App";
import { NativeAPI, type Hass } from "./nativeAdapter";
import styles from "./styles.css?inline";
/** HA injects the authenticated session and panel config into this custom element. */
export class HeatingAIPanel extends HTMLElement {
  private root?: Root;
  private api?: NativeAPI;
  private currentHass?: Hass;
  private currentPanel?: { config?: { entry_id?: string } };
  private mounted = false;
  private attempt = 0;
  set hass(value: Hass) {
    const previous = this.currentHass;
    this.currentHass = value;
    if (
      this.api &&
      previous?.connection === value.connection &&
      previous?.user?.id === value.user?.id
    ) {
      this.api.updateConnection(value.connected !== false, value);
      return;
    }
    this.setup();
  }
  set panel(value: { config?: { entry_id?: string } }) {
    this.currentPanel = value;
    this.setup();
  }
  connectedCallback() {
    this.mounted = true;
    if (!this.root) {
      const shadow = this.shadowRoot ?? this.attachShadow({ mode: "open" }),
        style = document.createElement("style"),
        mount = document.createElement("div");
      style.textContent =
        styles +
        "\n:host { display:block; font-family:system-ui,sans-serif; font-variant-numeric:tabular-nums; }";
      shadow.append(style, mount);
      this.root = createRoot(mount);
    }
    this.setup();
  }
  disconnectedCallback() {
    this.mounted = false;
    this.attempt++;
    this.api?.close();
    this.api = undefined;
    this.root?.unmount();
    this.root = undefined;
    this.shadowRoot?.replaceChildren();
  }
  private setup() {
    if (!this.mounted || !this.currentHass || !this.currentPanel || !this.root)
      return;
    const attempt = ++this.attempt;
    this.api?.close();
    this.root.render(
      <div className="app" data-theme="dark">
        <p role="status">Читаємо ізольовану симуляцію Home Assistant…</p>
      </div>,
    );
    try {
      const api = new NativeAPI(
        this.currentHass,
        this.currentPanel.config?.entry_id ?? "",
      );
      this.api = api;
      void api.start().then(
        () => {
          if (this.mounted && attempt === this.attempt)
            this.root?.render(<App api={api} />);
        },
        () => this.failure(attempt),
      );
    } catch {
      this.failure(attempt);
    }
  }
  private failure(attempt: number) {
    if (!this.mounted || attempt !== this.attempt) return;
    this.root?.render(
      <div className="app" data-theme="dark">
        <p role="alert">
          Стан Home Assistant недоступний або доступ відкликано. Керування
          заблоковано.
        </p>
        <button onClick={() => this.setup()}>Повторити читання</button>
      </div>,
    );
  }
}
if (!customElements.get("heating-ai-panel"))
  customElements.define("heating-ai-panel", HeatingAIPanel);
