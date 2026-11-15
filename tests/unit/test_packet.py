"""Constructed base-header bytes, independent of the production packet encoder.

At Unix 0, the request transmit words are (0x83aa7e80, 0). The normal reply
receives at .125 s (fraction 0x20000000), transmits at .1875 s (0x30000000),
and the client receives at .3125 s. Thus processing is .0625 s, network delay
is .3125-.0625=.25 s, and offset is (.125 + .1875-.3125)/2 = 0.
"""

import json
import struct
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from fractions import Fraction

import pytest

from ntp_sync_lab.core.calculations import calculate_exchange
from ntp_sync_lab.core.packet import (
    ClientRequest,
    NtpPeer,
    build_request,
    parse_packet,
    validate_response,
)
from ntp_sync_lab.core.timestamps import NtpTimestamp, decode_timestamp
from ntp_sync_lab.errors import (
    InvalidInputError,
    InvalidTimingError,
    MalformedPacketError,
    OriginMismatchError,
    PeerMismatchError,
    ServerControlError,
    ServerUnsynchronizedError,
    UnsupportedResponseError,
)
from ntp_sync_lab.models import ExchangeResult, Experiment, ResultSource, TimestampQuad
from ntp_sync_lab.serialization import to_json

PEER = NtpPeer("192.0.2.1", 123)
RESPONSE = bytes.fromhex(
    "240206fa ffff8000 00004000 47505300 "
    "83aa7e7f00000000 83aa7e8000000000 "
    "83aa7e8020000000 83aa7e8030000000"
)


def _change(data, offset, value):
    result = bytearray(data)
    result[offset:offset + len(value)] = value
    return bytes(result)


def _validate(data=RESPONSE, *, request=None, actual_peer=PEER, t4=312_500_000):
    return validate_response(
        parse_packet(data),
        build_request(0) if request is None else request,
        expected_peer=PEER,
        actual_peer=actual_peer,
        t4_unix_ns=t4,
    )


def test_request_bytes_are_a_valid_v4_mode_3_base_packet():
    expected = bytes.fromhex(
        "23000600 00000000 00000000 00000000 "
        "0000000000000000 0000000000000000 "
        "0000000000000000 83aa7e8000000000"
    )
    request = build_request(0)
    assert request.packet == expected
    assert len(request.packet) == 48
    assert request.transmit_bytes == bytes.fromhex("83aa7e8000000000")
    assert request.transmit_timestamp == NtpTimestamp(0x83AA7E80, 0)
    assert request.sampled_t1_unix_ns == request.t1_unix_ns == 0
    packet = parse_packet(request.packet)
    assert (packet.version, packet.mode, packet.leap_indicator) == (4, 3, 0)
    assert (packet.poll_exponent, packet.precision_exponent) == (6, 0)


def test_request_transmit_fraction_and_original_sample_are_preserved():
    request = build_request(1)
    assert request.transmit_bytes.hex() == "83aa7e8000000004"
    assert request.sampled_t1_unix_ns == request.t1_unix_ns == 1


@pytest.mark.parametrize("unix_ns", [-2_208_988_800_000_000_000, 2_085_978_496_000_000_000])
def test_request_rejects_reserved_all_zero_transmit_timestamp(unix_ns):
    with pytest.raises(InvalidInputError, match="reserved zero"):
        build_request(unix_ns)


def test_request_context_cannot_disagree_with_sent_timestamp():
    with pytest.raises(InvalidInputError, match="matching T1"):
        ClientRequest(build_request(0).packet, sampled_t1_unix_ns=1)
    with pytest.raises(FrozenInstanceError):
        build_request(0).packet = bytes(48)


def test_parse_decodes_raw_header_fields_with_correct_signedness():
    packet = parse_packet(RESPONSE)
    assert packet.raw == RESPONSE
    assert (packet.version, packet.mode, packet.leap_indicator, packet.stratum) == (4, 4, 0, 2)
    assert packet.poll_exponent == 6
    assert packet.precision_exponent == -6
    assert packet.root_delay_raw == -32768
    assert packet.root_dispersion_raw == 16384
    assert packet.root_delay_ns == Fraction(-500_000_000)
    assert packet.root_dispersion_ns == Fraction(250_000_000)
    assert packet.reference_id == b"GPS\x00"
    assert packet.reference_timestamp == NtpTimestamp(0x83AA7E7F, 0)
    assert packet.originate_timestamp == NtpTimestamp(0x83AA7E80, 0)
    assert packet.receive_timestamp == NtpTimestamp(0x83AA7E80, 0x20000000)
    assert packet.transmit_timestamp == NtpTimestamp(0x83AA7E80, 0x30000000)
    with pytest.raises(FrozenInstanceError):
        packet.stratum = 0


