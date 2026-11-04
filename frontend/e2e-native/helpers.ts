import { expect, type Page } from "@playwright/test";
import type { Snapshot } from "../src/types";
import sourceFixture from "./source.fixture.json" with { type: "json" };

/** Base bytes exported through the accepted Python WP2A SourceEvent codec. */
export function syntheticSource(at: number, sequence: number, value = 21) {
  return {
    ...sourceFixture,
    data: {
      ...sourceFixture.data,
      identity: `native-browser-${sequence}`,
      received_at: at,
      sequence,
      reading: {
        ...sourceFixture.data.reading,
        value,
        observed_at: at,
        received_at: at,
      },
    },
  };
}
export async function backendStatus(page: Page): Promise<Snapshot> {
  return page.evaluate(async () => {
    const app = document.querySelector("home-assistant") as HTMLElement & {
      hass: {
        panels: Record<string, { config: { entry_id: string } }>;
        callWS<T>(message: Record<string, unknown>): Promise<T>;
      };
    };
    return app.hass.callWS<Snapshot>({
      type: "heating_ai/status",
      entry_id: app.hass.panels["heating-ai"]!.config.entry_id,
      version: [2, 0],
    });
  });
}
export async function sourceEvent(page: Page, envelope: unknown) {
  await page.evaluate(async (envelope) => {
    const app = document.querySelector("home-assistant") as HTMLElement & {
      hass: {
        panels: Record<string, { config: { entry_id: string } }>;
        callWS<T>(message: Record<string, unknown>): Promise<T>;
      };
    };
    await app.hass.callWS({
      type: "fire_event",
      event_type: "heating_ai_synthetic_sample",
      event_data: {
        entry_id: app.hass.panels["heating-ai"]!.config.entry_id,
        envelope,
      },
    });
  }, envelope);
}
export async function qualifySource(page: Page, sequence: number) {
  const state = await backendStatus(page);
  await sourceEvent(page, syntheticSource(state.now, sequence));
  await expect
    .poll(async () => (await backendStatus(page)).permitted)
    .toBe(true);
}
/** Resolve each shadow boundary; a document-only selector cannot scope the native panel. */
export function shadowContext(element: Element): {
  fromShadowDom: [string, string, ...string[]];
} {
  const selectors: string[] = [".app"];
  let current = element;
  while (true) {
    const root = current.getRootNode();
    if (!(root instanceof Document || root instanceof ShadowRoot))
      throw Error("Detached panel accessibility context");
    const parts: string[] = [];
    for (let node: Element | null = current; node; node = node.parentElement) {
      let part = node.localName;
      const siblings = node.parentElement?.children ?? root.children;
      const same = Array.from(siblings).filter(
        (sibling) => sibling.localName === node!.localName,
      );
      if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
      parts.unshift(part);
      if (root.querySelectorAll(parts.join(" > ")).length === 1) break;
    }
    const selector = parts.join(" > ");
    if (root.querySelector(selector) !== current)
      throw Error("Ambiguous panel accessibility context");
    selectors.unshift(selector);
    if (root instanceof Document) break;
    current = root.host;
  }
  if (selectors.length < 2) throw Error("Missing native panel shadow boundary");
  return { fromShadowDom: selectors as [string, string, ...string[]] };
}
