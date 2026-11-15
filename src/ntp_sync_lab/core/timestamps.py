"""Integer NTP timestamp codec with explicit era inference.

The wire has unsigned seconds/fraction words (32 bits each), but no era number.
Decoding chooses the instant nearest era_reference_ns, which must be strictly
less than 2**31 seconds (about 68 years) from the actual timestamp. A reference
at exactly the midpoint is ambiguous and is rejected; an incorrect reference
can otherwise select a wrong era without detection. No current clock is read.

Both conversion directions round to nearest, ties to even, using integers.
One wire tick is 2**-32 seconds (about 0.233 ns). Decoding rounds to integer
nanoseconds (at most 0.5 ns error); encoding then decoding an integer-nanosecond
input recovers it exactly given the correct era. Nanosecond representation says
nothing about measurement accuracy. Raw words/bytes remain available for exact
originate matching and sub-nanosecond protocol timing checks.

All-zero words can be decoded mathematically (e.g. the 2036 era boundary), but
are reserved as an unspecified timestamp in packets. Packet validation, rather
than this codec, handles that sentinel.
"""

import struct
from dataclasses import dataclass

from ntp_sync_lab.errors import InvalidInputError

NS_PER_SECOND = 1_000_000_000
NTP_UNIX_EPOCH_SECONDS = 2_208_988_800
NTP_UNIX_EPOCH_NS = NTP_UNIX_EPOCH_SECONDS * NS_PER_SECOND
FRACTION_SCALE = 1 << 32
ERA_SECONDS = 1 << 32
ERA_TICKS = 1 << 64
_WORDS = struct.Struct("!II")


def _round_ratio(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    if 2 * remainder > denominator or (2 * remainder == denominator and quotient % 2):
        return quotient + 1
    return quotient


@dataclass(frozen=True, slots=True)
class NtpTimestamp:
    """Raw unsigned NTP words, without an inferred era."""

    seconds: int
    fraction: int

    def __post_init__(self) -> None:
        for name in ("seconds", "fraction"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value < FRACTION_SCALE:
                raise InvalidInputError(f"{name} must be an unsigned 32-bit integer")

    @property
    def is_zero(self) -> bool:
        return self.seconds == 0 and self.fraction == 0

    def to_bytes(self) -> bytes:
        return _WORDS.pack(self.seconds, self.fraction)

    @classmethod
    def from_bytes(cls, data: bytes) -> "NtpTimestamp":
        if not isinstance(data, bytes) or len(data) != _WORDS.size:
            raise InvalidInputError("a raw NTP timestamp must be exactly 8 bytes")
        return cls(*_WORDS.unpack(data))


def encode_timestamp(unix_ns: int) -> NtpTimestamp:
    """Encode an integer Unix nanosecond date, wrapping seconds modulo 2**32."""
    if type(unix_ns) is not int:
        raise InvalidInputError("unix_ns must be an integer number of nanoseconds")
    ticks = _round_ratio((unix_ns + NTP_UNIX_EPOCH_NS) * FRACTION_SCALE, NS_PER_SECOND)
    seconds, fraction = divmod(ticks, FRACTION_SCALE)
    return NtpTimestamp(seconds % ERA_SECONDS, fraction)


def unfold_timestamp(timestamp: NtpTimestamp, era_reference_ns: int) -> int:
    """Return extended ticks since 1900, selecting the nearest era exactly.

    The returned integer can be negative and can exceed 64 bits. This helper
    permits timing checks before nanosecond rounding; it is not a UTC date.
    """
    if not isinstance(timestamp, NtpTimestamp):
        raise InvalidInputError("timestamp must be an NtpTimestamp")
    if type(era_reference_ns) is not int:
        raise InvalidInputError("era_reference_ns must be integer Unix nanoseconds")
    raw_ticks = timestamp.seconds * FRACTION_SCALE + timestamp.fraction
    # Scale reference and raw time to common integer units without rounding.
    distance = (era_reference_ns + NTP_UNIX_EPOCH_NS) * FRACTION_SCALE
    distance -= raw_ticks * NS_PER_SECOND
    period = ERA_TICKS * NS_PER_SECOND
    era, remainder = divmod(distance, period)
    if 2 * remainder == period:
        raise InvalidInputError("era reference is equidistant between two NTP eras")
    if 2 * remainder > period:
        era += 1
    return raw_ticks + era * ERA_TICKS


def decode_timestamp(timestamp: NtpTimestamp, era_reference_ns: int) -> int:
    """Decode to integer Unix nanoseconds using a required nearby-date reference."""
    ticks = unfold_timestamp(timestamp, era_reference_ns)
    return _round_ratio(ticks * NS_PER_SECOND, FRACTION_SCALE) - NTP_UNIX_EPOCH_NS
