import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e-native",
  outputDir: "./test-results/native-artifacts",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results/native-results.json" }],
    [
      "html",
      { outputFolder: "playwright-report-native/report", open: "never" },
    ],
  ],
  use: {
    baseURL: process.env.TEST_HA_BASE_URL ?? "http://127.0.0.1:8123",
    trace: "off",
    screenshot: "only-on-failure",
    reducedMotion: "reduce",
    locale: "uk-UA",
    timezoneId: "Europe/Kyiv",
  },
  projects: [
    {
      name: "native-chromium-mobile",
      use: {
        browserName: "chromium",
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: "native-chromium-desktop",
      use: { browserName: "chromium", viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "native-webkit-mobile",
      use: {
        browserName: "webkit",
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
    {
      name: "native-webkit-desktop",
      use: { browserName: "webkit", viewport: { width: 1440, height: 1000 } },
    },
  ],
});
