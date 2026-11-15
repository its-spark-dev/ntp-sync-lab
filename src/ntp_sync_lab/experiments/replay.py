"""Bounded, offline recording validation. No live client, resolver or socket imports.

Validation proves internal consistency, not authenticity of a claimed capture.
Replay wraps the original document unchanged, preserving all capture metadata.
"""

import copy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
import re
from statistics import median

from ntp_sync_lab.core.calculations import calculate_exchange
from ntp_sync_lab.core.clock import ClockReading, check_clock_interval
from ntp_sync_lab.core.packet import ClientRequest, NtpPeer, parse_packet, validate_response
from ntp_sync_lab.errors import InvalidRecordingError, NtpSyncLabError
from ntp_sync_lab.experiments.delay import (
    DelayConfig, equal_increase_sweep, fixed_rtt_sweep, run_delay,
)
from ntp_sync_lab.experiments.synchronization import SyncConfig, run_sync
from ntp_sync_lab.models import TimestampQuad
from ntp_sync_lab.serialization import (
    _offset_string, delay_to_contract, series_contract, sync_to_contract,
)

MAX_RECORDING_BYTES = 1_048_576
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")


def integer_ns(value):
    if not isinstance(value, str) or not _INTEGER.fullmatch(value) or value == '-0':
        raise InvalidRecordingError('nanosecond values must be canonical integer strings')
    return int(value)


def milliseconds(ns):
    """Exact integer-nanosecond to millisecond string conversion, without context/float loss."""
    sign = '-' if ns < 0 else ''
    whole, remainder = divmod(abs(ns), 1_000_000)
    return f'{sign}{whole}' + ('.' + f'{remainder:06d}'.rstrip('0') if remainder else '')


def utc_date(value):
    if not isinstance(value, str):
        raise InvalidRecordingError('UTC metadata must be an ISO-8601 string')
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.utcoffset() != timedelta(0):
        raise InvalidRecordingError('recording date must include a UTC timezone')
    return date


def _same(actual, expected, path='recording'):
    if type(actual) is not type(expected):
        raise InvalidRecordingError(f'{path}: invalid type or units')
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise InvalidRecordingError(f'{path}: missing or unsupported fields')
        for key in expected:
            _same(actual[key], expected[key], f'{path}.{key}')
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise InvalidRecordingError(f'{path}: wrong number of entries')
        for index, (left, right) in enumerate(zip(actual, expected)):
            _same(left, right, f'{path}[{index}]')
    elif actual != expected:
        raise InvalidRecordingError(f'{path}: inconsistent value')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidRecordingError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def parse_recording(text):
    try:
        if len(text.encode('utf-8')) > MAX_RECORDING_BYTES:
            raise InvalidRecordingError('recording exceeds the 1 MiB limit')
        def nonfinite(value):
            raise InvalidRecordingError(f'nonfinite JSON value: {value}')
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=nonfinite)
        return validate_recording(document)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as error:
        if isinstance(error, InvalidRecordingError):
            raise
        raise InvalidRecordingError(f'invalid recording: {error}') from error


def load_recording(path):
    with Path(path).open('rb') as handle:
        data = handle.read(MAX_RECORDING_BYTES + 1)
    if len(data) > MAX_RECORDING_BYTES:
        raise InvalidRecordingError('recording exceeds the 1 MiB limit')
    try:
        return parse_recording(data.decode('utf-8'))
    except UnicodeError as error:
        raise InvalidRecordingError('recording must be UTF-8 JSON') from error


def delay_config(parameters):
    _same(sorted(parameters), sorted(('true_offset_ns', 'forward_delay_ns', 'reverse_delay_ns',
                                     'server_processing_ns', 'reference_unix_ns', 'preset_id')))
    return DelayConfig(**{
        key: parameters[key] if key == 'preset_id' else integer_ns(parameters[key])
        for key in ('true_offset_ns', 'forward_delay_ns', 'reverse_delay_ns',
                    'server_processing_ns', 'reference_unix_ns', 'preset_id')
    })


