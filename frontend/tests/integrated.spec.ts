import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
const capture = JSON.parse(
  readFileSync(new URL('../../docs/evidence/p1.3-public-ntp.json', import.meta.url), 'utf8'),
);

test('three-tab walkthrough preserves each experiment and reset isolation', async ({ page }) => {
  const posts: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST') posts.push(r.url());
  });
  await page.route('**/api/v1/measurements', (route) => route.abort());
  await page.goto('/');
  await page.getByRole('button', { name: 'Load captured exchange' }).click();
  await expect(page.getByText('REPLAY · original LIVE')).toBeVisible();
  await page.getByRole('tab', { name: /Network Delay/ }).click();
  let panel = page.getByRole('tabpanel');
  await panel.getByRole('combobox', { name: 'Comparison', exact: true }).selectOption('fixed');
  await panel.getByRole('button', { name: 'Run delay simulation' }).click();
  await panel.getByLabel('Point 3').check();
  await expect(panel.getByRole('img')).toHaveAccessibleName(/Estimation error: \+40 milliseconds/);
  await page.getByRole('tab', { name: /Clock Synchronization/ }).click();
  panel = page.getByRole('tabpanel');
  await panel.getByLabel('Clock scenario').selectOption('forward');
  await panel.getByRole('button', { name: 'Measure virtual clock' }).click();
  await panel.getByRole('button', { name: 'Apply correction' }).click();
  await expect(panel.getByRole('img')).toHaveAccessibleName(/Residual error: \+20 milliseconds/);
  await panel.getByRole('button', { name: 'Reset experiment' }).click();
  await expect(panel.getByText('Ready when you are.')).toBeVisible();
  await page.getByRole('tab', { name: /Network Delay/ }).click();
  await expect(page.getByRole('tabpanel').getByLabel('Point 3')).toBeChecked();
  await page.getByRole('tab', { name: /Real NTP/ }).click();
  await expect(page.getByText('+81.0434325', { exact: true })).toBeVisible();
  expect(posts).toHaveLength(3);
});

test('in-flight live result and cooldown survive navigation and other-tab reset', async ({
  page,
}) => {
  let sends = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/measurements', async (route) => {
    sends++;
    await gate;
    await route.fulfill({ json: capture.attempts[0].result });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Measure once' }).click();
  await page.getByRole('tab', { name: /Network Delay/ }).click();
  await page.getByRole('tabpanel').getByRole('button', { name: 'Reset experiment' }).click();
  await page.getByRole('tab', { name: /Real NTP/ }).click();
  await expect(page.getByRole('button', { name: 'Measuring…' })).toBeDisabled();
  release();
  await expect(page.getByText('LIVE MEASUREMENT')).toBeVisible();
  await expect(page.getByRole('button', { name: /Available in/ })).toBeDisabled();
  await page.getByRole('tab', { name: /Clock Synchronization/ }).click();
  await page.getByRole('tabpanel').getByRole('button', { name: 'Reset experiment' }).click();
  await page.getByRole('tab', { name: /Real NTP/ }).click();
  await expect(page.getByRole('button', { name: /Available in/ })).toBeDisabled();
  expect(sends).toBe(1);
});

test('429 wait expires without an automatic retry and keeps failure visible', async ({ page }) => {
  await page.clock.install();
  let sends = 0;
  await page.route('**/api/v1/measurements', (route) => {
    sends++;
    return route.fulfill({
      status: 429,
      headers: { 'Retry-After': '2' },
      json: {
        schema_version: '1',
        error: {
          code: 'RATE_LIMITED',
          message: 'Fixture cooldown',
          details: { retry_after_ns: 2000000000 },
        },
      },
    });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Measure once' }).click();
  await expect(page.getByRole('alert')).toContainText('RATE_LIMITED');
  await expect(page.getByRole('button', { name: /Available in/ })).toBeDisabled();
  await page.clock.fastForward(3500);
  await expect(page.getByRole('button', { name: 'Measure once' })).toBeEnabled();
  await expect(page.getByRole('alert')).toBeVisible();
  expect(sends).toBe(1);
});

test('local replay and simulations work with all external browser requests prohibited', async ({
  page,
}) => {
  let external = 0;
  await page.route('**/*', (route) => {
    const host = new URL(route.request().url()).hostname;
    if (!['127.0.0.1', 'localhost'].includes(host)) {
      external++;
      return route.abort();
    }
    if (route.request().url().endsWith('/measurements'))
      throw new Error('Unexpected public measurement');
    return route.continue();
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Load captured exchange' }).click();
  await expect(page.getByText('REPLAY · original LIVE')).toBeVisible();
  await page.getByRole('tab', { name: /Network Delay/ }).click();
  await page.getByRole('button', { name: 'Run delay simulation' }).click();
  await expect(page.getByRole('img')).toHaveAccessibleName(/Estimation error: 0 milliseconds/);
  await page.getByRole('tab', { name: /Clock Synchronization/ }).click();
  await page.getByRole('button', { name: 'Measure virtual clock' }).click();
  await page.getByRole('button', { name: 'Apply correction' }).click();
  await expect(page.getByRole('img')).toHaveAccessibleName(/Residual error: 0 milliseconds/);
  expect(external).toBe(0);
});

test('connection failure after startup updates status without discarding the last replay', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Load captured exchange' }).click();
  await page.route('**/api/v1/measurements', (route) => route.abort('connectionfailed'));
  await page.getByRole('button', { name: 'Measure once' }).click();
  await expect(page.getByText('API unavailable', { exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('API_UNAVAILABLE');
  await expect(page.getByText('REPLAY · original LIVE')).toBeVisible();
});
