from fractions import Fraction

import pytest

import ntp_sync_lab.core.client as client_module
from ntp_sync_lab.core.client import MeasurementConfig, measure_once
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.errors import (
    DnsFailureError, InvalidInputError, LocalClockDiscontinuityError, MalformedPacketError,
    NetworkError, NtpTimeoutError, RateLimitedError, ServerControlError, UnsupportedResponseError,
)
from tests.helpers import Delivery, FakeClock, FakeTransport, StaticResolver, TARGET, response_bytes


def execute(tmp_path, events=None, clock=None, transport=None):
    clock = clock if clock is not None else FakeClock()
    transport = transport if transport is not None else FakeTransport(clock, [events or [Delivery()]])
    result = measure_once(
        MeasurementConfig("fixture", provenance_label="Injected deterministic test fixture"),
        clock=clock, resolver=StaticResolver(), transport=transport, guard=PollGuard(clock, tmp_path),
    )
    return result, clock, transport


def test_actual_four_timestamp_ownership_and_calculation_with_injected_transport(tmp_path):
    result, clock, transport = execute(tmp_path)
    assert result.response.timestamps.t1_unix_ns == 0
    assert result.response.timestamps.t2_unix_ns == 120_000_000
    assert result.response.timestamps.t3_unix_ns == 125_000_000
    assert result.response.timestamps.t4_unix_ns == 45_000_000
    assert result.response.metrics.estimated_offset_ns == Fraction(100_000_000)
    assert result.response.metrics.round_trip_delay_ns == 40_000_000
    assert result.response.metrics.server_processing_ns == 5_000_000
    assert result.exchange.true_offset_ns is None
    assert transport.sessions[0].closed
    assert len(transport.sessions[0].sent) == 1
    assert "fixture" in result.exchange.provenance


def test_t4_is_captured_before_parse_and_expensive_processing(tmp_path, monkeypatch):
    clock = FakeClock()
    original = client_module.parse_packet
    def expensive_parse(data):
        received_index = clock.events.index("received")
        assert clock.events[received_index + 1:received_index + 4] == ["mono", "wall", "mono"]
        clock.advance(1_000_000_000)
        return original(data)
    monkeypatch.setattr(client_module, "parse_packet", expensive_parse)
    result, _, _ = execute(tmp_path, clock=clock)
    assert result.received.wall_ns == 45_000_000
    assert result.response.metrics.round_trip_delay_ns == 40_000_000


def test_wrong_peer_and_originate_do_not_reset_deadline_or_trigger_resend(tmp_path):
    def wrong_origin(request):
        data = response_bytes(request)
        return data[:24] + bytes(8) + data[32:]
    result, _, transport = execute(tmp_path, [
        Delivery(delay_ns=1_000_000, address=("192.0.2.2", 123), data=b"irrelevant"),
        Delivery(delay_ns=1_000_000, data=wrong_origin), Delivery(delay_ns=43_000_000),
    ])
    assert result.ignored_count == 2
    assert [item.reason for item in result.ignored_datagrams] == ["PEER_MISMATCH", "ORIGIN_MISMATCH"]
    session = transport.sessions[0]
    assert session.timeouts == pytest.approx([3, 2.999, 2.998])
    assert len(session.sent) == 1


def test_mismatch_only_timeout_is_bounded_and_diagnostic(tmp_path):
    clock = FakeClock()
    transport = FakeTransport(clock, [[Delivery(delay_ns=1_000_000_000, address=("192.0.2.2", 123))]])
    with pytest.raises(NtpTimeoutError) as error:
        execute(tmp_path, clock=clock, transport=transport)
    assert clock.mono == 4_000_000_000
    assert error.value.details["ignored_count"] == 1
    assert error.value.details["ignored_codes"] == ("PEER_MISMATCH",)
    assert len(transport.sessions[0].sent) == 1 and transport.sessions[0].closed


def test_ignored_datagram_diagnostics_are_memory_bounded(tmp_path):
    events = [Delivery(delay_ns=1_000_000, address=('192.0.2.2', 123)) for _ in range(26)]
    result, _, _ = execute(tmp_path, events + [Delivery(delay_ns=19_000_000)])
    assert result.ignored_count == 26 and len(result.ignored_datagrams) == 20


def test_late_datagram_is_not_accepted_as_timely(tmp_path):
    with pytest.raises(NtpTimeoutError, match="original"):
        execute(tmp_path, [Delivery(delay_ns=3_001_000_000)])


@pytest.mark.parametrize("jump", [-100_000_000, 100_000_000])
def test_local_wall_steps_are_reported_even_if_quartet_becomes_invalid(tmp_path, jump):
    with pytest.raises(LocalClockDiscontinuityError) as error:
        execute(tmp_path, [Delivery(wall_jump_ns=jump)])
    assert error.value.details["wall_monotonic_discrepancy_ns"] == jump


@pytest.mark.parametrize(
    "data, error_class", [(b"short", MalformedPacketError),
                          (lambda req: response_bytes(req) + bytes(4), UnsupportedResponseError)],
)
def test_invalid_responses_remain_protocol_errors_with_raw_context(tmp_path, data, error_class):
    with pytest.raises(error_class) as error:
        execute(tmp_path, [Delivery(data=data)])
    assert error.value.details["target_address"] == "192.0.2.1"
    assert error.value.details["response_hex"]


def test_kiss_of_death_stops_and_persists_control(tmp_path):
    def control(request):
        packet = bytearray(response_bytes(request))
        packet[0:2] = b"\xe4\x00"
        packet[12:16] = b"RATE"
        packet[32:48] = bytes(16)
        return bytes(packet)
    with pytest.raises(ServerControlError):
        execute(tmp_path, [Delivery(data=control)])
    clock = FakeClock()
    with pytest.raises(ServerControlError):
        PollGuard(clock, tmp_path).reserve(TARGET.peer)


def test_dns_error_never_opens_socket_or_creates_poll_reservation(tmp_path):
    clock = FakeClock()
    transport = FakeTransport(clock)
    with pytest.raises(DnsFailureError):
        measure_once(MeasurementConfig("fixture"), clock=clock, transport=transport,
                     resolver=StaticResolver(DnsFailureError("fixture DNS failure")),
                     guard=PollGuard(clock, tmp_path))
    assert not transport.sessions and not list(tmp_path.iterdir())


def test_network_failure_is_distinct_and_does_not_retry(tmp_path):
    clock = FakeClock()
    transport = FakeTransport(clock, [[NetworkError("fixture receive failure")]])
    with pytest.raises(NetworkError):
        execute(tmp_path, clock=clock, transport=transport)
    assert transport.sessions[0].closed and len(transport.sessions[0].sent) == 1


def test_cooldown_prevents_second_transmission_and_closes_unused_socket(tmp_path):
    clock = FakeClock()
    transport = FakeTransport(clock, [[Delivery()], [Delivery()]])
    execute(tmp_path, clock=clock, transport=transport)
    with pytest.raises(RateLimitedError):
        execute(tmp_path, clock=clock, transport=transport)
    assert len(transport.sessions[0].sent) == 1
    assert not transport.sessions[1].sent and transport.sessions[1].closed


@pytest.mark.parametrize("timeout", [True, 0, 0.01, 11, float('nan'), float('inf'), "3"])
def test_invalid_timeout_is_rejected_before_networking(timeout):
    with pytest.raises(InvalidInputError):
        MeasurementConfig("fixture", timeout_seconds=timeout)
