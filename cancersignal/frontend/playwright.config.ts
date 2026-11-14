import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", timeout: 45_000, workers: 1,
  use: { baseURL: "http://127.0.0.1:3107", trace: "retain-on-failure", launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3107",
    url: "http://127.0.0.1:3107", reuseExistingServer: false,
    env: { NEXT_PUBLIC_API_URL: process.env.E2E_API_URL ?? "http://127.0.0.1:8017" },
  },
});
