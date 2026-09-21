import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.CONSOLE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
  },
  reporter: process.env.CI ? "github" : "list",
});
