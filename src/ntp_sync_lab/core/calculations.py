"""Authoritative, exact four-timestamp calculation; no I/O or clock reads."""

from fractions import Fraction

from ntp_sync_lab.errors import InvalidInputError, InvalidTimingError
from ntp_sync_lab.models import ExchangeMetrics, TimestampQuad


def calculate_exchange(timestamps: TimestampQuad) -> ExchangeMetrics:
    """Estimate server-minus-client offset and network round-trip delay.

    offset = ((T2 - T1) + (T3 - T4)) / 2
    delay  = (T4 - T1) - (T3 - T2)

    The input is already decoded integer Unix nanoseconds. Subtraction happens
    before division, preserving precision for large epochs. Only within-clock
    intervals are checked. Negative delay is rejected rather than clamped.
    Equal clock rates and stable offsets during the exchange are assumed;
    symmetric one-way delays are needed for an unbiased offset estimate.
    """
    if not isinstance(timestamps, TimestampQuad):
        raise InvalidInputError("timestamps must be a TimestampQuad")

    t1 = timestamps.t1_unix_ns
    t2 = timestamps.t2_unix_ns
    t3 = timestamps.t3_unix_ns
    t4 = timestamps.t4_unix_ns
    elapsed = t4 - t1
    processing = t3 - t2
    if elapsed < 0:
        raise InvalidTimingError("client reception T4 precedes client transmission T1")
    if processing < 0:
        raise InvalidTimingError("server transmission T3 precedes server reception T2")
    delay = elapsed - processing
    if delay < 0:
        raise InvalidTimingError("server processing exceeds client elapsed time; delay is negative")

    return ExchangeMetrics(
        estimated_offset_ns=Fraction((t2 - t1) + (t3 - t4), 2),
        round_trip_delay_ns=delay,
        client_elapsed_ns=elapsed,
        server_processing_ns=processing,
    )