def test_fixed_point_metadata_is_exact_at_its_smallest_bit():
    packet = parse_packet(_change(RESPONSE, 4, struct.pack("!iI", -1, 0xFFFFFFFF)))
    assert packet.root_delay_ns == Fraction(-1_000_000_000, 65536)
    assert packet.root_dispersion_ns == Fraction(0xFFFFFFFF * 1_000_000_000, 65536)
    assert parse_packet(_change(RESPONSE, 2, b"\xff\x80")).poll_exponent == -1
    assert parse_packet(_change(RESPONSE, 2, b"\xff\x80")).precision_exponent == -128


def test_valid_response_integrates_with_existing_calculation_and_json():
    validated = _validate()
    expected = TimestampQuad(0, 125_000_000, 187_500_000, 312_500_000)
    assert validated.timestamps == expected
    assert validated.metrics == calculate_exchange(expected)
    assert validated.metrics.estimated_offset_ns == Fraction(0)
    assert validated.metrics.round_trip_delay_ns == 250_000_000
    assert validated.metrics.server_processing_ns == 62_500_000
    assert validated.peer == PEER
    result = ExchangeResult(
        timestamps=validated.timestamps,
        experiment=Experiment.REAL_EXCHANGE,
        source=ResultSource.LIVE,
        result_id="constructed-packet-fixture",
        created_at_utc=datetime(2026, 11, 15, tzinfo=timezone.utc),
        provenance="Constructed bytes only; no actual live request",
    )
    data = json.loads(to_json(result))["data"]
    assert data["estimated_offset_ns"] == "0"
    assert data["true_offset_ns"] is None
    assert data["estimation_error_ns"] is None


@pytest.mark.parametrize("length", [0, 1, 7, 40, 47])
def test_short_packets_are_malformed(length):
    with pytest.raises(MalformedPacketError) as error:
        parse_packet(RESPONSE[:length])
    assert error.value.code == "MALFORMED_PACKET"
    assert error.value.details["packet_length"] == length


@pytest.mark.parametrize("length", [49, 52, 68, 96])
def test_trailers_are_unsupported_without_claiming_their_contents(length):
    with pytest.raises(UnsupportedResponseError, match="not interpreted") as error:
        parse_packet(RESPONSE + bytes(length - 48))
    assert error.value.code == "UNSUPPORTED_RESPONSE"
    assert error.value.details == {"packet_length": length, "version": 4, "mode": 4}


@pytest.mark.parametrize("value", [bytearray(RESPONSE), memoryview(RESPONSE), None, "packet"])
def test_parse_requires_immutable_bytes(value):
    with pytest.raises(InvalidInputError):
        parse_packet(value)


@pytest.mark.parametrize("version", [0, 1, 2, 3, 5, 6, 7])
def test_unsupported_versions_are_distinct_from_malformed(version):
    raw = _change(RESPONSE, 0, bytes(((version << 3) | 4,)))
    assert parse_packet(raw).version == version  # Parsing is not response acceptance.
    with pytest.raises(UnsupportedResponseError) as error:
        _validate(raw)
    assert error.value.details["version"] == version


@pytest.mark.parametrize("mode", [0, 1, 2, 3, 5, 6, 7])
def test_nonserver_modes_are_unsupported(mode):
    with pytest.raises(UnsupportedResponseError) as error:
        _validate(_change(RESPONSE, 0, bytes((0x20 | mode,))))
    assert error.value.details["mode"] == mode


def test_originate_match_is_byte_exact_even_when_decoded_nanoseconds_match():
    origin = NtpTimestamp(0x83AA7E80, 1)
    assert decode_timestamp(origin, 0) == build_request(0).t1_unix_ns == 0
    with pytest.raises(OriginMismatchError) as error:
        _validate(_change(RESPONSE, 24, origin.to_bytes()))
    assert error.value.code == "ORIGIN_MISMATCH"
    assert error.value.details["actual_hex"] == "83aa7e8000000001"


@pytest.mark.parametrize("offset", [32, 40])
def test_required_server_timestamps_cannot_be_unspecified(offset):
    with pytest.raises(MalformedPacketError, match="unspecified"):
        _validate(_change(RESPONSE, offset, bytes(8)))