def _validate_simulation(document):
    parameters = document['parameters']
    metadata = dict(result_id=document['result_id'], created_at_utc=utc_date(document['created_at_utc']))
    if document['experiment'] == 'clock_sync':
        config = SyncConfig(**{key: value if key == 'mode' else integer_ns(value)
                               for key, value in parameters.items()})
        expected = sync_to_contract(run_sync(config), **metadata)
    elif document['experiment'] == 'network_delay':
        if 'sweep_kind' not in parameters:
            expected = delay_to_contract(run_delay(delay_config(parameters)), **metadata)
        else:
            count = parameters['point_count']
            if type(count) is not int or not 2 <= count <= 200:
                raise InvalidRecordingError('sweep point count must be 2–200')
            if parameters['sweep_kind'] == 'fixed_rtt':
                _same(sorted(parameters), sorted(('sweep_kind', 'point_count', 'round_trip_ns',
                                                   'true_offset_ns', 'server_processing_ns', 'reference_unix_ns')))
                results = fixed_rtt_sweep(
                    round_trip_ms=milliseconds(integer_ns(parameters['round_trip_ns'])), points=count,
                    true_offset_ms=milliseconds(integer_ns(parameters['true_offset_ns'])),
                    processing_ms=milliseconds(integer_ns(parameters['server_processing_ns'])),
                    reference_unix_ns=integer_ns(parameters['reference_unix_ns']),
                )
            elif parameters['sweep_kind'] == 'equal_increase':
                _same(sorted(parameters), sorted(('sweep_kind', 'point_count', 'base', 'increments_ns')))
                if not isinstance(parameters['increments_ns'], list) or len(parameters['increments_ns']) != count:
                    raise InvalidRecordingError('inconsistent increment count')
                results = equal_increase_sweep(delay_config(parameters['base']), increments_ms=[
                    milliseconds(integer_ns(value)) for value in parameters['increments_ns']
                ])
            else:
                raise InvalidRecordingError('unsupported delay sweep kind')
            expected = series_contract(results, parameters, **metadata)
    else:
        raise InvalidRecordingError('unsupported simulated experiment')
    _same(document, expected)


