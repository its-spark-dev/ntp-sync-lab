import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import socket

import pytest

from ntp_sync_lab.errors import InvalidRecordingError
from ntp_sync_lab.experiments.delay import make_delay_config, run_delay
from ntp_sync_lab.experiments.replay import (
    MAX_RECORDING_BYTES, load_recording, make_replay, parse_recording, validate_recording,
)
from ntp_sync_lab.experiments.scenarios import list_scenarios, scenario_recording
from ntp_sync_lab.experiments.synchronization import make_sync_config, run_sync
from ntp_sync_lab.serialization import delay_to_contract, sync_to_contract

DATE = datetime(2026, 11, 15, tzinfo=timezone.utc)


@pytest.fixture
def simulated():
    return delay_to_contract(run_delay(make_delay_config(preset='asymmetric-forward')),
                             result_id='fixture', created_at_utc=DATE)


def test_catalog_resources_are_valid_reproducible_and_explicitly_sourced():
    catalog = list_scenarios()
    assert len({entry['id'] for entry in catalog}) == len(catalog) == 10
    for entry in catalog:
        a = scenario_recording(entry['id'])
        assert a == scenario_recording(entry['id'])
        assert a['source'] == entry['source']
        assert validate_recording(a) is a


def test_public_capture_is_packaged_without_conversion_or_fabricated_fields():
    from importlib.resources import files
    resource = files('ntp_sync_lab').joinpath('fixtures', 'recordings', 'p1.3-public-ntp.json')
    evidence = Path(__file__).resolve().parents[2] / 'docs/evidence/p1.3-public-ntp.json'
    assert resource.read_bytes() == evidence.read_bytes()
    original = scenario_recording('captured-public-ntp')
    assert 'created_at_utc' not in original  # original native batch has no top-level capture date
    replay = make_replay(original, replayed_at_utc=DATE)
    assert replay['recording'] == original
    assert replay['source'] == 'replay' and replay['provenance']['original_source'] == 'live'
    assert replay['recording']['attempts'][0]['result']['created_at_utc'] == '2026-11-15T09:30:25.203822Z'
    assert replay['recording']['attempts'][0]['result']['data']['true_offset_ns'] is None


def test_replay_runs_with_all_socket_operations_disabled(simulated, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('network operations are forbidden in replay')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    for entry in list_scenarios():
        original = scenario_recording(entry['id'])
        replay = make_replay(original, replayed_at_utc=DATE)
        assert validate_recording(replay)
    assert make_replay(simulated, replayed_at_utc=DATE)['provenance']['original_source'] == 'simulation'


def test_nested_replay_preserves_previous_recording_without_refreshing_dates(simulated):
    first = make_replay(simulated, replayed_at_utc=DATE)
    second = make_replay(first, replayed_at_utc=DATE)
    assert second['recording'] == first
    assert second['provenance']['original_source'] == 'simulation'
    assert second['recording']['recording']['created_at_utc'] == simulated['created_at_utc']
    simulated['data']['true_offset_ns'] = 'changed after replay'
    assert second['recording']['recording']['data']['true_offset_ns'] == '100000000'


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(schema_version='2'),
    lambda d: d.update(source='live'),
    lambda d: d.update(source='unknown'),
    lambda d: d['parameters'].update(forward_delay_ns=60000000),
    lambda d: d['parameters'].update(forward_delay_ns='60 ms'),
    lambda d: d['parameters'].update(reference_unix_ns=True),
    lambda d: d['parameters'].update(units='seconds'),
    lambda d: d['data'].update(estimated_offset_ns='100000000'),
    lambda d: d['data'].update(estimation_error_ns='0'),
    lambda d: d['data']['timestamps'].update(t2_unix_ns='0'),
    lambda d: d['provenance'].update(model_version='2'),
    lambda d: d.update(created_at_utc='2026-11-15'),
    lambda d: d.update(created_at_utc='2026-11-15T00:00:00-05:00'),
])
def test_corrupted_simulation_structure_units_and_calculations_are_rejected(simulated, mutation):
    mutation(simulated)
    with pytest.raises(InvalidRecordingError):
        validate_recording(simulated)


@pytest.mark.parametrize('mutation', [
    lambda d: d['data'].update(true_offset_ns='0'),
    lambda d: d['data'].update(estimation_error_ns='0'),
    lambda d: d['data'].update(round_trip_delay_ns='78664214'),
    lambda d: d['data']['timestamps'].update(t4_unix_ns='1794735025203822001'),
    lambda d: d['data']['server_header'].update(stratum=1),
    lambda d: d['data']['server_header'].update(mode=True),
    lambda d: d['data']['raw_timestamps']['receive'].update(fraction=0),
    lambda d: d['provenance'].update(capture_time_utc='2026-11-15T00:00:00Z'),
    lambda d: d['parameters'].update(units='ms'),
    lambda d: d['data']['clock_capture'].update(t1_read_span_ns='-1'),
    lambda d: d['data']['clock_capture']['clock_info'].update(wall_resolution_ns=True),
    lambda d: d['data'].update(ignored_datagrams={}),
])
def test_corrupted_live_results_are_rejected_without_new_network_requests(mutation):
    original = scenario_recording('captured-public-ntp')['attempts'][0]['result']
    mutation(original)
    with pytest.raises(InvalidRecordingError):
        validate_recording(original)


