import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./demo-tests",
  timeout: 90_000,
  workers: 1,
  use: {
    baseURL: process.env.DEMO_BASE_URL ?? "http://127.0.0.1:3000",
    httpCredentials: process.env.DEMO_SITE_PASSWORD
      ? { username: process.env.DEMO_SITE_USER ?? "presenter", password: process.env.DEMO_SITE_PASSWORD }
      : undefined,
    // Hosted traces can contain site credentials; keep traces only for local CI.
    screenshot: "only-on-failure",
    trace: process.env.DEMO_SITE_PASSWORD ? "off" : "retain-on-failure",
  },
});
