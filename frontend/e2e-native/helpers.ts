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
export async function sourceEvent(
  page: Page,
  envelope: unknown,
  kind?: "voltage",
) {
  await page.evaluate(
    async ({ envelope, kind }) => {
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
          ...(kind ? { kind } : {}),
        },
      });
    },
    { envelope, kind },
  );
}
export async function qualifySource(page: Page, sequence: number) {
  const state = await backendStatus(page);
  await sourceEvent(page, syntheticSource(state.now, sequence));
  await expect
    .poll(async () => (await backendStatus(page)).permitted)
    .toBe(true);
}
export function syntheticVoltage(
  at: number,
  sequence: number,
  values: readonly [number, number, number] = [230, 230, 230],
  offlinePhase?: string,
) {
  return {
    phases: (["L1", "L2", "L3"] as const).map((phase, index) => ({
      phase,
      source_id: `synthetic.input.${phase}`,
      value_v: values[index],
      last_reported: at,
      received_at: at,
      sequence,
      phase_verified: true,
      online: phase !== offlinePhase,
    })),
    mapping_verified: true,
    grid_available: true,
    protection_trip: false,
    protection_last_reported: at,
    protection_qualified: true,
    feed: {
      reported_at: at,
      utility_ready: true,
      kws_online: true,
      output_ready: true,
      qualified: true,
    },
  };
}
export async function voltageEvent(
  page: Page,
  sequence: number,
  values: readonly [number, number, number] = [230, 230, 230],
  offlinePhase?: string,
) {
  const state = await backendStatus(page);
  await sourceEvent(
    page,
    syntheticVoltage(state.now, sequence, values, offlinePhase),
    "voltage",
  );
}
export async function qualifyVoltage(page: Page) {
  await page.evaluate(async () => {
    const app = document.querySelector("home-assistant") as HTMLElement & {
      hass: {
        panels: Record<string, { config: { entry_id: string } }>;
        callWS<T>(message: Record<string, unknown>): Promise<T>;
      };
    };
    const common = {
      entry_id: app.hass.panels["heating-ai"]!.config.entry_id,
      version: [2, 0],
    };
    const settings = await app.hass.callWS<import("../src/types").Persisted>({
      type: "heating_ai/settings/get",
      ...common,
    });
    const state = await app.hass.callWS<Snapshot>({
      type: "heating_ai/status",
      ...common,
    });
    const receipt = await app.hass.callWS<import("../src/types").APIReceipt>({
      type: "heating_ai/settings/save",
      ...common,
      boot_id: state.status.boot_id,
      generation: state.generation,
      owner_epoch: state.status.owner_epoch,
      request_id: `synthetic.voltage.setup.${crypto.randomUUID()}`,
      expected_revision: settings.revision,
      values: { ...settings.values, stable_recovery_s: 0 },
    });
    if (receipt.status !== "saved")
      throw Error("Synthetic voltage setup CAS failed");
    const readback = await app.hass.callWS<import("../src/types").Persisted>({
      type: "heating_ai/settings/get",
      ...common,
    });
    if (
      readback.revision !== receipt.persisted_revision ||
      readback.values.stable_recovery_s !== 0
    )
      throw Error("Synthetic voltage setup readback failed");
  });
  // Setup changed the authoritative settings revision outside the panel.
  // Bootstrap its current revision before testing user CAS edits.
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Дім", exact: true }),
  ).toBeAttached();
  await voltageEvent(page, 1);
  await expect
    .poll(async () => (await backendStatus(page)).voltage?.status)
    .toBe("NORMAL");
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
