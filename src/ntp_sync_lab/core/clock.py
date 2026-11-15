"""Injectable software clock capture. No clock-setting operations exist here."""

import math
import time
from dataclasses import dataclass
from typing import Protocol

from ntp_sync_lab.errors import LocalClockDiscontinuityError


@dataclass(frozen=True, slots=True)
class ClockInfo:
    wall_resolution_ns: int
    monotonic_resolution_ns: int
    wall_adjustable: bool
    implementation: str


@dataclass(frozen=True, slots=True)
class ClockReading:
    wall_ns: int
    monotonic_ns: int
    read_span_ns: int


class ClockSource(Protocol):
    def wall_time_ns(self) -> int: ...
    def monotonic_ns(self) -> int: ...
    def sleep(self, seconds: float) -> None: ...
    def info(self) -> ClockInfo: ...


class SystemClock:
    wall_time_ns = staticmethod(time.time_ns)
    monotonic_ns = staticmethod(time.monotonic_ns)
    sleep = staticmethod(time.sleep)

    def info(self) -> ClockInfo:
        wall = time.get_clock_info("time")
        mono = time.get_clock_info("monotonic")
        return ClockInfo(
            math.ceil(wall.resolution * 1_000_000_000),
            math.ceil(mono.resolution * 1_000_000_000),
            wall.adjustable,
            wall.implementation,
        )


def capture_clock(clock: ClockSource) -> ClockReading:
    """Bracket a wall reading by monotonic readings; record midpoint and span.

    These are application timestamps, not kernel or wire timestamps. A large
    span reveals possible preemption; it does not certify clock accuracy.
    """
    before = clock.monotonic_ns()
    wall = clock.wall_time_ns()
    after = clock.monotonic_ns()
    if after < before:
        raise LocalClockDiscontinuityError("monotonic clock moved backward during capture")
    return ClockReading(wall, (before + after) // 2, after - before)


def check_clock_interval(sent: ClockReading, received: ClockReading, threshold_ns: int) -> int:
    discrepancy = (received.wall_ns - sent.wall_ns) - (
        received.monotonic_ns - sent.monotonic_ns
    )
    if (
        received.monotonic_ns < sent.monotonic_ns
        or abs(discrepancy) > threshold_ns + sent.read_span_ns + received.read_span_ns
    ):
        raise LocalClockDiscontinuityError(
            "wall/monotonic elapsed times disagree; measurement invalidated",
            wall_monotonic_discrepancy_ns=discrepancy,
            threshold_ns=threshold_ns,
        )
    return discrepancy
