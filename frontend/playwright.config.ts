import { defineConfig, devices } from '@playwright/test';
const python =
  process.env.NTP_LAB_PYTHON || new URL('../.venv/bin/python', import.meta.url).pathname;
const root = new URL('..', import.meta.url).pathname;
const audited = `import tests.conftest; import uvicorn; uvicorn.run`;
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  use: {
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 1050 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'development', use: { baseURL: 'http://127.0.0.1:5173' } },
    { name: 'release', use: { baseURL: 'http://127.0.0.1:8001' } },
  ],
  webServer: [
    {
      command: `${python} -c '${audited}("ntp_sync_lab.api.app:app", host="127.0.0.1", port=8000, log_level="warning")'`,
      cwd: root,
      url: 'http://127.0.0.1:8000/api/v1/health',
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
    },
    {
      command: `${python} -c '${audited}("ntp_sync_lab.api.web:create_web_app", factory=True, host="127.0.0.1", port=8001, log_level="warning")'`,
      cwd: root,
      url: 'http://127.0.0.1:8001/api/v1/health',
      reuseExistingServer: false,
    },
  ],
});