def test_exact_originate_bytes_are_revalidated_from_saved_packets():
    document = scenario_recording('captured-public-ntp')
    result = document['attempts'][0]['result']
    raw = bytearray.fromhex(result['data']['response_packet_hex'])
    raw[31] ^= 1
    result['data']['response_packet_hex'] = raw.hex()
    with pytest.raises(InvalidRecordingError, match='originate'):
        validate_recording(document)


def test_replay_rejects_self_consistent_but_invalid_wall_monotonic_interval():
    document = scenario_recording('captured-public-ntp')
    capture = document['attempts'][0]['result']['data']['clock_capture']
    capture['t4_monotonic_ns'] = str(int(capture['t4_monotonic_ns']) + 100_000_000)
    capture['wall_monotonic_discrepancy_ns'] = str(int(capture['wall_monotonic_discrepancy_ns']) - 100_000_000)
    with pytest.raises(InvalidRecordingError, match='wall/monotonic'):
        validate_recording(document)


def test_live_export_retains_custom_clock_discontinuity_threshold(tmp_path):
    from ntp_sync_lab.core.client import MeasurementConfig, measure_once
    from ntp_sync_lab.core.polling import PollGuard
    from ntp_sync_lab.serialization import measurement_to_contract
    from tests.helpers import Delivery, FakeClock, FakeTransport, StaticResolver
    clock = FakeClock()
    config = MeasurementConfig('fixture', discontinuity_threshold_ns=20_000_000,
                               provenance_label='Injected clock-threshold fixture; not public NTP')
    result = measure_once(config, clock=clock, resolver=StaticResolver(),
                          transport=FakeTransport(clock, [[Delivery(wall_jump_ns=10_000_000)]]),
                          guard=PollGuard(clock, tmp_path))
    document = measurement_to_contract(result)
    assert document['parameters']['discontinuity_threshold_ns'] == '20000000'
    assert validate_recording(document)


@pytest.mark.parametrize('threshold', ['0', '-1', '1.5', True, None])
def test_replay_rejects_invalid_clock_discontinuity_threshold(threshold):
    document = scenario_recording('captured-public-ntp')
    document['attempts'][0]['result']['parameters']['discontinuity_threshold_ns'] = threshold
    with pytest.raises(InvalidRecordingError):
        validate_recording(document)


@pytest.mark.parametrize('mutation', [
    lambda d: d['summary'].update(median_offset_ns='0'),
    lambda d: d['summary'].update(valid_count=True),
    lambda d: d['attempts'][0].update(number=2),
    lambda d: d.update(requested_count=0),
    lambda d: d.update(requested_count=2),
    lambda d: d.update(interrupted=True),
    lambda d: d.update(stop_reason=True),
    lambda d: d.update(source='simulation'),
])
def test_bad_batch_counts_summary_and_status_are_rejected(mutation):
    document = scenario_recording('captured-public-ntp')
    mutation(document)
    with pytest.raises(InvalidRecordingError):
        validate_recording(document)


def test_sync_timeline_and_nested_measurement_are_checked_by_existing_model():
    document = sync_to_contract(run_sync(make_sync_config()), result_id='sync', created_at_utc=DATE)
    assert validate_recording(document)
    for path in ('timeline', 'measurement'):
        corrupted = copy.deepcopy(document)
        if path == 'timeline':
            corrupted['data']['timeline'][2]['virtual_client_unix_ns'] = '0'
        else:
            corrupted['data']['measurement']['data']['estimated_offset_ns'] = '0'
        with pytest.raises(InvalidRecordingError):
            validate_recording(corrupted)


@pytest.mark.parametrize('text', [
    'not json', '[]', 'null', '{"schema_version":"1","schema_version":"1"}',
    '{"schema_version":"1","value":NaN}', '{"schema_version":"1","value":Infinity}',
    '{"schema_version":"1","value":1e999}', '['*1000 + ']'*1000,
])
def test_invalid_or_nonfinite_json_is_rejected_with_domain_error(text):
    with pytest.raises(InvalidRecordingError):
        parse_recording(text)


def test_size_utf8_and_replay_depth_limits_fail_cleanly(simulated, tmp_path):
    with pytest.raises(InvalidRecordingError, match='1 MiB'):
        parse_recording(' '*(MAX_RECORDING_BYTES+1))
    path = tmp_path / 'not-utf8.json'
    path.write_bytes(b'\xff\xfe')
    with pytest.raises(InvalidRecordingError, match='UTF-8'):
        load_recording(path)
    document = simulated
    with pytest.raises(InvalidRecordingError, match='nesting'):
        for _ in range(20):
            document = make_replay(document, replayed_at_utc=DATE)
