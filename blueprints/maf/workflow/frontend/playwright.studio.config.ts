import { defineConfig, devices } from "@playwright/test";

const baseURL = "http://127.0.0.1:4174";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "studio-shell.spec.ts",
  outputDir: "test-results-studio",
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
    command: "npm run build && npm run preview -- --host 127.0.0.1 --port 4174",
    url: baseURL,
    reuseExistingServer: false,
    env: {
      ...process.env,
      VITE_ENTRA_TENANT_ID: "10000000-0000-4000-8000-000000000001",
      VITE_ENTRA_SPA_CLIENT_ID: "30000000-0000-4000-8000-000000000003",
      VITE_ENTRA_API_APP_ID_URI: "api://20000000-0000-4000-8000-000000000002",
    },
  },
});

