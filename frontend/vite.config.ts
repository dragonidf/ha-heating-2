import { defineConfig } from "vitest/config";
export default defineConfig({
  base: "./",
  server: { host: "127.0.0.1", strictPort: true, hmr: false },
  preview: { host: "127.0.0.1", strictPort: true },
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
      ],
      thresholds: { lines: 90, branches: 85, functions: 90, statements: 90 },
    },
  },
});
