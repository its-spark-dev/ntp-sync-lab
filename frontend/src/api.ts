import type { components } from './generated/api';
export type Exchange = components['schemas']['Result'];
export type Replay = components['schemas']['ReplayResult'];
export type Failure = components['schemas']['ErrorInfo'];
export type Server = {
  id: string;
  hostname: string;
  cooldown: { state: string; retry_after_ns: string | null; code?: string };
};
export type Config = { servers: Server[]; live_busy: boolean };
export type Recording = { id: string; purpose: string };
export type Observation = {
  exchange: Exchange;
  source: 'live' | 'replay';
  original: Exchange | Replay;
};

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public retrySeconds?: number,
  ) {
    super(message);
  }
}
export const object = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

async function request(path: string, body?: unknown): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(
      '/api/v1/' + path,
      body === undefined
        ? { signal: AbortSignal.timeout(10_000) }
        : {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          },
    );
  } catch {
    throw new ApiError(
      'API_UNAVAILABLE',
      'The local API could not be reached. Check that the Python server is running. No retry was made.',
    );
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = object(payload) && object(payload.error) ? payload.error : {};
    const retry = response.headers.get('Retry-After');
    throw new ApiError(
      typeof error.code === 'string' ? error.code : 'HTTP_ERROR',
      typeof error.message === 'string'
        ? error.message
        : `The API returned HTTP ${response.status}.`,
      object(error.details) ? error.details : {},
      retry && /^\d+$/.test(retry) ? Number(retry) : undefined,
    );
  }
  return payload;
}

export function readExchange(value: unknown): Exchange {
  if (
    !object(value) ||
    value.schema_version !== '1' ||
    value.experiment !== 'real_exchange' ||
    value.source !== 'live' ||
    typeof value.result_id !== 'string' ||
    typeof value.created_at_utc !== 'string' ||
    !object(value.provenance) ||
    !object(value.parameters) ||
    !object(value.data) ||
    !Array.isArray(value.assumptions) ||
    !value.assumptions.every((v) => typeof v === 'string') ||
    !Array.isArray(value.warnings) ||
    !value.warnings.every((v) => typeof v === 'string')
  )
    throw new ApiError('INVALID_RESULT', 'The API did not return a supported real exchange.');
  const data = value.data;
  if (
    !object(data.timestamps) ||
    !['t1_unix_ns', 't2_unix_ns', 't3_unix_ns', 't4_unix_ns'].every(
      (k) =>
        typeof (data.timestamps as Record<string, unknown>)[k] === 'string' &&
        /^-?\d+$/.test(String((data.timestamps as Record<string, unknown>)[k])),
    ) ||
    ![
      'estimated_offset_ns',
      'round_trip_delay_ns',
      'client_elapsed_ns',
      'server_processing_ns',
    ].every((k) => typeof data[k] === 'string' && /^-?\d+(?:\.\d+)?$/.test(data[k] as string)) ||
    data.true_offset_ns !== null ||
    data.estimation_error_ns !== null
  )
    throw new ApiError(
      'INVALID_RESULT',
      'The result has invalid precision or live ground truth fields.',
    );
  return value as Exchange;
}

export function readReplay(value: unknown): Observation {
  if (
    !object(value) ||
    value.source !== 'replay' ||
    value.schema_version !== '1' ||
    !object(value.recording)
  )
    throw new ApiError('INVALID_RECORDING', 'Unsupported replay response.');
  const original = value.recording;
  if (Array.isArray(original.attempts)) {
    const attempt = original.attempts.find((v) => object(v) && v.result !== null);
    if (!object(attempt))
      throw new ApiError('NO_VALID_SAMPLE', 'This recording contains no successful exchange.');
    return {
      source: 'replay',
      exchange: readExchange(attempt.result),
      original: value as Replay,
    };
  }
  return {
    source: 'replay',
    exchange: readExchange(original),
    original: value as Replay,
  };
}

export async function getConfig(): Promise<Config> {
  const value = await request('config');
  if (
    !object(value) ||
    !Array.isArray(value.servers) ||
    typeof value.live_busy !== 'boolean' ||
    !value.servers.every(
      (s) =>
        object(s) &&
        typeof s.id === 'string' &&
        typeof s.hostname === 'string' &&
        object(s.cooldown) &&
        typeof s.cooldown.state === 'string' &&
        (s.cooldown.retry_after_ns === null ||
          (typeof s.cooldown.retry_after_ns === 'string' &&
            /^\d+$/.test(s.cooldown.retry_after_ns))),
    )
  )
    throw new ApiError('INVALID_CONFIG', 'Unsupported API configuration.');
  return value as Config;
}
export async function getRecordings(): Promise<Recording[]> {
  const value = await request('recordings');
  if (
    !object(value) ||
    !Array.isArray(value.recordings) ||
    !value.recordings.every(
      (v) => object(v) && typeof v.id === 'string' && typeof v.purpose === 'string',
    )
  )
    throw new ApiError('INVALID_CATALOG', 'Unsupported recording catalog.');
  return value.recordings as Recording[];
}
export async function measure(server_id: string, timeout_seconds: number): Promise<Observation> {
  const exchange = readExchange(await request('measurements', { server_id, timeout_seconds }));
  return { source: 'live', exchange, original: exchange };
}
export async function replay(recording_id: string) {
  return readReplay(await request('replays', { recording_id }));
}
