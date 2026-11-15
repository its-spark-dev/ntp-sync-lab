from ntp_sync_lab.core.clock import (
    ClockReading, SystemClock, capture_clock, check_clock_interval,
)
from ntp_sync_lab.errors import LocalClockDiscontinuityError
from tests.helpers import FakeClock
import pytest


def test_capture_brackets_wall_time_and_records_span():
    clock = FakeClock()
    assert capture_clock(clock) == ClockReading(0, 1_000_000_000, 0)
    assert clock.events == ["mono", "wall", "mono"]


@pytest.mark.parametrize("jump", [-10_000_000, 10_000_000])
def test_significant_clock_steps_are_invalid(jump):
    with pytest.raises(LocalClockDiscontinuityError) as error:
        check_clock_interval(ClockReading(0, 0, 0), ClockReading(45_000_000+jump, 45_000_000, 0), 5_000_000)
    assert error.value.details["wall_monotonic_discrepancy_ns"] == jump


def test_capture_uncertainty_is_recorded_not_claimed_as_accuracy():
    assert check_clock_interval(ClockReading(0, 0, 2), ClockReading(10, 5, 2), 1) == 5
    info = SystemClock().info()
    assert info.wall_resolution_ns > 0 and info.monotonic_resolution_ns > 0


def test_monotonic_backward_is_rejected():
    with pytest.raises(LocalClockDiscontinuityError):
        check_clock_interval(ClockReading(0, 5, 0), ClockReading(0, 4, 0), 5_000_000)
