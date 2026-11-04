// @vitest-environment node
import { it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { original } from "../src/fixtures";
import { DemoAPI } from "../src/mock";
import { defaults, NOW } from "../src/fixtures";
it("runtime has no transport, service writer or external endpoint", () => {
  const sources = readdirSync("src")
    .filter((n) => /\.(ts|tsx)$/.test(n))
    .map((n) => readFileSync("src/" + n, "utf8"))
    .join("\n");
  for (const forbidden of [
    /\bfetch\s*\(/,
    /\bWebSocket\s*\(/,
    /\bEventSource\s*\(/,
    /XMLHttpRequest/,
    /sendBeacon/,
    /call_service/,
    /dangerouslySetInnerHTML/,
    /https?:\/\//,
  ])
    expect(sources).not.toMatch(forbidden);
  expect(readFileSync("index.html", "utf8")).toContain("connect-src 'none'");
});
it("history and dependencies are bounded, local and reproducible", () => {
  const api = new DemoAPI({
    read: async () => ({ revision: 1, values: defaults, lastRequest: null }),
    commit: async () => {
      throw Error("not used");
    },
  });
  const page = api.history({ start: NOW - 31 * 86400, end: NOW }, null, 256);
  expect(Buffer.byteLength(JSON.stringify(page))).toBeLessThan(65536);
  const pkg = JSON.parse(readFileSync("package.json", "utf8"));
  expect(Object.keys(pkg.dependencies).sort()).toEqual(["react", "react-dom"]);
  expect(
    Object.values({ ...pkg.dependencies, ...pkg.devDependencies }).some(
      (v) => String(v).includes("latest") || String(v).startsWith("^"),
    ),
  ).toBe(false);
});
it("original fixture is deeply immutable and never recomputed by the model", () => {
  const before = JSON.stringify(original);
  expect(Object.isFrozen(original)).toBe(true);
  expect(Object.isFrozen(original.points)).toBe(true);
  expect(Object.isFrozen(original.points[0])).toBe(true);
  expect(() => Object.assign(original, { received: NOW })).toThrow();
  expect(JSON.stringify(original)).toBe(before);
});
