import { it, expect, afterEach } from "vitest";
import { renderHook, waitFor, act, cleanup } from "@testing-library/react";
import "fake-indexeddb/auto";
import { useSettings } from "../src/useSettings";
import { DemoAPI } from "../src/mock";
import { BrowserStore } from "../src/storage";
import { defaults } from "../src/fixtures";
afterEach(cleanup);
function api(latency = 0) {
  return new DemoAPI(
    new BrowserStore("synthetic-hook-" + crypto.randomUUID()),
    latency,
  );
}
it("cancel and undo edit only draft, never persisted settings", async () => {
  const a = api(),
    { result } = renderHook(() => useSettings(a));
  await waitFor(() => expect(result.current.saved).not.toBeNull());
  act(() => result.current.edit({ ...defaults, day: 22 }));
  act(() => result.current.cancel());
  expect(result.current.draft.day).toBe(21.5);
  act(() => result.current.undo());
  expect(result.current.draft.day).toBe(22);
  expect((await a.settings()).values.day).toBe(21.5);
});
it("explicit conflict rebase preserves draft then saves new revision", async () => {
  const a = api(),
    { result } = renderHook(() => useSettings(a));
  await waitFor(() => expect(result.current.saved).not.toBeNull());
  await a.save("synthetic.other", 1, { ...defaults, day: 23 }, a.session);
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await act(() => result.current.save());
  expect(result.current.conflict?.revision).toBe(2);
  act(() => result.current.rebase());
  expect(result.current.draft.day).toBe(22);
  // Same-field edits require a choice, even after adopting the remote revision.
  await act(() => result.current.save());
  expect(result.current.saved?.revision).toBe(2);
  act(() => result.current.resolve(["day"], "local"));
  await act(() => result.current.save());
  expect(result.current.saved?.revision).toBe(3);
  expect(result.current.message).toContain("Збережено");
});
it("initial read failure is explicit and retry does not invent persisted state", async () => {
  let ready = false;
  const a = new DemoAPI(
    {
      read: async () => {
        if (!ready) throw Error("synthetic");
        return { revision: 1, values: defaults, lastRequest: null };
      },
      commit: async () => {
        throw Error("not used");
      },
    },
    0,
  );
  const { result } = renderHook(() => useSettings(a));
  await waitFor(() => expect(result.current.error).toBe(true));
  await act(() => result.current.save());
  expect(result.current.saved).toBeNull();
  ready = true;
  await act(() => result.current.load());
  expect(result.current.error).toBe(false);
  expect(result.current.saved?.revision).toBe(1);
});
it("old connection acknowledgement cannot clear or overwrite current draft", async () => {
  const a = api(20),
    { result } = renderHook(() => useSettings(a));
  await waitFor(() => expect(result.current.saved).not.toBeNull());
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await act(async () => {
    const work = result.current.save();
    a.reconnect();
    await work;
  });
  expect(result.current.pending).toBe(false);
  expect(result.current.message).toContain("Старе підтвердження відкинуто");
  expect(result.current.draft.day).toBe(22);
  expect(result.current.saved?.revision).toBe(1);
});
