/** Real Home Assistant panel: read-only live state, no fake NativeAPI. */
import { createRoot, type Root } from "react-dom/client";
import { LiveApp } from "./liveApp";
import {
  LiveHAAPI,
  optionalRoles,
  type LiveHass,
  type LiveBindings,
} from "./liveHA";
import styles from "./styles.css?inline";

const roles: (keyof LiveBindings)[] = [
  "thermostat",
  "room",
  "grid",
  "voltage_l1",
  "voltage_l2",
  "voltage_l3",
  "kws_l1",
  "kws_l2",
  "kws_l3",
  "kws_energy",
];

export class HeatingAIV2Panel extends HTMLElement {
  private root?: Root;
  private api?: LiveHAAPI;
  private currentHass?: LiveHass;
  private currentPanel?: { config?: Record<string, unknown> };
  private holder?: HTMLElement;

  set hass(value: LiveHass) {
    this.currentHass = value;
    if (this.api) this.api.updateHass(value);
    else this.mount();
  }
  set panel(value: { config?: Record<string, unknown> }) {
    this.currentPanel = value;
    this.mount();
  }
  connectedCallback() {
    if (!this.root) {
      const shadow = this.shadowRoot ?? this.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      this.holder = document.createElement("div");
      style.textContent =
        styles +
        "\n:host {display:block;font-family:system-ui,sans-serif;font-variant-numeric:tabular-nums}";
      shadow.append(style, this.holder);
      this.root = createRoot(this.holder);
    }
    this.mount();
  }
  disconnectedCallback() {
    this.root?.unmount();
    this.root = undefined;
    this.api = undefined;
    this.holder = undefined;
    this.shadowRoot?.replaceChildren();
  }
  private mount() {
    if (this.api || !this.root || !this.currentHass || !this.currentPanel)
      return;
    try {
      const config = this.currentPanel.config ?? {};
      const bindings = Object.fromEntries(
        [...roles, ...optionalRoles]
          .filter((role) => typeof config[role] === "string")
          .map((role) => [role, config[role]]),
      ) as LiveBindings;
      this.api = new LiveHAAPI(
        bindings,
        this.currentHass,
        typeof config.entry_id === "string" ? config.entry_id : undefined,
      );
      this.root.render(<LiveApp api={this.api} />);
    } catch {
      this.root.render(
        <div className="app" role="alert">
          Не вдалося перевірити прив'язки до реальних датчиків. Жодних команд не
          надсилалося.
        </div>,
      );
    }
  }
}
if (!customElements.get("heating-ai-v2-panel"))
  customElements.define("heating-ai-v2-panel", HeatingAIV2Panel);
