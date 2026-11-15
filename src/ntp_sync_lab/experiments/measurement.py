"""Bounded sequential measurements and descriptive summaries; no NTP discipline."""

import math
from dataclasses import dataclass
from fractions import Fraction
from statistics import median
from types import MappingProxyType
from typing import Mapping

from ntp_sync_lab.core.client import MeasurementConfig, MeasurementResult, measure_once
from ntp_sync_lab.core.clock import ClockSource, SystemClock
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.core.transport import Resolver, SystemResolver, Transport, UdpTransport
from ntp_sync_lab.errors import (
    InvalidInputError, LiveStateUnavailableError, NtpSyncLabError, RateLimitedError, ServerControlError,
)


@dataclass(frozen=True, slots=True)
class FailureInfo:
    code: str
    message: str
    details: Mapping[str, object]

    @classmethod
    def from_error(cls, error: NtpSyncLabError) -> "FailureInfo":
        # Adapter-owned diagnostics contain scalar values and immutable tuples.
        return cls(error.code, str(error), MappingProxyType(dict(error.details)))


@dataclass(frozen=True, slots=True)
class MeasurementAttempt:
    number: int
    result: MeasurementResult | None = None
    error: FailureInfo | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.error is None):
            raise InvalidInputError("an attempt must contain exactly one result or failure")


@dataclass(frozen=True, slots=True)
class MeasurementSummary:
    valid_count: int
    median_offset_ns: Fraction
    minimum_round_trip_delay_ns: int
    offset_range_ns: Fraction


@dataclass(frozen=True, slots=True)
class MeasurementBatch:
    server: str
    requested_count: int
    attempts: tuple[MeasurementAttempt, ...]
    interrupted: bool = False
    stop_reason: str | None = None

    @property
    def successes(self) -> tuple[MeasurementResult, ...]:
        return tuple(item.result for item in self.attempts if item.result is not None)

    @property
    def failures(self) -> tuple[FailureInfo, ...]:
        return tuple(item.error for item in self.attempts if item.error is not None)

    @property
    def summary(self) -> MeasurementSummary | None:
        results = self.successes
        if not results:
            return None
        offsets = [item.response.metrics.estimated_offset_ns for item in results]
        return MeasurementSummary(
            len(results), median(offsets),
            min(item.response.metrics.round_trip_delay_ns for item in results),
            max(offsets) - min(offsets),
        )


def run_measurements(
    config: MeasurementConfig, *, count: int = 1, interval_seconds: float = 64,
    clock: ClockSource | None = None, resolver: Resolver | None = None,
    transport: Transport | None = None, guard: PollGuard | None = None,
) -> MeasurementBatch:
    """Resolve once, measure sequentially, retain failures and interruption state.

    This batch requests explicit separate attempts, not automatic probe retries.
    An initial cooldown or contention fails visibly. Between attempts, wait for
    both the requested interval and shared backoff. A competing reservation
    after that wait stops the batch, rather than busy-waiting indefinitely.
    """
    if not isinstance(config, MeasurementConfig):
        raise InvalidInputError("config must be a MeasurementConfig")
    if type(count) is not int or not 1 <= count <= 10:
        raise InvalidInputError("count must be an integer from 1 to 10")
    if (
        type(interval_seconds) not in (int, float) or not math.isfinite(interval_seconds)
        or not 64 <= interval_seconds <= 3600
    ):
        raise InvalidInputError("interval_seconds must be finite and between 64 and 3600")
    clock = clock if clock is not None else SystemClock()
    resolver = resolver if resolver is not None else SystemResolver()
    transport = transport if transport is not None else UdpTransport()
    guard = guard if guard is not None else PollGuard(clock)
    attempts: list[MeasurementAttempt] = []
    stop = None
    interrupted = False
    try:
        try:
            target = resolver.resolve(config.server)
        except NtpSyncLabError as error:
            error.details.setdefault("server", config.server)
            error.details.setdefault("provenance", config.provenance_label)
            return MeasurementBatch(config.server, count, (MeasurementAttempt(
                1, error=FailureInfo.from_error(error)
            ),), stop_reason=error.code)
        due = 0
        for index in range(count):
            started = clock.monotonic_ns()
            try:
                if index:
                    delay = max(due - clock.monotonic_ns(), guard.remaining_ns(target.peer))
                    if delay > 0:
                        clock.sleep(delay / 1_000_000_000)
                started = clock.monotonic_ns()
                result = measure_once(
                    config, clock=clock, resolver=resolver, transport=transport,
                    guard=guard, resolved_target=target,
                )
            except NtpSyncLabError as error:
                attempts.append(MeasurementAttempt(index + 1, error=FailureInfo.from_error(error)))
                if error.details.get("polling_update_error"):
                    stop = "LIVE_STATE_UNAVAILABLE"
                    break
                if isinstance(error, (ServerControlError, LiveStateUnavailableError, RateLimitedError)):
                    stop = error.code
                    break
            else:
                attempts.append(MeasurementAttempt(index + 1, result=result))
            due = started + int(interval_seconds * 1_000_000_000)
    except KeyboardInterrupt:
        interrupted = True
        stop = "INTERRUPTED"
    return MeasurementBatch(config.server, count, tuple(attempts), interrupted, stop)
