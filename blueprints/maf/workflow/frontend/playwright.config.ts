import { defineConfig, devices } from "@playwright/test";

const live = process.env.E2E_LIVE === "true";
const localUrl = "http://127.0.0.1:4173";
const baseURL = live ? process.env.E2E_BASE_URL : localUrl;

if (live && !baseURL) {
  throw new Error("E2E_BASE_URL is required when E2E_LIVE=true.");
}

export default defineConfig({
  testDir: "./e2e",
  outputDir: "test-results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    trace: live ? "off" : "retain-on-failure",
    screenshot: live ? "off" : "only-on-failure",
    video: live ? "off" : "retain-on-failure",
  },
  webServer: live
    ? undefined
    : {
        command: "npm run dev -- --port 4173",
        url: localUrl,
        reuseExistingServer: false,
        env: {
          ...process.env,
          VITE_ENTRA_TENANT_ID: "10000000-0000-4000-8000-000000000001",
          VITE_ENTRA_SPA_CLIENT_ID: "30000000-0000-4000-8000-000000000003",
          VITE_ENTRA_API_APP_ID_URI: "api://20000000-0000-4000-8000-000000000002",
        },
      },
});