def test_zero_reference_timestamp_is_not_confused_with_required_t2_t3():
    assert _validate(_change(RESPONSE, 16, bytes(8))).metrics.estimated_offset_ns == 0


@pytest.mark.parametrize("indicator", [0, 1, 2])
def test_usable_leap_status_is_preserved(indicator):
    reply = _validate(_change(RESPONSE, 0, bytes(((indicator << 6) | 0x24,))))
    assert reply.packet.leap_indicator == indicator


def test_unsynchronized_leap_indicator_is_rejected():
    with pytest.raises(ServerUnsynchronizedError) as error:
        _validate(_change(RESPONSE, 0, b"\xe4"))
    assert error.value.code == "SERVER_UNSYNCHRONIZED"
    assert error.value.details["leap_indicator"] == 3


@pytest.mark.parametrize("stratum", [1, 15])
def test_synchronized_stratum_boundaries(stratum):
    assert _validate(_change(RESPONSE, 1, bytes((stratum,)))).packet.stratum == stratum


def test_stratum_16_is_unsynchronized():
    with pytest.raises(ServerUnsynchronizedError):
        _validate(_change(RESPONSE, 1, b"\x10"))


@pytest.mark.parametrize("stratum", [17, 255])
def test_reserved_strata_are_invalid(stratum):
    with pytest.raises(MalformedPacketError, match="stratum"):
        _validate(_change(RESPONSE, 1, bytes((stratum,))))


def test_reserved_stratum_is_still_malformed_when_li_is_unsynchronized():
    with pytest.raises(MalformedPacketError):
        _validate(_change(RESPONSE, 0, b"\xe4\xff"))


@pytest.mark.parametrize(
    "reference_id, kiss_code",
    [(b"RATE", "RATE"), (b"DENY", "DENY"), (b"RSTR", "RSTR"),
     (b"INIT", "INIT"), (b"STEP", "STEP"), (b"XXXX", "XXXX"),
     (b"\xff\x00\x00\x00", None), (bytes(4), None)],
)
def test_control_replies_stop_before_unusable_time_and_leap_checks(reference_id, kiss_code):
    raw = _change(RESPONSE, 0, b"\xe4\x00")  # LI=3, stratum=0.
    raw = _change(raw, 12, reference_id)
    raw = _change(raw, 32, bytes(16))
    with pytest.raises(ServerControlError) as error:
        _validate(raw)
    assert error.value.code == "SERVER_CONTROL"
    assert error.value.stop_polling is True
    assert error.value.reference_id == reference_id
    assert error.value.kiss_code == kiss_code
    assert error.value.details["reference_id_hex"] == reference_id.hex()


@pytest.mark.parametrize("peer", [NtpPeer("192.0.2.2", 123), NtpPeer("192.0.2.1", 124)])
def test_unexpected_peer_is_rejected_before_control_handling(peer):
    raw = _change(RESPONSE, 1, b"\x00")
    with pytest.raises(PeerMismatchError) as error:
        _validate(raw, actual_peer=peer)
    assert error.value.code == "PEER_MISMATCH"


def test_originate_is_checked_before_control_handling():
    raw = _change(RESPONSE, 1, b"\x00")
    raw = _change(raw, 24, bytes(8))
    with pytest.raises(OriginMismatchError):
        _validate(raw)


@pytest.mark.parametrize(
    "raw, t4, message",
    [
        (_change(RESPONSE, 40, bytes.fromhex("83aa7e8010000000")), 312_500_000, "server transmission"),
        (RESPONSE, -1, "client reception"),
        (RESPONSE, 1, "delay is negative"),
    ],
)
def test_invalid_within_clock_intervals_and_delay(raw, t4, message):
    with pytest.raises(InvalidTimingError, match=message):
        _validate(raw, t4=t4)


def test_subnanosecond_server_timestamp_reversal_is_not_hidden_by_rounding():
    raw = _change(RESPONSE, 32, bytes.fromhex("83aa7e8020000001"))
    raw = _change(raw, 40, bytes.fromhex("83aa7e8020000000"))
    assert decode_timestamp(parse_packet(raw).receive_timestamp, 0) == 125_000_000
    assert decode_timestamp(parse_packet(raw).transmit_timestamp, 0) == 125_000_000
    with pytest.raises(InvalidTimingError, match="server transmission"):
        _validate(raw)


