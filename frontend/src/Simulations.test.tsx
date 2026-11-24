import { fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { expect, it, vi } from 'vitest';
import DelayLab from './DelayLab';
import SyncLab from './SyncLab';
import fixtures from './__fixtures__/simulations.json';
import { readDelayResponse, readSync } from './simulationApi';

function mockResult(value: unknown) {
  const fetch = vi.fn().mockResolvedValue(Response.json(value));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
const names = [
  'symmetric-low',
  'symmetric-high',
  'asymmetric-forward',
  'asymmetric-reverse',
] as const;
it.each(names)('displays API preset %s and sends only decimal strings', async (name) => {
  const fetch = mockResult(fixtures[name]);
  const user = userEvent.setup();
  render(<DelayLab />);
  await user.selectOptions(screen.getByLabelText('Delay preset'), name);
  await user.click(screen.getByRole('button', { name: 'Run delay simulation' }));
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(Object.values(body).every((v) => typeof v === 'string')).toBe(true);
  expect(body.forward_ms).toBe(
    name === 'symmetric-high' ? '80' : name === 'asymmetric-forward' ? '60' : '20',
  );
  expect(await screen.findByRole('img')).toHaveAccessibleName(
    name === 'asymmetric-forward'
      ? /NTP estimate: \+120 milliseconds/
      : name === 'asymmetric-reverse'
        ? /NTP estimate: \+80 milliseconds/
        : /NTP estimate: \+100 milliseconds/,
  );
  expect(fetch).toHaveBeenCalledTimes(1);
});
it.each(['fixed', 'equal'] as const)('shows every backend %s comparison point', async (mode) => {
  const fetch = mockResult(fixtures[mode]);
  const user = userEvent.setup();
  render(<DelayLab />);
  await user.selectOptions(screen.getByLabelText('Comparison'), mode);
  await user.click(screen.getByRole('button', { name: 'Run delay simulation' }));
  const rows = within(await screen.findByRole('table', { name: /Comparison/ })).getAllByRole('row');
  expect(rows).toHaveLength(mode === 'fixed' ? 4 : 3);
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  if (mode === 'fixed') {
    expect(body.round_trip_ms).toBe('80');
    expect(body.sweep_points).toBe(3);
    expect(rows[1]).toHaveTextContent('−40 ms');
    expect(rows[3]).toHaveTextContent('+40 ms');
  } else {
    expect(body.increments_ms).toEqual(['0', '60']);
    expect(rows[1]).toHaveTextContent('40 ms');
    expect(rows[2]).toHaveTextContent('160 ms');
  }
  await user.click(screen.getByLabelText('Point 2'));
  expect(screen.getByRole('img')).toHaveAccessibleName(/Estimation error: 0 milliseconds/);
});
it('makes no startup POSTs in StrictMode and guards duplicate submits', async () => {
  const fetch = mockResult(fixtures['symmetric-low']);
  render(
    <StrictMode>
      <DelayLab />
    </StrictMode>,
  );
  expect(fetch).not.toHaveBeenCalled();
  const button = screen.getByRole('button', { name: 'Run delay simulation' });
  fireEvent.click(button);
  fireEvent.click(button);
  await screen.findByRole('img');
  expect(fetch).toHaveBeenCalledTimes(1);
});
it.each([
  ['sync-symmetric', 'symmetric', '0'],
  ['sync-forward', 'forward', '+20'],
  ['sync-reverse', 'reverse', '−20'],
  ['sync-behind', 'behind', '0'],
  ['sync-aligned', 'aligned', '+20'],
] as const)('shows backend correction and residual for %s', async (key, preset, residual) => {
  const fetch = mockResult(fixtures[key]);
  const user = userEvent.setup();
  render(<SyncLab />);
  await user.selectOptions(screen.getByLabelText('Clock scenario'), preset);
  await user.click(screen.getByRole('button', { name: 'Measure virtual clock' }));
  expect(await screen.findByText('Not applied')).toBeVisible();
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Apply correction' }));
  expect(screen.getByRole('img')).toHaveAccessibleName(
    new RegExp(`Residual error: ${residual.replace('+', '\\+')} milliseconds`),
  );
  expect(fetch).toHaveBeenCalledTimes(1); // Apply reveals a backend snapshot, without recomputing or sending again.
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.mode).toBe('step');
  expect(body.client_offset_ms).toBe(
    preset === 'behind' ? '-120' : preset === 'aligned' ? '0' : '120',
  );
});
it('preserves half-ns readings and the common reference instant', async () => {
  mockResult(fixtures['sync-half']);
  const user = userEvent.setup();
  render(<SyncLab />);
  await user.click(screen.getByRole('button', { name: 'Measure virtual clock' }));
  await user.click(await screen.findByRole('button', { name: 'Apply correction' }));
  expect(screen.getByRole('img')).toHaveAccessibleName(/Residual error: \+0.0000005 milliseconds/);
  await user.click(screen.getByText('Virtual clock snapshots & timeline'));
  expect(screen.getByRole('table', { name: 'Backend virtual clock timeline' })).toHaveTextContent(
    '.5',
  );
});
it('disables correction for edited inputs and resets the whole experiment', async () => {
  mockResult(fixtures['sync-symmetric']);
  const user = userEvent.setup();
  render(<SyncLab />);
  await user.click(screen.getByRole('button', { name: 'Measure virtual clock' }));
  await screen.findByText('Not applied');
  await user.clear(screen.getByLabelText(/Initial error/));
  await user.type(screen.getByLabelText(/Initial error/), '0');
  expect(screen.getByRole('button', { name: 'Apply correction' })).toBeDisabled();
  expect(screen.getByText(/Inputs changed/).textContent).toMatch(/Inputs changed/);
  await user.click(screen.getByRole('button', { name: 'Reset experiment' }));
  expect(screen.getByLabelText(/Initial error/)).toHaveValue('120');
  expect(screen.queryByRole('button', { name: 'Apply correction' })).not.toBeInTheDocument();
});
it('keeps a failed simulation separate from the last successful result', async () => {
  const fetch = mockResult(fixtures['symmetric-low']);
  const user = userEvent.setup();
  render(<DelayLab />);
  await user.click(screen.getByRole('button', { name: 'Run delay simulation' }));
  await screen.findByRole('img');
  fetch.mockResolvedValueOnce(
    Response.json(
      { error: { code: 'INVALID_INPUT', message: 'forward_ms exceeds model bound', details: {} } },
      { status: 422 },
    ),
  );
  await user.clear(screen.getByLabelText(/Forward delay/));
  await user.type(screen.getByLabelText(/Forward delay/), '2001');
  await user.click(screen.getByRole('button', { name: 'Run delay simulation' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('previous successful run');
  expect(screen.getByRole('img')).toHaveAccessibleName(/NTP estimate: \+100 milliseconds/);
});
it('invalidates the previous correction on a new successful measurement', async () => {
  const fetch = mockResult(fixtures['sync-symmetric']);
  const user = userEvent.setup();
  render(<SyncLab />);
  await user.click(screen.getByRole('button', { name: 'Measure virtual clock' }));
  await user.click(await screen.findByRole('button', { name: 'Apply correction' }));
  fetch.mockResolvedValueOnce(Response.json(fixtures['sync-forward']));
  await user.selectOptions(screen.getByLabelText('Clock scenario'), 'forward');
  await user.click(screen.getByRole('button', { name: 'Measure virtual clock' }));
  await waitFor(() => expect(screen.getByText('Not applied')).toBeVisible());
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
});
it.each([
  { ...fixtures['symmetric-low'], source: 'live' },
  {
    ...fixtures['symmetric-low'],
    data: { ...fixtures['symmetric-low'].data, true_offset_ns: null },
  },
  { ...fixtures.fixed, data: { points: [] } },
])('rejects unsupported delay boundaries', (value) =>
  expect(() => readDelayResponse(value)).toThrow(),
);
it('rejects mismatched reference instants and missing snapshots', () => {
  const copy = structuredClone(fixtures['sync-symmetric']);
  copy.data.after.reference_unix_ns = '1';
  expect(() => readSync(copy)).toThrow();
  expect(() => readSync({ ...copy, data: {} })).toThrow();
});
