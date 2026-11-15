import json
from fractions import Fraction

import pytest

from ntp_sync_lab.core.client import MeasurementConfig
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.errors import DnsFailureError, InvalidInputError, NtpTimeoutError
from ntp_sync_lab.experiments.measurement import run_measurements
from ntp_sync_lab.serialization import batch_to_json
from tests.helpers import Delivery, FakeClock, FakeTransport, StaticResolver, response_bytes


def run(tmp_path, scenarios, *, clock=None, count=None, **kwargs):
    clock = clock if clock is not None else FakeClock()
    transport = FakeTransport(clock, scenarios)
    batch = run_measurements(
        MeasurementConfig('fixture', provenance_label='Synthetic injected transport fixture'),
        count=len(scenarios) if count is None else count, clock=clock,
        resolver=StaticResolver(), transport=transport, guard=PollGuard(clock, tmp_path), **kwargs,
    )
    return batch, clock, transport


def test_partial_success_failure_and_summary_excludes_failed_measurements(tmp_path):
    negative = lambda req: response_bytes(req, offset_ns=-50_000_000)
    batch, clock, transport = run(tmp_path, [[Delivery()], [NtpTimeoutError('timeout')], [Delivery(data=negative)]])
    assert len(batch.successes) == 2 and len(batch.failures) == 1
    assert batch.failures[0].code == 'NTP_TIMEOUT'
    assert batch.summary.valid_count == 2
    assert batch.summary.median_offset_ns == 25_000_000
    assert batch.summary.offset_range_ns == 150_000_000
    assert batch.summary.minimum_round_trip_delay_ns == 40_000_000
    starts = [session.sent[0][1] - 1_000_000_000 for session in transport.sessions]
    assert starts == [0, 64*10**9, 192*10**9]
    assert all(session.closed and len(session.sent) == 1 for session in transport.sessions)
    payload = json.loads(batch_to_json(batch))
    assert [item['number'] for item in payload['attempts']] == [1, 2, 3]
    assert payload['attempts'][1]['result'] is None
    assert payload['attempts'][0]['result']['data']['true_offset_ns'] is None
    assert payload['attempts'][0]['result']['data']['server_header']['stratum'] == 2
    assert 'fixture' in payload['attempts'][0]['result']['provenance']['description']


def test_consecutive_timeouts_use_fake_time_for_128_256_backoff(tmp_path):
    batch, clock, transport = run(tmp_path, [[NtpTimeoutError('timeout')], [NtpTimeoutError('timeout')], [Delivery()]])
    assert len(batch.failures) == 2 and len(batch.successes) == 1
    starts = [session.sent[0][1] - 1_000_000_000 for session in transport.sessions]
    assert starts == [0, 128*10**9, 384*10**9]
    assert clock.sleeps == [125, 253]


def test_longer_requested_interval_is_respected(tmp_path):
    batch, _, transport = run(tmp_path, [[Delivery()], [Delivery()]], interval_seconds=128)
    assert len(batch.successes) == 2
    assert transport.sessions[1].sent[0][1] - transport.sessions[0].sent[0][1] == 128*10**9


def test_no_valid_measurements_means_null_summary(tmp_path):
    batch, _, _ = run(tmp_path, [[NtpTimeoutError('timeout')]])
    assert batch.summary is None
    assert json.loads(batch_to_json(batch))['summary'] is None


@pytest.mark.parametrize('direction', [-1, 1])
def test_median_of_half_nanosecond_offsets_preserves_quarter_nanosecond(tmp_path, direction):
    # First estimate is 0, second is +/-0.5ns; the exact median is +/-0.25ns.
    def zero(req):
        return response_bytes(req, offset_ns=0, processing_ns=0)[:32] + req[40:48] * 2
    def half(req):
        timestamp = int.from_bytes(req[40:48], 'big') + (4 if direction > 0 else 0)
        return response_bytes(req)[:32] + timestamp.to_bytes(8, 'big') * 2
    batch, _, _ = run(tmp_path, [[Delivery(delay_ns=0, data=zero)], [Delivery(delay_ns=1, data=half)]])
    assert batch.summary.median_offset_ns == Fraction(direction, 4)
    assert json.loads(batch_to_json(batch))['summary']['median_offset_ns'] == ('0.25' if direction > 0 else '-0.25')


def test_interrupt_during_wait_preserves_prior_attempts(tmp_path):
    clock = FakeClock()
    clock.interrupt_sleep = True
    batch, _, transport = run(tmp_path, [[Delivery()], [Delivery()]], clock=clock)
    assert batch.interrupted and batch.stop_reason == 'INTERRUPTED'
    assert len(batch.successes) == 1 and len(transport.sessions) == 1


def test_interrupt_during_receive_closes_socket_and_preserves_results(tmp_path):
    batch, _, transport = run(tmp_path, [[Delivery()], [KeyboardInterrupt()]])
    assert batch.interrupted and len(batch.successes) == 1
    assert transport.sessions[1].closed


def test_control_response_stops_batch_without_later_attempt(tmp_path):
    def control(req):
        raw = bytearray(response_bytes(req))
        raw[1] = 0
        raw[12:16] = b'DENY'
        return bytes(raw)
    batch, _, transport = run(tmp_path, [[Delivery(data=control)], [Delivery()]])
    assert batch.stop_reason == 'SERVER_CONTROL'
    assert len(batch.failures) == 1 and len(transport.sessions) == 1


def test_dns_failure_is_a_structured_attempt_without_socket(tmp_path):
    clock = FakeClock()
    transport = FakeTransport(clock)
    batch = run_measurements(MeasurementConfig('fixture'), count=3, clock=clock,
                             resolver=StaticResolver(DnsFailureError('fixture failure')),
                             transport=transport, guard=PollGuard(clock, tmp_path))
    assert batch.stop_reason == 'DNS_FAILURE' and len(batch.failures) == 1
    assert batch.requested_count == 3 and not transport.sessions


@pytest.mark.parametrize('kwargs', [{'count': 0}, {'count': 11}, {'count': True}, {'interval_seconds': 1}, {'interval_seconds': float('nan')}])
def test_invalid_batch_parameters_are_rejected_before_any_networking(kwargs):
    with pytest.raises(InvalidInputError):
        run_measurements(MeasurementConfig('fixture'), **kwargs)
