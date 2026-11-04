import { afterEach, expect, it } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import "fake-indexeddb/auto";
import { equal, merge, replaceField } from "../src/settingsMerge";
import { defaults } from "../src/fixtures";
import { useSettings } from "../src/useSettings";
import { DemoAPI } from "../src/mock";
import { BrowserStore } from "../src/storage";
import type { Settings } from "../src/types";
afterEach(cleanup);
const edits: Settings = {
  day: 22,
  night: 20,
  budget: 700,
  windowStart: "22:00",
  windowEnd: "08:00",
  strategy: "comfort",
  mode: "observation",
  circulation: "manual",
  fan: 70,
  scenario: 9,
  freshness: 45,
  aiAdvice: true,
};
it.each(Object.keys(defaults) as (keyof Settings)[])(
  "three-way merge keeps remote-only %s and detects local-only dirty leaves",
  (key) => {
    const localKey = key === "day" ? "budget" : "day";
    const local = { ...defaults, [localKey]: edits[localKey] };
    const remote = { ...defaults, [key]: edits[key] };
    const result = merge(defaults, local, remote);
    expect(result.value).toEqual({ ...remote, [localKey]: edits[localKey] });
    expect(result.collisions).toEqual([]);
    expect(result.fields).toHaveLength(12);
    expect(merge(remote, result.value, remote).value).toEqual(result.value);
  },
);
it("recursive merge handles future nested leaves, additions, removals, arrays and null", () => {
  const base = {
    nested: { a: 1, b: 2, removed: true },
    array: [1],
    nullable: null,
  };
  const local = { nested: { a: 3, b: 2 }, array: [2], nullable: null };
  const remote = {
    nested: { a: 1, b: 4, removed: true },
    array: [3],
    nullable: null,
  };
  const result = merge<unknown>(base, local, remote);
  expect(result.value).toEqual({
    nested: { a: 3, b: 4 },
    array: [2],
    nullable: null,
  });
  expect(result.collisions.map((f) => f.path)).toEqual([["array"]]);
  expect(replaceField(result.value, ["array"], [3])).toEqual({
    nested: { a: 3, b: 4 },
    array: [3],
    nullable: null,
  });
  expect(
    merge<unknown>({}, { new: { a: 1 } }, { new: { b: 2 } }).value,
  ).toEqual({ new: { a: 1, b: 2 } });
  expect(equal({ b: [1, null], a: 0 }, { a: 0, b: [1, null] })).toBe(true);
  expect(equal([1], [1, 2])).toBe(false);
  expect(equal({ a: undefined }, {})).toBe(false);
  expect(replaceField({ a: 1 }, ["a"], undefined)).toEqual({});
});
async function clients() {
  const name = "synthetic-merge-" + crypto.randomUUID();
  const a = new DemoAPI(new BrowserStore(name), 0),
    b = new DemoAPI(new BrowserStore(name), 0);
  const hook = renderHook(() => useSettings(a));
  await waitFor(() => expect(hook.result.current.saved?.revision).toBe(1));
  return { a, b, ...hook };
}
it("same-field collision cannot save until explicitly resolved in favor of remote", async () => {
  const { result, b } = await clients();
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await b.save(
    "synthetic.remote",
    1,
    { ...defaults, day: 23, fan: 70 },
    b.session,
  );
  await act(() => result.current.save());
  expect(result.current.differences).toHaveLength(12);
  act(() => result.current.rebase());
  expect(result.current.collisions.map((f) => f.path)).toEqual([["day"]]);
  expect(result.current.draft.fan).toBe(70);
  await act(() => result.current.save());
  expect((await b.settings()).revision).toBe(2);
  act(() => result.current.resolve(["not-a-field"], "local"));
  expect(result.current.collisions).toHaveLength(1);
  act(() => result.current.resolve(["day"], "remote"));
  expect(result.current.draft.day).toBe(23);
  await act(() => result.current.save());
  expect((await b.settings()).values).toMatchObject({ day: 23, fan: 70 });
});
it("a remote save after rebase conflicts again and cannot lose either writer's edits", async () => {
  const { result, b } = await clients();
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await b.save("synthetic.remote1", 1, { ...defaults, fan: 70 }, b.session);
  await act(() => result.current.save());
  act(() => result.current.rebase());
  await b.save(
    "synthetic.remote2",
    2,
    { ...defaults, fan: 70, budget: 800 },
    b.session,
  );
  await act(() => result.current.save());
  expect(result.current.conflict?.revision).toBe(3);
  act(() => result.current.rebase());
  expect(result.current.draft).toMatchObject({ day: 22, fan: 70, budget: 800 });
  await act(() => result.current.save());
  expect((await b.settings()).revision).toBe(4);
  expect((await b.settings()).values).toMatchObject({
    day: 22,
    fan: 70,
    budget: 800,
  });
});
it("retry reread, cancel and undo preserve local intent without undoing unrelated remote edits", async () => {
  const { result, b } = await clients();
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await act(() => result.current.load());
  expect(result.current.draft.day).toBe(22);
  await b.save("synthetic.remote", 1, { ...defaults, fan: 70 }, b.session);
  await act(() => result.current.load());
  expect(result.current.conflict?.revision).toBe(2);
  act(() => result.current.cancel());
  expect(result.current.draft).toMatchObject({ day: 21.5, fan: 70 });
  act(() => result.current.undo());
  expect(result.current.draft).toMatchObject({ day: 22, fan: 70 });
  await act(() => result.current.save());
  expect((await b.settings()).values).toMatchObject({ day: 22, fan: 70 });
});
it("same concurrent value is not a collision, and undo across rebase keeps remote values", async () => {
  const { result, b } = await clients();
  act(() => result.current.undo());
  act(() => result.current.rebase());
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await b.save(
    "synthetic.remote",
    1,
    { ...defaults, day: 22, fan: 70 },
    b.session,
  );
  await act(() => result.current.save());
  act(() => result.current.rebase());
  expect(result.current.collisions).toHaveLength(0);
  act(() => result.current.undo());
  expect(result.current.draft.fan).toBe(70);
  expect(result.current.draft.day).toBe(22);
});
it("a quick-save cannot discard an existing unsaved settings draft", async () => {
  const { result, b } = await clients();
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await act(() => result.current.save({ ...defaults, night: 21 }));
  expect(result.current.draft.day).toBe(22);
  expect((await b.settings()).revision).toBe(1);
});
it("a quick-save conflict retains the intended quick change for explicit merge", async () => {
  const { result, b } = await clients();
  await b.save("synthetic.remote", 1, { ...defaults, fan: 70 }, b.session);
  await act(() => result.current.save({ ...defaults, night: 21 }));
  expect(result.current.conflict?.revision).toBe(2);
  expect(result.current.draft.night).toBe(21);
  act(() => result.current.rebase());
  await act(() => result.current.save());
  expect((await b.settings()).values).toMatchObject({ night: 21, fan: 70 });
});
it("editing an unresolved local field updates the explicit choice without changing remote-only fields", async () => {
  const { result, b } = await clients();
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await b.save(
    "synthetic.remote",
    1,
    { ...defaults, day: 23, fan: 70 },
    b.session,
  );
  await act(() => result.current.save());
  act(() => result.current.rebase());
  act(() => result.current.edit({ ...result.current.draft, day: 22.5 }));
  expect(result.current.collisions[0]?.local).toBe(22.5);
  act(() => result.current.resolve(["day"], "local"));
  await act(() => result.current.save());
  expect((await b.settings()).values).toMatchObject({ day: 22.5, fan: 70 });
});
it("a late reread cannot roll back a newer persisted save and clear its values", async () => {
  let blockNext = false;
  let release = () => {};
  let began = () => {};
  const started = new Promise<void>((resolve) => {
    began = resolve;
  });
  class DelayedReadAPI extends DemoAPI {
    override async settings() {
      const state = await super.settings();
      if (blockNext) {
        blockNext = false;
        began();
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      }
      return state;
    }
  }
  const api = new DelayedReadAPI(
    new BrowserStore("synthetic-late-read-" + crypto.randomUUID()),
    0,
  );
  const { result } = renderHook(() => useSettings(api));
  await waitFor(() => expect(result.current.saved?.revision).toBe(1));
  blockNext = true;
  let pending: ReturnType<typeof result.current.load>;
  await act(async () => {
    pending = result.current.load();
    await started;
  });
  act(() => result.current.edit({ ...defaults, day: 22 }));
  await act(() => result.current.save());
  expect(result.current.saved?.revision).toBe(2);
  await act(async () => {
    release();
    await pending!;
  });
  expect(result.current.saved?.revision).toBe(2);
  expect(result.current.draft.day).toBe(22);
});
