import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/measurements', () => {
    throw new Error('Simulation requested a public measurement');
  });
});
const delayPresets = [
  ['symmetric-low', '+100', '0', '40'],
  ['symmetric-high', '+100', '0', '160'],
  ['asymmetric-forward', '+120', '+20', '80'],
  ['asymmetric-reverse', '+80', '−20', '80'],
];
for (const [preset, estimate, error, rtt] of delayPresets)
  test(`delay ${preset} uses Python results`, async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: /Network Delay/ }).click();
    const panel = page.getByRole('tabpanel');
    await panel.getByLabel('Delay preset').selectOption(preset);
    await panel.getByRole('button', { name: 'Run delay simulation' }).click();
    await expect(panel.getByRole('img')).toHaveAccessibleName(
      `True offset: +100 milliseconds; NTP estimate: ${estimate} milliseconds; Estimation error: ${error} milliseconds`,
    );
    await expect(panel.locator('.small-tag')).toContainText(`Network RTT ${rtt} ms`);
    await expect(panel.getByText('SIMULATION', { exact: true })).toBeVisible();
    await panel.getByText('Modeled timestamps & calculations', { exact: true }).click();
    await expect(panel.getByRole('table', { name: 'Modeled four timestamps' })).toBeVisible();
  });
test('equal-delay increase raises RTT without bias', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: /Network Delay/ }).click();
  await page
    .getByRole('tabpanel')
    .getByRole('combobox', { name: 'Comparison', exact: true })
    .selectOption('equal');
  await page.getByRole('button', { name: 'Run delay simulation' }).click();
  const table = page.getByRole('table', { name: /Comparison/ });
  await expect(table.getByRole('row').nth(1)).toContainText('40 ms');
  await expect(table.getByRole('row').nth(2)).toContainText('160 ms');
  await page.getByRole('tabpanel').getByLabel('Point 2').check();
  await expect(page.getByRole('img')).toHaveAccessibleName(/Estimation error: 0 milliseconds/);
  await expect(page.getByRole('tabpanel').locator('.small-tag')).toContainText('160 ms');
});
test('fixed RTT holds total delay and exposes opposite errors', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: /Network Delay/ }).click();
  await page
    .getByRole('tabpanel')
    .getByRole('combobox', { name: 'Comparison', exact: true })
    .selectOption('fixed');
  await page.getByRole('button', { name: 'Run delay simulation' }).click();
  const table = page.getByRole('table', { name: /Comparison/ });
  await expect(table.getByRole('row').nth(1)).toContainText('−40 ms');
  await expect(table.getByRole('row').nth(3)).toContainText('+40 ms');
  for (const label of ['Point 1', 'Point 2', 'Point 3']) {
    await page.getByRole('tabpanel').getByLabel(label).check();
    await expect(page.getByRole('tabpanel').locator('.small-tag')).toContainText('80 ms');
  }
  await expect(page.getByRole('img')).toHaveAccessibleName(/NTP estimate: \+140 milliseconds/);
});
for (const [scenario, correction, residual] of [
  ['symmetric', '−120', '0'],
  ['forward', '−100', '+20'],
  ['reverse', '−140', '−20'],
  ['behind', '+120', '0'],
  ['aligned', '+20', '+20'],
]) {
  test(`virtual ${scenario}: correction ${correction}, residual ${residual}`, async ({ page }) => {
    let posts = 0;
    page.on('request', (r) => {
      if (r.url().endsWith('/experiments/sync') && r.method() === 'POST') posts++;
    });
    await page.goto('/');
    await page.getByRole('tab', { name: /Clock Synchronization/ }).click();
    await page.getByRole('tabpanel').getByLabel('Clock scenario').selectOption(scenario);
    await page.getByRole('button', { name: 'Measure virtual clock' }).click();
    await expect(page.getByText('Not applied', { exact: true })).toBeVisible();
    const panel = page.getByRole('tabpanel');
    await expect(panel.locator('.metric').nth(1)).toContainText(`${correction}ms`);
    await page.getByRole('button', { name: 'Apply correction' }).click();
    await expect(page.getByRole('img')).toHaveAccessibleName(
      new RegExp(`Residual error: ${residual.replace('+', '\\+')} milliseconds`),
    );
    expect(posts).toBe(1);
    await expect(page.getByRole('button', { name: 'Correction applied' })).toBeDisabled();
    await panel.getByText('Virtual clock snapshots & timeline', { exact: true }).click();
    await expect(
      panel.getByRole('table', { name: 'Backend virtual clock timeline' }).getByRole('row'),
    ).toHaveCount(4);
    await page.getByRole('button', { name: 'Reset experiment' }).click();
    await expect(page.getByRole('tabpanel').getByText('Ready when you are.')).toBeVisible();
    expect(posts).toBe(1);
  });
}
test('edited inputs need a new measurement and errors preserve old results', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: /Clock Synchronization/ }).click();
  await page.getByRole('button', { name: 'Measure virtual clock' }).click();
  await expect(page.getByText('Not applied', { exact: true })).toBeVisible();
  await page
    .getByRole('tabpanel')
    .getByLabel(/Forward delay/)
    .fill('2001');
  await expect(page.getByRole('button', { name: 'Apply correction' })).toBeDisabled();
  await page.getByRole('button', { name: 'Measure virtual clock' }).click();
  await expect(page.getByRole('alert')).toContainText('INVALID_INPUT');
  await expect(page.getByRole('alert')).toContainText('previous successful run');
  await expect(page.getByRole('button', { name: 'Apply correction' })).toBeDisabled();
});
test('half-nanosecond snapshot survives display and API export', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('tab', { name: /Clock Synchronization/ }).click();
  await page
    .getByRole('tabpanel')
    .getByLabel(/Initial error/)
    .fill('0.000001');
  await page
    .getByRole('tabpanel')
    .getByLabel(/Forward delay/)
    .fill('0.000001');
  await page
    .getByRole('tabpanel')
    .getByLabel(/Reverse delay/)
    .fill('0');
  await page.getByRole('button', { name: 'Measure virtual clock' }).click();
  await page.getByRole('button', { name: 'Apply correction' }).click();
  await expect(page.getByRole('img')).toHaveAccessibleName(
    /Residual error: \+0.0000005 milliseconds/,
  );
  await page.getByText('Virtual clock snapshots & timeline', { exact: true }).click();
  await expect(page.getByRole('table', { name: 'Backend virtual clock timeline' })).toContainText(
    '.5',
  );
});
test('simulation screens keep presentation typography, responsive layout and accessibility', async ({
  page,
}, testInfo) => {
  await page.goto('/');
  for (const [name, button] of [
    [/Network Delay/, 'Run delay simulation'],
    [/Clock Synchronization/, 'Measure virtual clock'],
  ] as const) {
    await page.getByRole('tab', { name }).click();
    await page.getByRole('button', { name: button }).click();
    if (button === 'Measure virtual clock')
      await page.getByRole('button', { name: 'Apply correction' }).click();
    for (const width of [1280, 1024, 390]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      const panel = page.getByRole('tabpanel');
      for (const el of await panel.locator('.metric p>span:first-child').all()) {
        expect(await el.evaluate((e) => e.scrollWidth <= e.clientWidth + 1)).toBe(true);
        if (width >= 1024)
          expect(
            await el.evaluate((e) => parseFloat(getComputedStyle(e).fontSize)),
          ).toBeGreaterThanOrEqual(32);
      }
      const findings = await new AxeBuilder({ page }).analyze();
      expect(
        findings.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
      ).toEqual([]);
      const tag = button === 'Run delay simulation' ? 'delay' : 'sync';
      await page.screenshot({
        path: `test-results/${testInfo.project.name}-${tag}-${width}.png`,
        fullPage: true,
      });
    }
    await page.setViewportSize({ width: 1440, height: 1050 });
  }
});

test('export retains the whole delay series as returned by Python', async ({ page }) => {
  const { readFileSync } = await import('node:fs');
  await page.goto('/');
  await page.getByRole('tab', { name: /Network Delay/ }).click();
  const panel = page.getByRole('tabpanel');
  await panel.getByRole('combobox', { name: 'Comparison', exact: true }).selectOption('fixed');
  const responsePromise = page.waitForResponse(
    (r) => r.url().endsWith('/experiments/delay') && r.request().method() === 'POST',
  );
  await panel.getByRole('button', { name: 'Run delay simulation' }).click();
  const original = await (await responsePromise).json();
  await panel.getByText('Model assumptions & original JSON', { exact: true }).click();
  const downloadPromise = page.waitForEvent('download');
  await panel.getByRole('button', { name: 'Export simulation JSON' }).click();
  const file = await (await downloadPromise).path();
  expect(JSON.parse(readFileSync(file!, 'utf8'))).toEqual(original);
  expect(original.data.points).toHaveLength(3);
});
