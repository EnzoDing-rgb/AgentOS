import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:8766",
    trace: "on-first-retry",
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 720 },
  },
  /**
   * 在 macOS 上想贴近 Safari 时，先 `npx playwright install webkit`，再：
   * `npx playwright test --project=webkit`
   * （Linux 无图形依赖时 WebKit 常会启动失败，故默认不启用。）
   */
  projects: process.env.PLAYWRIGHT_WEBKIT
    ? [
        { name: "chromium", use: { ...devices["Desktop Chrome"] } },
        { name: "webkit", use: { ...devices["Desktop Safari"] } },
      ]
    : [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "python3 -m http.server 8766 --bind 127.0.0.1",
    url: "http://127.0.0.1:8766",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
