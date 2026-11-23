"""Thin local API over existing services. No automatic probes or retries."""
import math
import threading
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException

from ntp_sync_lab.api.schemas import (
    DelayInput, ErrorResult, MeasurementInput, ReplayInput, ReplayResult, Result,
    SeriesResult, SyncInput, SyncResult,
)
from ntp_sync_lab.core.client import MeasurementConfig, measure_once
from ntp_sync_lab.core.clock import SystemClock
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.core.transport import SystemResolver, UdpTransport
from ntp_sync_lab.errors import InvalidInputError, NtpSyncLabError, RateLimitedError
from ntp_sync_lab.experiments.delay import (
    DEFAULT_REFERENCE_UNIX_NS, MAX_DELAY_NS, _milliseconds_to_ns,
    equal_increase_sweep, fixed_rtt_sweep, make_delay_config, run_delay,
)
from ntp_sync_lab.experiments.replay import make_replay
from ntp_sync_lab.experiments.scenarios import list_scenarios, scenario_recording
from ntp_sync_lab.experiments.synchronization import make_sync_config, run_sync
from ntp_sync_lab.serialization import (
    delay_to_contract, measurement_to_contract, series_contract, sync_to_contract,
)

STATUS = {'INVALID_INPUT': 422, 'NOT_FOUND': 404, 'RATE_LIMITED': 429,
          'NTP_TIMEOUT': 504, 'DNS_FAILURE': 503, 'NETWORK_UNREACHABLE': 503,
          'LIVE_STATE_UNAVAILABLE': 503, 'INVALID_RECORDING': 503}


def metadata():
    return dict(result_id=uuid4().hex, created_at_utc=datetime.now(timezone.utc))


def error_response(code, message, status, details=None):
    details = details or {}
    headers = {}
    retry = details.get('retry_after_ns')
    if status == 429 and isinstance(retry, int):
        headers['Retry-After'] = str(max(1, math.ceil(retry / 1_000_000_000)))
    return JSONResponse({'schema_version': '1', 'error': {
        'code': code, 'message': message, 'details': details}}, status_code=status, headers=headers)


class LiveService:
    """One shared guard and cached numeric targets; config never performs DNS."""
    def __init__(self, *, clock=None, resolver=None, transport=None, guard=None):
        self.clock = clock if clock is not None else SystemClock()
        self.resolver = resolver if resolver is not None else SystemResolver()
        self.transport = transport if transport is not None else UdpTransport()
        self.guard = guard if guard is not None else PollGuard(self.clock)
        self.targets = {}
        self.lock = threading.Lock()

    def measure(self, config):
        target = self.resolver.resolve(config.server)
        with self.lock:
            self.targets[config.server] = target
        return measure_once(config, clock=self.clock, resolver=self.resolver,
                            transport=self.transport, guard=self.guard, resolved_target=target)

    def cooldown(self, server):
        with self.lock:
            target = self.targets.get(server)
        if target is None:
            return {'state': 'unknown', 'retry_after_ns': None}
        try:
            remaining = self.guard.remaining_ns(target.peer)
            return {'state': 'cooldown' if remaining else 'ready', 'retry_after_ns': str(remaining)}
        except NtpSyncLabError as error:
            return {'state': 'blocked', 'retry_after_ns': None, 'code': error.code}


def delay_document(body):
    values = body.model_dump(exclude_none=True)
    if 'reference_unix_ns' in values:
        values['reference_unix_ns'] = int(values['reference_unix_ns'])
    total = values.pop('round_trip_ms', None)
    points = values.pop('sweep_points', None)
    increments = values.pop('increments_ms', None)
    if total is not None:
        if any(key in values for key in ('preset', 'forward_ms', 'reverse_ms')) or increments is not None:
            raise InvalidInputError('fixed-RTT excludes preset, individual delays, and equal-increase mode')
        results = fixed_rtt_sweep(round_trip_ms=total, points=points or 9,
                                 true_offset_ms=values.get('true_offset_ms', '100'),
                                 processing_ms=values.get('processing_ms', '5'),
                                 reference_unix_ns=values.get('reference_unix_ns', DEFAULT_REFERENCE_UNIX_NS))
        config = results[0].config
        parameters = {'sweep_kind': 'fixed_rtt', 'point_count': len(results),
                      'round_trip_ns': str(results[0].metrics.round_trip_delay_ns),
                      'true_offset_ns': str(config.true_offset_ns),
                      'server_processing_ns': str(config.server_processing_ns),
                      'reference_unix_ns': str(config.reference_unix_ns)}
    else:
        if points is not None:
            raise InvalidInputError('sweep_points requires round_trip_ms')
        config = make_delay_config(**values)
        if increments is None:
            return delay_to_contract(run_delay(config), **metadata())
        results = equal_increase_sweep(config, increments_ms=increments)
        parameters = {'sweep_kind': 'equal_increase', 'point_count': len(results),
                      'base': delay_to_contract(run_delay(config), **metadata())['parameters'],
                      'increments_ns': [str(_milliseconds_to_ns('increment_ms', v, maximum_ns=MAX_DELAY_NS))
                                        for v in increments]}
    return series_contract(results, parameters, **metadata())