def _validate_live(document):
    _same(sorted(document), sorted(('schema_version', 'experiment', 'source', 'result_id',
                                    'created_at_utc', 'provenance', 'parameters', 'data', 'warnings', 'assumptions')))
    if document['experiment'] != 'real_exchange':
        raise InvalidRecordingError('live source requires a real exchange')
    if not isinstance(document['result_id'], str) or not document['result_id'].strip():
        raise InvalidRecordingError('missing result ID')
    utc_date(document['created_at_utc'])
    data, provenance, parameters = document['data'], document['provenance'], document['parameters']
    parameter_keys = ['server', 'timeout_seconds']
    if 'discontinuity_threshold_ns' in parameters:
        parameter_keys.append('discontinuity_threshold_ns')
    _same(sorted(parameters), sorted(parameter_keys))
    # Legacy schema-1 captures used the documented default without storing it.
    # Validate that default in place; never insert metadata into old captures.
    threshold = integer_ns(parameters.get('discontinuity_threshold_ns', '5000000'))
    if threshold <= 0:
        raise InvalidRecordingError('invalid clock discontinuity threshold')
    _same(sorted(provenance), sorted(('description', 'server', 'peer', 'local_peer', 'capture_time_utc')))
    _same(sorted(data), sorted(('timestamps', 'estimated_offset_ns', 'round_trip_delay_ns',
                               'client_elapsed_ns', 'server_processing_ns', 'true_offset_ns', 'estimation_error_ns',
                               'request_packet_hex', 'response_packet_hex', 'server_header', 'raw_timestamps',
                               'clock_capture', 'ignored_count', 'ignored_datagrams')))
    _same(document['warnings'], [])
    if not isinstance(provenance['description'], str) or not provenance['description'].strip():
        raise InvalidRecordingError('missing capture description')
    if not isinstance(parameters['server'], str) or provenance['server'] != parameters['server']:
        raise InvalidRecordingError('inconsistent server provenance')
    timeout = parameters['timeout_seconds']
    if type(timeout) not in (int, float) or not 0.1 <= timeout <= 10:
        raise InvalidRecordingError('invalid UDP timeout')
    quad = TimestampQuad(**{key: integer_ns(value) for key, value in data['timestamps'].items()})
    capture = data['clock_capture']
    _same(sorted(capture), sorted(('t1_wall_ns', 't1_monotonic_ns', 't4_wall_ns', 't4_monotonic_ns',
                                   't1_read_span_ns', 't4_read_span_ns', 'wall_monotonic_discrepancy_ns', 'clock_info')))
    info = capture['clock_info']
    _same(sorted(info), sorted(('wall_resolution_ns', 'monotonic_resolution_ns', 'wall_adjustable', 'implementation')))
    for key in ('wall_resolution_ns', 'monotonic_resolution_ns'):
        if type(info[key]) is not int or info[key] <= 0:
            raise InvalidRecordingError('invalid clock resolution units/value')
    if type(info['wall_adjustable']) is not bool or not isinstance(info['implementation'], str):
        raise InvalidRecordingError('invalid clock implementation metadata')
    for key in ('request_packet_hex', 'response_packet_hex'):
        if bytes.fromhex(data[key]).hex() != data[key]:
            raise InvalidRecordingError('packet hex must be canonical')
    request = ClientRequest(bytes.fromhex(data['request_packet_hex']), integer_ns(capture['t1_wall_ns']))
    peer = NtpPeer(**provenance['peer'])
    NtpPeer(**provenance['local_peer'])
    response = validate_response(
        parse_packet(bytes.fromhex(data['response_packet_hex'])), request,
        expected_peer=peer, actual_peer=peer, t4_unix_ns=quad.t4_unix_ns,
    )
    _same(data['timestamps'], {key: str(getattr(response.timestamps, key)) for key in (
        't1_unix_ns', 't2_unix_ns', 't3_unix_ns', 't4_unix_ns')})
    metrics = calculate_exchange(quad)
    for key in ('estimated_offset_ns', 'round_trip_delay_ns', 'client_elapsed_ns', 'server_processing_ns'):
        value = getattr(metrics, key)
        _same(data[key], _offset_string(value) if isinstance(value, Fraction) else str(value), key)
    _same(data['true_offset_ns'], None)
    _same(data['estimation_error_ns'], None)
    packet = response.packet
    _same(data['server_header'], {
        'version': packet.version, 'mode': packet.mode, 'stratum': packet.stratum,
        'leap_indicator': packet.leap_indicator, 'packet_length': len(packet.raw),
        'poll_exponent': packet.poll_exponent, 'precision_exponent': packet.precision_exponent,
        'root_delay_raw': packet.root_delay_raw, 'root_dispersion_raw': packet.root_dispersion_raw,
        'reference_id_hex': packet.reference_id.hex(),
    })
    _same(data['raw_timestamps'], {name: {
        'seconds': getattr(packet, f'{name}_timestamp').seconds,
        'fraction': getattr(packet, f'{name}_timestamp').fraction,
    } for name in ('reference', 'originate', 'receive', 'transmit')})
    _same(capture['t4_wall_ns'], str(quad.t4_unix_ns))
    for key in ('t1_read_span_ns', 't4_read_span_ns'):
        if integer_ns(capture[key]) < 0:
            raise InvalidRecordingError('negative clock read span')
    discrepancy = check_clock_interval(
        ClockReading(integer_ns(capture['t1_wall_ns']), integer_ns(capture['t1_monotonic_ns']),
                     integer_ns(capture['t1_read_span_ns'])),
        ClockReading(integer_ns(capture['t4_wall_ns']), integer_ns(capture['t4_monotonic_ns']),
                     integer_ns(capture['t4_read_span_ns'])), threshold,
    )
    _same(capture['wall_monotonic_discrepancy_ns'], str(discrepancy))
    seconds, ns = divmod(quad.t4_unix_ns, 1_000_000_000)
    captured = (datetime.fromtimestamp(seconds, timezone.utc) + timedelta(microseconds=ns // 1000)).isoformat().replace('+00:00', 'Z')
    _same(provenance['capture_time_utc'], captured)
    _same(document['created_at_utc'], captured)
    if not isinstance(data['ignored_datagrams'], list):
        raise InvalidRecordingError('ignored datagrams must be a list')
    if type(data['ignored_count']) is not int or data['ignored_count'] < len(data['ignored_datagrams']):
        raise InvalidRecordingError('invalid ignored-datagram diagnostics')
    if len(data['ignored_datagrams']) > 20:
        raise InvalidRecordingError('too many ignored-datagram diagnostics')
    if len(data['ignored_datagrams']) != min(20, data['ignored_count']):
        raise InvalidRecordingError('inconsistent ignored count')
    for ignored in data['ignored_datagrams']:
        _same(sorted(ignored), ['packet_length', 'peer', 'reason'])
        NtpPeer(**ignored['peer'])
        if ignored['reason'] not in ('PEER_MISMATCH', 'ORIGIN_MISMATCH'):
            raise InvalidRecordingError('unsupported ignored-datagram reason')
        if type(ignored['packet_length']) is not int or not 0 <= ignored['packet_length'] <= 65535:
            raise InvalidRecordingError('invalid datagram size')


def _validate_batch(document, depth):
    _same(sorted(document), sorted(('schema_version', 'experiment', 'source', 'server',
                                    'requested_count', 'attempts', 'interrupted', 'stop_reason', 'summary')))
    if document['source'] != 'live' or document['experiment'] != 'real_exchange':
        raise InvalidRecordingError('invalid measurement batch source/experiment')
    count, attempts = document['requested_count'], document['attempts']
    if type(count) is not int or not 1 <= count <= 10 or not isinstance(attempts, list) or len(attempts) > count:
        raise InvalidRecordingError('invalid batch size')
    if type(document['interrupted']) is not bool:
        raise InvalidRecordingError('invalid interruption flag')
    if document['stop_reason'] is not None and not isinstance(document['stop_reason'], str):
        raise InvalidRecordingError('invalid batch stop reason')
    if not isinstance(document['server'], str) or not document['server']:
        raise InvalidRecordingError('invalid batch server')
    if len(attempts) < count and document['stop_reason'] is None:
        raise InvalidRecordingError('partial batch is missing its stop reason')
    if document['interrupted'] != (document['stop_reason'] == 'INTERRUPTED'):
        raise InvalidRecordingError('inconsistent interruption status')
    offsets, delays = [], []
    for index, attempt in enumerate(attempts, 1):
        _same(sorted(attempt), ['error', 'number', 'result'])
        _same(attempt['number'], index)
        result, error = attempt['result'], attempt['error']
        if (result is None) == (error is None):
            raise InvalidRecordingError('each attempt requires exactly one result or failure')
        if result is not None:
            _validate(result, depth + 1)
            if result['source'] != 'live' or result['parameters']['server'] != document['server']:
                raise InvalidRecordingError('batch attempt does not match live server/source')
            offsets.append(Fraction(result['data']['estimated_offset_ns']))
            delays.append(integer_ns(result['data']['round_trip_delay_ns']))
        else:
            if not isinstance(error, dict) or set(error) != {'code', 'message', 'details'}:
                raise InvalidRecordingError('invalid failure structure')
            if not isinstance(error['code'], str) or not re.fullmatch('[A-Z_]+', error['code']):
                raise InvalidRecordingError('invalid failure code')
            if not isinstance(error['message'], str) or not isinstance(error['details'], dict):
                raise InvalidRecordingError('invalid failure diagnostic types')
            for key, value in error['details'].items():
                if key.endswith('_ns'):
                    integer_ns(value)
    expected = None if not offsets else {
        'valid_count': len(offsets), 'median_offset_ns': _offset_string(median(offsets)),
        'minimum_round_trip_delay_ns': str(min(delays)), 'offset_range_ns': _offset_string(max(offsets)-min(offsets)),
        'interpretation': 'Descriptive variation only; true synchronization accuracy is unknown',
    }
    _same(document['summary'], expected)


def _validate(document, depth):
    if depth > 12 or not isinstance(document, dict) or document.get('schema_version') != '1':
        raise InvalidRecordingError('unsupported schema or excessive recording nesting')
    source = document.get('source')
    if source == 'replay':
        _same(sorted(document), sorted(('schema_version', 'experiment', 'source', 'provenance', 'recording')))
        _same(sorted(document['provenance']), sorted(('original_source', 'replayed_at_utc', 'description')))
        utc_date(document['provenance']['replayed_at_utc'])
        _validate(document['recording'], depth + 1)
        original = original_recording(document['recording'])
        _same(document['provenance']['original_source'], original['source'])
        _same(document['experiment'], original['experiment'])
        _same(document['provenance']['description'], 'Offline replay; no network request sent')
    elif 'attempts' in document:
        _validate_batch(document, depth)
    elif source in ('simulation', 'live'):
        for name in ('warnings', 'assumptions'):
            if not isinstance(document[name], list):
                raise InvalidRecordingError(f'{name} must be a list')
        if not all(isinstance(value, str) for value in document['assumptions']):
            raise InvalidRecordingError('assumptions must contain text')
        if source == 'simulation':
            _validate_simulation(document)
        else:
            _validate_live(document)
    else:
        raise InvalidRecordingError('unsupported recording source')


def validate_recording(document):
    try:
        # Reject nonfinite values even for direct callers, not just the JSON reader.
        encoded = json.dumps(document, allow_nan=False)
        if len(encoded.encode()) > MAX_RECORDING_BYTES:
            raise InvalidRecordingError('recording exceeds the 1 MiB limit')
        _validate(document, 0)
        return document
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError, NtpSyncLabError) as error:
        if isinstance(error, InvalidRecordingError):
            raise
        raise InvalidRecordingError(f'invalid recording: {error}') from error


def original_recording(document):
    while document['source'] == 'replay':
        document = document['recording']
    return document


def make_replay(document, *, replayed_at_utc):
    validate_recording(document)
    original = original_recording(document)
    replay = {
        'schema_version': '1', 'experiment': original['experiment'], 'source': 'replay',
        'provenance': {'original_source': original['source'],
                       'replayed_at_utc': replayed_at_utc.isoformat().replace('+00:00', 'Z'),
                       'description': 'Offline replay; no network request sent'},
        'recording': copy.deepcopy(document),
    }
    return validate_recording(replay)
