import { defineConfig } from '@playwright/test'

// Browser tests. The API is mocked inside the browser (see e2e/fixtures.ts), so these need no backend,
// no database and no internet, and they cannot touch real data or the kill switch.
const PORT = 5180

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts', // keeps these out of Vitest, which runs src/**/*.test.ts
  fullyParallel: false,
  workers: 1, // one browser at a time: this PC is short of memory
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    // Locally use the Microsoft Edge already installed on Windows (no download). On CI the bundled Chromium is installed instead.
    channel: process.env.CI ? undefined : 'msedge',
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 900 },
    reducedMotion: 'reduce',
  },
  webServer: {
    command: `npm run dev -- --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})
