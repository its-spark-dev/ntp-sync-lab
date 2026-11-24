import type { components } from './generated/api';
import { ApiError, object, request } from './api';
export type DelayInput = components['schemas']['DelayInput'];
export type SyncInput = components['schemas']['SyncInput'];
export type DelayResult = components['schemas']['Result'];
export type DelaySeries = components['schemas']['SeriesResult'];
export type SyncResult = components['schemas']['SyncResult'];
const exact = (v: unknown): v is string => typeof v === 'string' && /^-?\d+(?:\.\d+)?$/.test(v);
const integer = (v: unknown) => typeof v === 'string' && /^-?\d+$/.test(v);

function envelope(value: unknown, experiment: string): asserts value is Record<string, unknown> {
  if (
    !object(value) ||
    value.schema_version !== '1' ||
    value.source !== 'simulation' ||
    value.experiment !== experiment ||
    typeof value.result_id !== 'string' ||
    typeof value.created_at_utc !== 'string' ||
    !object(value.data) ||
    !object(value.parameters) ||
    !object(value.provenance) ||
    !Array.isArray(value.assumptions) ||
    !value.assumptions.every((v) => typeof v === 'string')
  )
    throw new ApiError('INVALID_RESULT', 'The API did not return a supported simulation.');
}
function metrics(value: unknown) {
  if (
    !object(value) ||
    !object(value.timestamps) ||
    !['t1_unix_ns', 't2_unix_ns', 't3_unix_ns', 't4_unix_ns'].every((k) =>
      integer((value.timestamps as Record<string, unknown>)[k]),
    ) ||
    ![
      'estimated_offset_ns',
      'round_trip_delay_ns',
      'client_elapsed_ns',
      'server_processing_ns',
      'true_offset_ns',
      'estimation_error_ns',
    ].every((k) => exact(value[k]))
  ) {
    throw new ApiError('INVALID_RESULT', 'Simulation precision or known truth is missing.');
  }
}
export function readDelay(value: unknown): DelayResult {
  envelope(value, 'network_delay');
  metrics(value.data);
  if (
    !object(value.data) ||
    !integer(value.data.forward_delay_ns) ||
    !integer(value.data.reverse_delay_ns) ||
    typeof value.data.conclusion !== 'string'
  )
    throw new ApiError('INVALID_RESULT', 'The delay result is incomplete.');
  return value as DelayResult;
}
export function readDelayResponse(value: unknown): DelayResult | DelaySeries {
  envelope(value, 'network_delay');
  if (object(value.data) && Array.isArray(value.data.points)) {
    if (value.data.points.length < 2 || value.data.points.length > 200)
      throw new ApiError('INVALID_RESULT', 'Unsupported series size.');
    value.data.points.forEach(readDelay);
    return value as DelaySeries;
  }
  return readDelay(value);
}
export function readSync(value: unknown): SyncResult {
  envelope(value, 'clock_sync');
  metrics(value.data);
  const data = value.data;
  if (
    !object(data) ||
    !['initial_client_error_ns', 'applied_correction_ns', 'final_client_error_ns'].every((k) =>
      exact(data[k]),
    ) ||
    !['before', 'after'].every((k) => {
      const snapshot = data[k];
      return (
        object(snapshot) &&
        integer(snapshot.reference_unix_ns) &&
        exact(snapshot.virtual_client_unix_ns) &&
        exact(snapshot.client_error_ns)
      );
    }) ||
    !object(data.before) ||
    !object(data.after) ||
    data.before.reference_unix_ns !== data.after.reference_unix_ns ||
    !Array.isArray(data.timeline) ||
    data.timeline.length !== 3 ||
    !data.timeline.every(
      (p) =>
        object(p) &&
        Number.isInteger(p.sequence) &&
        typeof p.stage === 'string' &&
        integer(p.reference_unix_ns) &&
        exact(p.virtual_client_unix_ns) &&
        exact(p.client_error_ns) &&
        exact(p.applied_correction_ns),
    ) ||
    typeof data.conclusion !== 'string'
  )
    throw new ApiError('INVALID_RESULT', 'The virtual-clock snapshots are incomplete.');
  readDelay(data.measurement);
  return value as SyncResult;
}
export async function simulateDelay(input: DelayInput) {
  return readDelayResponse(await request('experiments/delay', input));
}
export async function simulateSync(input: SyncInput) {
  return readSync(await request('experiments/sync', input));
}