def create_app(*, live_service=None, servers=None):
    service = live_service if live_service is not None else LiveService()
    configured = dict(servers if servers is not None else {'pool': 'pool.ntp.org'})
    app = FastAPI(title='NTP Sync Lab API', version='0.1.0',
                  responses={status: {'model': ErrorResult} for status in (403, 404, 422, 429, 500, 502, 503, 504)})
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1'])
    slot = threading.Lock()

    @app.middleware('http')
    async def local_origin(request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            try:
                parsed = urlsplit(origin)
            except ValueError:
                return error_response('FORBIDDEN_ORIGIN', 'Invalid request origin', 403)
            if parsed.scheme != request.url.scheme or parsed.netloc != request.headers.get('host'):
                return error_response('FORBIDDEN_ORIGIN', 'Use the same-origin local API', 403)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Avoid reflecting raw JSON/nonfinite inputs or Pydantic exception objects.
        return error_response('INVALID_INPUT', 'Request validation failed', 422,
                              {'issues': [{'location': list(e['loc']), 'message': e['msg']} for e in error.errors()]})

    @app.exception_handler(NtpSyncLabError)
    async def domain_error(request, error):
        return error_response(error.code, str(error), STATUS.get(error.code, 502), error.details)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return error_response('NOT_FOUND' if error.status_code == 404 else 'HTTP_ERROR',
                              str(error.detail), error.status_code)

    @app.exception_handler(Exception)
    async def internal_error(request, error):
        return error_response('INTERNAL_ERROR', 'Unexpected internal error', 500)

    @app.get('/api/v1/health')
    def health():
        return {'schema_version': '1', 'status': 'ok'}

    @app.get('/api/v1/config')
    def config():
        return {'schema_version': '1', 'servers': [
            {'id': key, 'hostname': host, 'cooldown': service.cooldown(host)} for key, host in configured.items()],
            'live_busy': slot.locked(), 'units': {'duration_input': 'decimal milliseconds string', 'timestamp': 'Unix nanoseconds string'},
            'bounds': {'offset_ms': ['-60000', '60000'], 'one_way_ms': ['0', '2000'],
                       'processing_ms': ['0', '500'], 'sweep_points': [2, 200], 'timeout_seconds': [0.1, 10]},
            'minimum_poll_interval_ns': '64000000000'}

    @app.get('/api/v1/scenarios')
    def scenarios():
        return {'schema_version': '1', 'scenarios': list_scenarios()}

    @app.get('/api/v1/recordings')
    def recordings():
        return {'schema_version': '1', 'recordings': [entry for entry in list_scenarios() if entry['source'] == 'live']}

    @app.post('/api/v1/measurements', response_model=Result)
    async def measurements(body: MeasurementInput):
        if body.server_id not in configured:
            return error_response('NOT_FOUND', 'Unknown configured server ID', 404)
        if not slot.acquire(blocking=False):
            raise RateLimitedError('A live measurement is already in progress', retry_after_ns=1_000_000_000)
        def execute():
            try:
                return measurement_to_contract(service.measure(MeasurementConfig(
                    configured[body.server_id], timeout_seconds=body.timeout_seconds)))
            finally:
                slot.release()
        # Shield worker completion on disconnect; release only inside worker, never retry.
        # No queued live operations: slot is acquired before submitting any worker.
        with anyio.CancelScope(shield=True):
            return await anyio.to_thread.run_sync(execute, abandon_on_cancel=False)

    @app.post('/api/v1/experiments/delay', response_model=Result | SeriesResult)
    def delay(body: DelayInput):
        return delay_document(body)

    @app.post('/api/v1/experiments/sync', response_model=SyncResult)
    def sync(body: SyncInput):
        values = body.model_dump(exclude_none=True)
        if 'reference_unix_ns' in values:
            values['reference_unix_ns'] = int(values['reference_unix_ns'])
        return sync_to_contract(run_sync(make_sync_config(**values)), **metadata())

    @app.post('/api/v1/replays', response_model=ReplayResult)
    def replay(body: ReplayInput):
        selected = body.scenario_id or body.recording_id
        entries = list_scenarios()
        allowed = [entry['id'] for entry in entries if body.recording_id is None or entry['source'] == 'live']
        if selected not in allowed:
            return error_response('NOT_FOUND', 'Unknown packaged recording/scenario ID', 404)
        return make_replay(scenario_recording(selected), replayed_at_utc=datetime.now(timezone.utc))

    return app


app = create_app()
