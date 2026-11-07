import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./demo-tests",
  timeout: 90_000,
  workers: 1,
  use: { baseURL: process.env.DEMO_BASE_URL ?? "http://127.0.0.1:3000", screenshot: "only-on-failure", trace: "retain-on-failure" },
});
