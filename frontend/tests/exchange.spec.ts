import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'node:fs';
const capture = JSON.parse(
  readFileSync(new URL('../../docs/evidence/p1.3-public-ntp.json', import.meta.url), 'utf8'),
);

// All live measurement requests below are intercepted fixtures, never public probes.
test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/measurements', (route) =>
    route.fulfill({
      status: 504,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: '1',
        error: {
          code: 'NTP_TIMEOUT',
          message: 'Isolated browser test timeout; no NTP request sent',
          details: {},
        },
      }),
    }),
  );
});
test('real API replay, exact data, playback and keyboard tabs', async ({ page }, testInfo) => {
  const mutations: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST') mutations.push(r.url());
  });
  await page.goto('/');
  await expect(page.getByText('API connected')).toBeVisible();
  expect(mutations).toHaveLength(0);
  await expect(page.getByText('Awaiting an exchange')).toBeVisible();
  await page.getByRole('button', { name: 'Load captured exchange' }).click();
  await expect(page.getByText('REPLAY · original LIVE')).toBeVisible();
  await expect(page.getByText('+81.0434325', { exact: true })).toBeVisible();
  await expect(page.getByText('78.664213', { exact: true })).toBeVisible();
  await expect(page.getByText('Unknown', { exact: true })).toBeVisible();
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-desktop.png`,
    fullPage: true,
  });
  await page.getByText('Four timestamps', { exact: true }).click();
  await expect(page.getByText('1794735025245506539 ns', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Play exchange illustration' }).click();
  await expect(page.getByRole('button', { name: 'Pause illustration' })).toBeVisible();
  await page.getByRole('button', { name: 'Pause illustration' }).click();
  await page.getByRole('tab', { name: /Real NTP Exchange/ }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tabpanel')).toContainText('Delay setup');
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: /Clock Synchronization/ })).toBeFocused();
  await page.keyboard.press('Home');
  await expect(page.getByText('+81.0434325', { exact: true })).toBeVisible();
  expect(mutations).toHaveLength(1);
});
test('failure stays visible until explicit replay and no silent fallback', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Measure once' }).click();
  await expect(page.getByRole('alert')).toContainText('NTP_TIMEOUT');
  await expect(page.getByText('Awaiting an exchange')).toBeVisible();
  await page.getByRole('button', { name: 'Load captured exchange' }).click();
  await expect(page.getByText('+81.0434325', { exact: true })).toBeVisible();
});
test('one explicit request, configured ID and cooldown under double click', async ({ page }) => {
  let count = 0;
  await page.route('**/api/v1/measurements', async (route) => {
    count++;
    expect(route.request().postDataJSON()).toEqual({
      server_id: 'pool',
      timeout_seconds: 3,
    });
    await new Promise((resolve) => setTimeout(resolve, 150));
    await route.fulfill({ json: capture.attempts[0].result });
  });
  await page.goto('/');
  const button = page.getByRole('button', { name: 'Measure once' });
  await button.click({ clickCount: 2 });
  await expect(page.getByText('LIVE MEASUREMENT')).toBeVisible();
  await expect(page.getByRole('button', { name: /Available in/ })).toBeDisabled();
  expect(count).toBe(1);
});
test('reduced motion, narrow viewport and accessible replay', async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Load captured exchange' }).click();
  await expect(page.getByText('+81.0434325', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Next event' })).toBeEnabled();
  await page.getByRole('button', { name: 'Next event' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'T1' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: `test-results/${testInfo.project.name}-mobile.png`,
    fullPage: true,
  });
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
test('cross-origin mutations are rejected, including through development proxy', async ({
  request,
}) => {
  const response = await request.post('/api/v1/replays', {
    headers: { origin: 'https://unrelated.example' },
    data: { recording_id: 'captured-public-ntp' },
  });
  expect(response.status()).toBe(403);
});
test('empty experiment screens are accessible without experiment requests', async ({ page }) => {
  const posts: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST') posts.push(r.url());
  });
  await page.goto('/');
  await expect(page.getByText('API connected')).toBeVisible();
  for (const name of [/Real NTP Exchange/, /Network Delay/, /Clock Synchronization/]) {
    await page.getByRole('tab', { name }).click();
    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    ).toEqual([]);
  }
  expect(posts).toHaveLength(0);
});
test('exports the unchanged replay and preserves historical capture metadata', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Load captured exchange' }).click();
  await page.getByText('Provenance & limitations', { exact: true }).click();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export original JSON' }).click();
  const download = await downloadPromise;
  const path = await download.path();
  const exported = JSON.parse(readFileSync(path!, 'utf8'));
  expect(exported.source).toBe('replay');
  expect(exported.recording).toEqual(capture);
});

test('presentation typography and wrapping at projector sizes', async ({ page }, testInfo) => {
  for (const size of [
    { width: 1280, height: 720 },
    { width: 1024, height: 768 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(size);
    await page.goto('/');
    await page.getByRole('button', { name: 'Load captured exchange' }).click();
    const offset = page.getByText('+81.0434325', { exact: true });
    await expect(offset).toBeVisible();
    const box = await offset.boundingBox();
    expect(box!.y + box!.height).toBeLessThan(size.height);
    expect(
      await offset.evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
    ).toBeGreaterThanOrEqual(32);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    expect(
      await page
        .getByRole('tabpanel')
        .locator('.primary-button')
        .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
    ).toBeGreaterThanOrEqual(14);
    for (const selector of [
      '.metric p>span:first-child',
      '.primary-button',
      '.intro',
      '.tabs button',
    ]) {
      const elements = page.getByRole('tabpanel').locator(selector);
      for (let i = 0; i < (await elements.count()); i++)
        expect(await elements.nth(i).evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(
          true,
        );
    }
    await page.screenshot({
      path: `test-results/${testInfo.project.name}-projector-${size.width}.png`,
      fullPage: true,
    });
  }
});
