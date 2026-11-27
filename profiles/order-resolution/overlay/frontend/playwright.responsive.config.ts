import { defineConfig, devices } from "@playwright/test";

const baseURL = "http://127.0.0.1:4175";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "studio-responsive.spec.ts",
  workers: 1,
  use: { ...devices["Desktop Chrome"], baseURL },
  webServer: {
    command: "npm run dev -- --port 4175",
    url: baseURL,
    reuseExistingServer: false,
  },
});
