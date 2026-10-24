import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3062",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
  webServer: [
    {
      command: `${process.env.E2E_PYTHON || (process.platform === "win32" ? "..\\backend\\.venv\\Scripts\\python.exe" : "../backend/.venv/bin/python")} e2e/backend.py`,
      url: "http://127.0.0.1:8062/api/health",
      reuseExistingServer: process.env.E2E_REUSE_SERVERS === "1",
      timeout: 60000,
      env: { ACP_FAKE_SCENARIO: "bugfix_happy_path" },
    },
    {
      command:
        "node node_modules/next/dist/bin/next dev --turbopack --hostname 127.0.0.1 --port 3062",
      url: "http://127.0.0.1:3062/login",
      reuseExistingServer: process.env.E2E_REUSE_SERVERS === "1",
      timeout: 120000,
      env: { BACKEND_URL: "http://127.0.0.1:8062", NEXT_DIST_DIR: ".next-e2e" },
    },
  ],
});
