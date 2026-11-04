import { defineConfig } from "vitest/config";
export default defineConfig({
  base: "./",
  server: { host: "127.0.0.1", strictPort: true, hmr: false },
  preview: { host: "127.0.0.1", strictPort: true },
  build: {
    rollupOptions: {
      input: { main: "index.html", panel: "src/panel.tsx" },
      output: { entryFileNames: "assets/[name].js" },
    },
  },
  test: {
    include: ["tests/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    coverage: {
      provider: "v8",
      include: [
        "src/domain.ts",
        "src/mock.ts",
        "src/storage.ts",
        "src/contracts.ts",
        "src/useSettings.ts",
        "src/settingsMerge.ts",
        "src/history.ts",
        "src/historyEnergy.ts",
        "src/nativeAdapter.ts",
        "src/nativeContracts.ts",
      ],
      thresholds: { lines: 90, branches: 85, functions: 90, statements: 90 },
    },
  },
});
