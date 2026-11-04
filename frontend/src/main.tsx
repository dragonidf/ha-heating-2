import { createRoot } from "react-dom/client";
import { App } from "./App";
import { DemoAPI } from "./mock";
import { BrowserStore } from "./storage";
import { readStatus } from "./contracts";
import fixtures from "./contracts.fixture.json";
import "./styles.css";
const api = new DemoAPI(new BrowserStore());
// Canonical Python-produced envelopes are checked before any controls render.
const root = createRoot(document.getElementById("root")!);
try {
  readStatus(fixtures.status);
  root.render(<App api={api} />);
} catch {
  root.render(
    <main role="alert">
      <h1>Дані несумісні з інтерфейсом</h1>
      <p>Керування заблоковано. Перевірте версію локального пакета.</p>
    </main>,
  );
}
