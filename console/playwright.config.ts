import { defineConfig } from "@playwright/test";

// Two servers: the in-process stack on a real port (one golden waiting at the gate) and the
// built console. No compose, no images — CI runs exactly this.
const API = "http://localhost:8010";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // the two specs share one seeded proposal, in order
  use: {
    baseURL: process.env.CONSOLE_URL ?? "http://localhost:4173",
    trace: "retain-on-failure",
  },
  reporter: process.env.CI ? "github" : "list",
  webServer: [
    {
      command: "uv run qgate-eval serve --port 8010",
      cwd: "..",
      url: `${API}/health`,
      timeout: 180_000,
      reuseExistingServer: false, // every run seeds its own proposal
    },
    {
      command: "npm run build && npm run preview -- --port 4173 --strictPort",
      url: "http://localhost:4173",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: { VITE_API_BASE_URL: API },
    },
  ],
});
