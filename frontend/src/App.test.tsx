import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { expect, it, vi } from 'vitest';
import App from './App';
import capture from '../../docs/evidence/p1.3-public-ntp.json';
import { readExchange, readReplay } from './api';
const exchange = capture.attempts[0].result;
const replay = {
  schema_version: '1',
  source: 'replay',
  experiment: 'real_exchange',
  provenance: { original_source: 'live' },
  recording: capture,
};
function setup(liveStatus = 200) {
  const calls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      calls.push(`${options?.method ?? 'GET'} ${url}`);
      if (url.endsWith('/config'))
        return Response.json({
          servers: [
            {
              id: 'pool',
              hostname: 'pool.ntp.org',
              cooldown: { state: 'unknown', retry_after_ns: null },
            },
          ],
          live_busy: false,
        });
      if (url.endsWith('/recordings'))
        return Response.json({
          recordings: [{ id: 'captured-public-ntp', purpose: 'Historical public capture' }],
        });
      if (url.endsWith('/replays')) return Response.json(replay);
      if (liveStatus !== 200)
        return Response.json(
          {
            schema_version: '1',
            error: {
              code: 'NTP_TIMEOUT',
              message: 'Fixture timeout',
              details: {},
            },
          },
          { status: liveStatus },
        );
      return Response.json(exchange);
    }),
  );
  render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
  return calls;
}
it('starts empty and never automatically measures or replays in StrictMode', async () => {
  const calls = setup();
  await screen.findByText('API connected');
  expect(calls.every((v) => v.startsWith('GET'))).toBe(true);
  expect(screen.queryByText('+81.0434325')).not.toBeInTheDocument();
});
it('loads an explicit historical capture, exact timestamps and backend metrics', async () => {
  setup();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Load captured exchange' }));
  expect(await screen.findByText('REPLAY · original LIVE')).toBeVisible();
  expect(screen.getByText('+81.0434325')).toBeVisible();
  expect(screen.getByText('Unknown')).toBeVisible();
  await user.click(screen.getByText('Four timestamps'));
  expect(screen.getByText('1794735025245506539 ns')).toBeVisible();
  await user.click(screen.getByText('How the estimate works'));
  expect(screen.getByText('= +81.0434325 ms')).toBeVisible();
});
it('keeps a failure visible and never silently loads replay', async () => {
  const calls = setup(504);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Measure once' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Fixture timeout');
  expect(calls.filter((v) => v.includes('POST'))).toEqual(['POST /api/v1/measurements']);
  await user.click(screen.getByRole('button', { name: 'Load captured exchange' }));
  expect(await screen.findByText('REPLAY · original LIVE')).toBeVisible();
});
it('prevents double submits and maintains cooldown', async () => {
  const calls = setup();
  await screen.findByText('API connected');
  const button = screen.getByRole('button', { name: 'Measure once' });
  fireEvent.click(button);
  fireEvent.click(button);
  await screen.findByText('LIVE MEASUREMENT');
  expect(calls.filter((v) => v === 'POST /api/v1/measurements')).toHaveLength(1);
  expect(screen.getByRole('button', { name: /Available in/ })).toBeDisabled();
});
it('switches Safari-style tabs by keyboard and preserves exchange state', async () => {
  setup();
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Load captured exchange' }));
  const tab = screen.getByRole('tab', { name: /Real NTP/ });
  tab.focus();
  await user.keyboard('{ArrowRight}');
  expect(screen.getByRole('tab', { name: /Network Delay/ })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  expect(screen.getByRole('tabpanel')).toHaveTextContent('Delay setup');
  await user.keyboard('{End}');
  expect(screen.getByRole('tab', { name: /Clock Synchronization/ })).toHaveFocus();
  await user.keyboard('{Home}');
  expect(screen.getByText('+81.0434325')).toBeVisible();
});
it('caps in-memory history at 20 entries', async () => {
  setup();
  const user = userEvent.setup();
  const button = await screen.findByRole('button', {
    name: 'Load captured exchange',
  });
  for (let i = 0; i < 22; i++) {
    await user.click(button);
    await waitFor(() => expect(button).not.toBeDisabled());
  }
  const history = screen.getByRole('list', { name: 'Session history' });
  expect(within(history).getAllByRole('listitem')).toHaveLength(20);
});
it('rejects incompatible or invented live truth', () => {
  expect(() =>
    readExchange({
      ...exchange,
      data: { ...exchange.data, true_offset_ns: '0' },
    }),
  ).toThrow();
  expect(() => readReplay({ ...replay, recording: { attempts: [] } })).toThrow(
    'no successful exchange',
  );
});
it('shows API unavailability and keeps measurement disabled', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
  render(<App />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not connect');
  expect(screen.getByRole('button', { name: 'Measure once' })).toBeDisabled();
});
it('keeps the last successful result explicitly separate from a later failure', async () => {
  setup(504);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Load captured exchange' }));
  await screen.findByText('+81.0434325');
  await user.click(screen.getByRole('button', { name: 'Measure once' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('NTP_TIMEOUT');
  expect(screen.getByText(/not a result of the failed attempt/)).toBeVisible();
  expect(screen.getByText('REPLAY · original LIVE')).toBeVisible();
});
it('respects persisted cooldown and control blocks from configuration', async () => {
  setup();
  await screen.findByText('API connected');
  const fetch = vi.mocked(globalThis.fetch);
  fetch.mockImplementation(async (url) =>
    Response.json(
      String(url).endsWith('/recordings')
        ? { recordings: [] }
        : {
            servers: [
              {
                id: 'pool',
                hostname: 'pool.ntp.org',
                cooldown: {
                  state: 'blocked',
                  retry_after_ns: null,
                  code: 'SERVER_CONTROL',
                },
              },
            ],
            live_busy: false,
          },
    ),
  );
  // Remount is an independent app session; existing backend state must still block it.
  const { unmount } = render(<App />);
  await screen.findByRole('button', { name: 'Target blocked' });
  expect(screen.getByRole('button', { name: 'Target blocked' })).toBeDisabled();
  expect(screen.getByText(/SERVER_CONTROL/)).toBeVisible();
  unmount();
});
it('does not report a cached API connection as healthy after connection loss', async () => {
  setup();
  const user = userEvent.setup();
  await screen.findByText('API connected');
  const fetch = vi.mocked(globalThis.fetch);
  const original = fetch.getMockImplementation()!;
  fetch.mockImplementation((...args) =>
    String(args[0]).endsWith('/measurements')
      ? Promise.reject(new TypeError('connection lost'))
      : original(...args),
  );
  await user.click(screen.getByRole('button', { name: 'Measure once' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('API_UNAVAILABLE');
  expect(screen.getByText('API unavailable', { exact: true })).toBeVisible();
});
