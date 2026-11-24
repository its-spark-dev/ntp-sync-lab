import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  getConfig,
  getRecordings,
  measure,
  replay,
  type Config,
  type Observation,
  type Recording,
} from './api';
import { cooldownDuration } from './format';
export type HistoryEntry = Observation & { key: number };
const asError = (e: unknown) =>
  e instanceof ApiError
    ? e
    : new ApiError(
        'UNEXPECTED_RESULT',
        'The response could not be displayed. No automatic retry was made.',
      );

export function useExchange() {
  const [config, setConfig] = useState<Config | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [setupError, setSetupError] = useState<ApiError | null>(null);
  const [serverId, setServerId] = useState('');
  const [recordingId, setRecordingId] = useState('');
  const [timeout, setTimeoutValue] = useState(3);
  const [busy, setBusy] = useState<'live' | 'replay' | null>(null);
  const lock = useRef(false);
  const serial = useRef(0);
  const [observation, setObservation] = useState<HistoryEntry | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [dueByServer, setDueByServer] = useState<Record<string, number>>({});
  const [now, setNow] = useState(() => performance.now());
  const applyConfig = useCallback((value: Config) => {
    setConfig(value);
    setServerId((previous) =>
      value.servers.some((s) => s.id === previous) ? previous : (value.servers[0]?.id ?? ''),
    );
    const observedAt = performance.now();
    setDueByServer((previous) => {
      const next = { ...previous };
      for (const server of value.servers) {
        // Unknown after restart must not clear a locally known wait.
        if (server.cooldown.state === 'cooldown')
          next[server.id] = observedAt + cooldownDuration(server.cooldown.retry_after_ns) * 1000;
        else if (server.cooldown.state === 'ready') next[server.id] = 0;
      }
      return next;
    });
  }, []);
  const refresh = useCallback(async () => {
    try {
      applyConfig(await getConfig());
    } catch {
      /* existing cooldown/failure remains visible; next request is still guarded by Python */
    }
  }, [applyConfig]);
  const setup = useCallback(async () => {
    setSetupError(null);
    try {
      const [settings, catalog] = await Promise.all([getConfig(), getRecordings()]);
      applyConfig(settings);
      setRecordings(catalog);
      setRecordingId((previous) =>
        catalog.some((r) => r.id === previous) ? previous : (catalog[0]?.id ?? ''),
      );
    } catch (e) {
      setSetupError(asError(e));
    }
  }, [applyConfig]);
  useEffect(() => {
    void setup();
  }, [setup]); // GET only, including StrictMode remounts.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(performance.now()), 500);
    return () => window.clearInterval(timer);
  }, []);
  const execute = async (kind: 'live' | 'replay') => {
    if (lock.current) return;
    lock.current = true;
    setBusy(kind);
    setError(null);
    const requestedServer = serverId;
    try {
      const value =
        kind === 'live' ? await measure(requestedServer, timeout) : await replay(recordingId);
      const entry = { ...value, key: ++serial.current };
      setObservation(entry);
      setHistory((previous) => [entry, ...previous].slice(0, 20));
      if (kind === 'live')
        setDueByServer((previous) => ({
          ...previous,
          [requestedServer]: performance.now() + 64_000,
        }));
    } catch (e) {
      const failure = asError(e);
      setError(failure);
      if (kind === 'live' && failure.retrySeconds)
        setDueByServer((previous) => ({
          ...previous,
          [requestedServer]: performance.now() + failure.retrySeconds! * 1000,
        }));
    } finally {
      if (kind === 'live') await refresh();
      setBusy(null);
      lock.current = false;
    }
  };
  return {
    config,
    recordings,
    setupError,
    setup,
    serverId,
    setServerId,
    recordingId,
    setRecordingId,
    timeout,
    setTimeoutValue,
    busy,
    observation,
    history,
    error,
    execute,
    due: dueByServer[serverId] ?? 0,
    now,
    selectHistory: (entry: HistoryEntry) => {
      setObservation(entry);
    },
    refresh,
  };
}
