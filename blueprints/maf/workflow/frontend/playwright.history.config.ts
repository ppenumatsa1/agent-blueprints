import { defineConfig, devices } from "@playwright/test";

const baseURL = "http://127.0.0.1:4175";

export default defineConfig({
  testDir: "./e2e",
  testMatch: ["history.spec.ts", "activity-live.spec.ts", "optional-adapters.spec.ts"],
  outputDir: "test-results-history",
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4175",
    url: baseURL,
    reuseExistingServer: false,
  },
});
