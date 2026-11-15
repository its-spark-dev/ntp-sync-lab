"""Independent wire vectors: 1970 is NTP second 0x83aa7e80; binary
fractions .25/.5/.75 are 0x40000000/0x80000000/0xc0000000. At
2036-02-07 06:28:16 UTC, NTP seconds wrap to zero (Unix 2085978496).
No expected timestamp is generated with the production codec.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from ntp_sync_lab.core.timestamps import (
    NTP_UNIX_EPOCH_NS,
    NTP_UNIX_EPOCH_SECONDS,
    NtpTimestamp,
    decode_timestamp,
    encode_timestamp,
    unfold_timestamp,
)
from ntp_sync_lab.errors import InvalidInputError

ROLLOVER_NS = 2_085_978_496_000_000_000


@pytest.mark.parametrize(
    "unix_ns, wire_hex",
    [
        (-2_208_988_800_000_000_000, "0000000000000000"),
        (-500_000_000, "83aa7e7f80000000"),
        (-1, "83aa7e7ffffffffc"),
        (0, "83aa7e8000000000"),
        (1, "83aa7e8000000004"),
        (250_000_000, "83aa7e8040000000"),
        (500_000_000, "83aa7e8080000000"),
        (750_000_000, "83aa7e80c0000000"),
        (999_999_999, "83aa7e80fffffffc"),
        (1_000_000_000, "83aa7e8100000000"),
        (946_684_800_000_000_000, "bc17c20000000000"),
        (ROLLOVER_NS - 500_000_000, "ffffffff80000000"),
        (ROLLOVER_NS - 1, "fffffffffffffffc"),
        (ROLLOVER_NS, "0000000000000000"),
        (ROLLOVER_NS + 1, "0000000000000004"),
        (ROLLOVER_NS + 500_000_000, "0000000080000000"),
    ],
)
def test_independently_known_wire_vectors(unix_ns, wire_hex):
    raw = NtpTimestamp.from_bytes(bytes.fromhex(wire_hex))
    assert encode_timestamp(unix_ns) == raw
    assert encode_timestamp(unix_ns).to_bytes().hex() == wire_hex
    assert decode_timestamp(raw, era_reference_ns=unix_ns) == unix_ns


def test_epoch_and_rollover_calendar_relationships():
    # datetime subtraction yields an integer day/second count, never a float epoch.
    ntp = datetime(1900, 1, 1, tzinfo=timezone.utc)
    unix = datetime(1970, 1, 1, tzinfo=timezone.utc)
    difference = unix - ntp
    assert difference.days * 86400 + difference.seconds == NTP_UNIX_EPOCH_SECONDS
    assert NTP_UNIX_EPOCH_NS == 2_208_988_800_000_000_000
    assert unix + timedelta(seconds=2_085_978_496) == datetime(
        2036, 2, 7, 6, 28, 16, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    "fraction, expected_ns",
    [
        (1, 0),           # 0.233 ns rounds down, but raw timestamp is nonzero.
        (2, 0),           # 0.466 ns.
        (3, 1),           # 0.698 ns.
        (4, 1),
        (0x00400000, 976_562),   # Exactly 976562.5 ns: even lower integer.
        (0x00C00000, 2_929_688), # Exactly 2929687.5 ns: even upper integer.
        (0xFFFFFFFF, 1_000_000_000), # Carry into next second after decoding.
    ],
)
def test_decode_quantization_uses_nearest_ties_to_even(fraction, expected_ns):
    assert decode_timestamp(NtpTimestamp(0x83AA7E80, fraction), 0) == expected_ns


def test_decode_rounding_carries_across_era_boundary():
    raw = NtpTimestamp(0xFFFFFFFF, 0xFFFFFFFF)
    assert decode_timestamp(raw, ROLLOVER_NS) == ROLLOVER_NS
    assert raw.to_bytes() == b"\xff" * 8


@pytest.mark.parametrize(
    "fraction, expected_ns", [(0xFFC00000, -976_562), (0xFF400000, -2_929_688)]
)
def test_negative_unix_dates_use_the_same_ties_to_even_rule(fraction, expected_ns):
    assert decode_timestamp(NtpTimestamp(0x83AA7E7F, fraction), 0) == expected_ns


@pytest.mark.parametrize("reference", [ROLLOVER_NS - 1_000_000_000, ROLLOVER_NS + 1_000_000_000])
def test_same_nearby_reference_decodes_both_sides_of_rollover(reference):
    assert decode_timestamp(NtpTimestamp(0xFFFFFFFF, 0x80000000), reference) == (
        ROLLOVER_NS - 500_000_000
    )
    assert decode_timestamp(NtpTimestamp(0, 0x80000000), reference) == (
        ROLLOVER_NS + 500_000_000
    )


@pytest.mark.parametrize("direction", [-1, 1])
def test_exact_half_era_reference_is_rejected(direction):
    # Unix epoch's raw timestamp repeats every 2**32 seconds.
    with pytest.raises(InvalidInputError, match="equidistant"):
        decode_timestamp(NtpTimestamp(0x83AA7E80, 0), direction * (2**31) * 10**9)


def test_nearby_reference_assumption_has_an_explicit_limit():
    raw = NtpTimestamp(0x83AA7E80, 0)
    half = (2**31) * 10**9
    assert decode_timestamp(raw, half - 1) == 0
    assert decode_timestamp(raw, half + 1) == (2**32) * 10**9
    # Wrong-era local dates cannot be detected from the 64-bit timestamp alone.
    assert decode_timestamp(raw, (2**32) * 10**9) == (2**32) * 10**9


@pytest.mark.parametrize("unix_ns", [-(2**100), 2**100, 1_794_693_600_123_456_789])
def test_integer_nanosecond_round_trip_in_negative_and_large_eras(unix_ns):
    assert decode_timestamp(encode_timestamp(unix_ns), unix_ns) == unix_ns


def test_raw_ticks_preserve_order_hidden_by_nanosecond_rounding():
    earlier = NtpTimestamp(0x83AA7E80, 0)
    later = NtpTimestamp(0x83AA7E80, 1)
    assert decode_timestamp(earlier, 0) == decode_timestamp(later, 0) == 0
    assert unfold_timestamp(later, 0) - unfold_timestamp(earlier, 0) == 1
    assert later.to_bytes() != earlier.to_bytes()


@pytest.mark.parametrize("words", [(-1, 0), (2**32, 0), (0, -1), (0, 2**32), (True, 0), (0, 0.0)])
def test_invalid_raw_words(words):
    with pytest.raises(InvalidInputError):
        NtpTimestamp(*words)


@pytest.mark.parametrize("raw", [b"", bytes(7), bytes(9), bytearray(8), "00000000"])
def test_invalid_timestamp_bytes(raw):
    with pytest.raises(InvalidInputError):
        NtpTimestamp.from_bytes(raw)


@pytest.mark.parametrize("value", [True, 1.0, "1", None, float("nan"), float("inf")])
def test_codec_rejects_noninteger_dates(value):
    with pytest.raises(InvalidInputError):
        encode_timestamp(value)
    with pytest.raises(InvalidInputError):
        decode_timestamp(NtpTimestamp(1, 0), value)


def test_decode_requires_raw_timestamp_model():
    with pytest.raises(InvalidInputError):
        decode_timestamp((1, 0), 0)


def test_raw_words_are_immutable():
    with pytest.raises(FrozenInstanceError):
        NtpTimestamp(1, 2).fraction = 3
