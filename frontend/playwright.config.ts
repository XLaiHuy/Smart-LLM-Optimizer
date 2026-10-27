import { defineConfig, devices } from "@playwright/test";

process.env.E2E_PASSWORD ||= "e2e-isolated-test-only";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 10000 },
  retries: 0,
  outputDir: "../output/playwright/results",
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "../output/playwright/report" }],
  ],
  use: {
    baseURL: "http://localhost:3001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "node ../scripts/e2e-server.mjs",
    url: "http://localhost:3001",
    timeout: 300000,
    reuseExistingServer: false,
  },
});