@pytest.mark.parametrize("server_offset_seconds", [-86400, 86400])
def test_large_offset_does_not_trigger_cross_clock_ordering_rejection(server_offset_seconds):
    # Known seconds words plus exact binary fractions; no production timestamp codec.
    seconds = 2_208_988_800 + server_offset_seconds
    raw = _change(RESPONSE, 32, struct.pack("!II", seconds, 0x20000000))
    raw = _change(raw, 40, struct.pack("!II", seconds, 0x30000000))
    reply = _validate(raw)
    assert reply.metrics.estimated_offset_ns == server_offset_seconds * 10**9
    assert reply.metrics.round_trip_delay_ns == 250_000_000


@pytest.mark.parametrize("fraction, offset", [(0, Fraction(-1, 2)), (4, Fraction(1, 2))])
def test_wire_response_preserves_half_nanosecond_offset_in_existing_core(fraction, offset):
    raw = _change(RESPONSE, 32, struct.pack("!II", 0x83AA7E80, fraction) * 2)
    reply = _validate(raw, t4=1)
    assert reply.metrics.estimated_offset_ns == offset
    assert reply.metrics.round_trip_delay_ns == 1


def test_server_processing_and_client_exchange_cross_2036_rollover():
    rollover = 2_085_978_496_000_000_000
    request = build_request(rollover - 250_000_000)
    assert request.transmit_bytes.hex() == "ffffffffc0000000"
    raw = _change(RESPONSE, 24, bytes.fromhex("ffffffffc0000000"))
    raw = _change(raw, 32, bytes.fromhex("ffffffffe0000000"))
    raw = _change(raw, 40, bytes.fromhex("0000000020000000"))
    reply = _validate(raw, request=request, t4=rollover + 250_000_000)
    assert reply.timestamps == TimestampQuad(
        rollover - 250_000_000, rollover - 125_000_000,
        rollover + 125_000_000, rollover + 250_000_000,
    )
    assert reply.metrics.estimated_offset_ns == 0
    assert reply.metrics.server_processing_ns == reply.metrics.round_trip_delay_ns == 250_000_000


def test_nonzero_server_fraction_at_era_boundary_is_not_unspecified():
    rollover = 2_085_978_496_000_000_000
    request = build_request(rollover - 250_000_000)
    raw = _change(RESPONSE, 24, bytes.fromhex("ffffffffc0000000"))
    raw = _change(raw, 32, bytes.fromhex("0000000000000001 0000000000000002"))
    reply = _validate(raw, request=request, t4=rollover + 250_000_000)
    assert reply.timestamps.t2_unix_ns == reply.timestamps.t3_unix_ns == rollover
    assert reply.metrics.estimated_offset_ns == 0


@pytest.mark.parametrize("t4", [True, 1.0, float("nan"), None])
def test_t4_requires_exact_integer_nanoseconds(t4):
    with pytest.raises(InvalidInputError):
        _validate(t4=t4)


def test_ipv6_peer_normalization_and_scope_identity():
    expected = NtpPeer("2001:0db8:0000:0000:0000:0000:0000:0001", 123)
    assert expected == NtpPeer("2001:db8::1", 123)
    reply = validate_response(
        parse_packet(RESPONSE), build_request(0), expected_peer=expected,
        actual_peer=NtpPeer("2001:db8::1", 123), t4_unix_ns=312_500_000,
    )
    assert reply.peer == expected
    with pytest.raises(PeerMismatchError):
        validate_response(
            parse_packet(RESPONSE), build_request(0),
            expected_peer=NtpPeer("fe80::1", 123, 2),
            actual_peer=NtpPeer("fe80::1", 123, 3), t4_unix_ns=312_500_000,
        )


@pytest.mark.parametrize(
    "args",
    [("pool.ntp.org", 123), ("192.0.2.1", True), ("192.0.2.1", 0),
     ("192.0.2.1", 65536), ("192.0.2.1", 123, 1), ("fe80::1%en0", 123),
     ("fe80::1", 123, -1)],
)
def test_peer_model_rejects_hostnames_and_invalid_identifiers(args):
    with pytest.raises(InvalidInputError):
        NtpPeer(*args)


def test_validation_requires_parsed_models_and_peer_objects():
    with pytest.raises(InvalidInputError):
        validate_response(RESPONSE, build_request(0), expected_peer=PEER, actual_peer=PEER, t4_unix_ns=0)
    with pytest.raises(InvalidInputError):
        validate_response(parse_packet(RESPONSE), build_request(0), expected_peer=PEER,
                          actual_peer=("192.0.2.1", 123), t4_unix_ns=0)
