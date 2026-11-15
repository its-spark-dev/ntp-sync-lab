"""Expected values below are hand-derived, not produced by a simulator.

Use a reference departure instant of 0 ms and 5 ms server processing:
- A client 100 ms behind sends at -100. With 20/20 ms transit, the server
  receives at 20 and sends at 25; the client receives at 45-100 = -55.
  Differences are +120 and +80: offset +100, delay 45-5 = 40 ms.
- A client 100 ms ahead gives (100,20,25,145): differences -80 and -120,
  offset -100, with the same 40 ms delay.
- 60/20 transit gives (-100,60,65,-15): differences 160 and 80,
  offset +120; the known +100 offset is biased +20, delay 85-5 = 80 ms.
- 20/60 transit gives (-100,20,25,-15): differences 120 and 40,
  offset +80 and bias -20, while round-trip delay remains 80 ms.

Literal timestamp fixtures and expected metrics are specified independently.
"""

from fractions import Fraction

import pytest

from ntp_sync_lab.core.calculations import calculate_exchange
from ntp_sync_lab.errors import InvalidInputError, InvalidTimingError
from ntp_sync_lab.models import TimestampQuad


@pytest.mark.parametrize(
    "timestamps, offset, delay, elapsed, processing",
    [
        ((0, 20_000_000, 25_000_000, 45_000_000), 0, 40_000_000, 45_000_000, 5_000_000),
        ((-100_000_000, 20_000_000, 25_000_000, -55_000_000), 100_000_000, 40_000_000, 45_000_000, 5_000_000),
        ((100_000_000, 20_000_000, 25_000_000, 145_000_000), -100_000_000, 40_000_000, 45_000_000, 5_000_000),
        ((-100_000_000, 80_000_000, 85_000_000, 65_000_000), 100_000_000, 160_000_000, 165_000_000, 5_000_000),
        ((-100_000_000, 60_000_000, 65_000_000, -15_000_000), 120_000_000, 80_000_000, 85_000_000, 5_000_000),
        ((-100_000_000, 20_000_000, 25_000_000, -15_000_000), 80_000_000, 80_000_000, 85_000_000, 5_000_000),
        ((0, 20_000_000, 45_000_000, 65_000_000), 0, 40_000_000, 65_000_000, 25_000_000),
        ((0, 20_000_000, 20_000_000, 40_000_000), 0, 40_000_000, 40_000_000, 0),
    ],
    ids=["zero", "positive", "negative", "symmetric-high", "asymmetric-forward", "asymmetric-reverse", "long-processing", "no-processing"],
)
def test_hand_derived_exchange(timestamps, offset, delay, elapsed, processing):
    metrics = calculate_exchange(TimestampQuad(*timestamps))
    assert metrics.estimated_offset_ns == Fraction(offset)
    assert isinstance(metrics.estimated_offset_ns, Fraction)
    assert metrics.round_trip_delay_ns == delay
    assert metrics.client_elapsed_ns == elapsed
    assert metrics.server_processing_ns == processing


@pytest.mark.parametrize(
    "timestamps, offset, delay",
    [
        ((0, 1, 1, 1), Fraction(1, 2), 1),
        ((0, 0, 0, 1), Fraction(-1, 2), 1),
        ((0, 100, 100, 0), Fraction(100), 0),
        ((0, 0, 0, 0), Fraction(0), 0),
    ],
    ids=["positive-half-ns", "negative-half-ns", "zero-delay-offset", "all-zero"],
)
def test_exact_boundary_cases(timestamps, offset, delay):
    metrics = calculate_exchange(TimestampQuad(*timestamps))
    assert metrics.estimated_offset_ns == offset
    assert metrics.round_trip_delay_ns == delay


@pytest.mark.parametrize("epoch", [1_794_693_600_000_000_001, -(2**80), 2**100])
def test_large_epoch_translation_preserves_single_nanosecond_differences(epoch):
    # Both client/server differences must remain exact at any epoch.
    metrics = calculate_exchange(TimestampQuad(epoch, epoch + 1, epoch + 1, epoch + 1))
    assert metrics.estimated_offset_ns == Fraction(1, 2)
    assert metrics.round_trip_delay_ns == 1


@pytest.mark.parametrize(
    "timestamps, message",
    [
        ((10, 20, 20, 9), "client reception"),
        ((0, 20, 19, 40), "server transmission"),
        ((0, 10, 30, 10), "delay is negative"),
    ],
)
def test_impossible_within_clock_timing_is_not_clamped(timestamps, message):
    with pytest.raises(InvalidTimingError, match=message) as error:
        calculate_exchange(TimestampQuad(*timestamps))
    assert error.value.code == "INVALID_TIMING"


def test_calculation_requires_typed_timestamps():
    with pytest.raises(InvalidInputError):
        calculate_exchange((0, 1, 1, 2))
