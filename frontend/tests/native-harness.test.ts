import { expect, it } from "vitest";
import { shadowContext, syntheticSource } from "../e2e-native/helpers";
it("builds axe context through every HA shadow boundary to the owned app", () => {
  const host = document.createElement("home-assistant");
  document.body.append(host);
  const outer = host.attachShadow({ mode: "open" }),
    layout = document.createElement("ha-main");
  outer.append(layout);
  const inner = layout.attachShadow({ mode: "open" }),
    panel = document.createElement("heating-ai-panel");
  inner.append(panel);
  panel.attachShadow({ mode: "open" }).innerHTML = '<main class="app"></main>';
  expect(shadowContext(panel)).toEqual({
    fromShadowDom: ["home-assistant", "ha-main", "heating-ai-panel", ".app"],
  });
  host.remove();
});
it("qualifies synthetic source timestamps without mutating the codec fixture", () => {
  const first = syntheticSource(100, 1),
    second = syntheticSource(200, 2, 0);
  expect(first.version).toEqual([2, 0]);
  expect(first.type).toBe("SourceEvent");
  expect(first.data.entity).toBe("synthetic.native.room");
  expect(first.data.author).toBe("sensor");
  expect(first.data.reading.observed_at).toBe(100);
  expect(first.data.reading.received_at).toBe(100);
  expect(first.data.received_at).toBe(100);
  expect(second.data.sequence).toBe(2);
  expect(second.data.reading.value).toBe(0);
  expect(first.data.reading.value).toBe(21);
  expect(second.data.reading.provenance).toEqual({
    components: [],
    independent: true,
    kind: "direct",
  });
});
