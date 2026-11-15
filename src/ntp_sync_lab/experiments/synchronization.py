"""Exact virtual clock step correction, using the existing modeled NTP exchange.

Client error b is client minus reference; NTP offset theta is reference minus
client, so theta=-b. Correction comes only from run_delay's calculated estimate.
This module never reads or sets a host clock, sends packets, sleeps, or slews.
"""

from dataclasses import dataclass, field
from fractions import Fraction

from ntp_sync_lab.errors import InvalidInputError
from ntp_sync_lab.experiments.delay import (
    DEFAULT_REFERENCE_UNIX_NS, MAX_DELAY_NS, MAX_OFFSET_NS, MAX_PROCESSING_NS,
    DelayConfig, DelayResult, Milliseconds, _milliseconds_to_ns, run_delay,
)
from ntp_sync_lab.models import ResultSource

MODEL_VERSION = "1"
MODEL_ASSUMPTIONS = (
    "The reference/server clock is ideal within this controlled simulation",
    "Client and reference clocks have equal rates and constant offset during the exchange",
    "One-way delays and server processing are fixed configured values, not observed Internet delays",
    "No packet loss, jitter, or oscillator drift is modeled",
    "One instantaneous step changes only virtual client time after the modeled exchange",
    "Before and after correction share the same reference instant; sequence orders the step",
    "Clock offset is a time difference; drift is a rate difference and is not estimated",
    "Live NTP does not reveal known true offset or individual one-way delays",
    "This educational step is not full NTP clock discipline or operating-system synchronization",
)


def _exact_ns(name: str, value: int | Fraction) -> Fraction:
    if type(value) is int:
        return Fraction(value)
    if not isinstance(value, Fraction) or value.denominator not in (1, 2):
        raise InvalidInputError(f"{name} must be exact whole or half nanoseconds")
    return value


def _reference_ns(value: int) -> None:
    if type(value) is not int:
        raise InvalidInputError("reference_unix_ns must be integer Unix nanoseconds")


@dataclass(frozen=True, slots=True)
class SyncConfig:
    initial_client_error_ns: int = 120_000_000
    forward_delay_ns: int = 20_000_000
    reverse_delay_ns: int = 20_000_000
    server_processing_ns: int = 5_000_000
    reference_unix_ns: int = DEFAULT_REFERENCE_UNIX_NS
    mode: str = "step"

    def __post_init__(self) -> None:
        if type(self.initial_client_error_ns) is not int:
            raise InvalidInputError("initial_client_error_ns must be integer nanoseconds")
        if self.mode != "step":
            raise InvalidInputError("only step correction is supported")
        # The approved model enforces the same bounds and native precision.
        self.to_delay_config()

    def to_delay_config(self) -> DelayConfig:
        return DelayConfig(
            true_offset_ns=-self.initial_client_error_ns,
            forward_delay_ns=self.forward_delay_ns,
            reverse_delay_ns=self.reverse_delay_ns,
            server_processing_ns=self.server_processing_ns,
            reference_unix_ns=self.reference_unix_ns,
        )


def make_sync_config(
    *, client_offset_ms: Milliseconds = 120, forward_ms: Milliseconds = 20,
    reverse_ms: Milliseconds = 20, processing_ms: Milliseconds = 5,
    reference_unix_ns: int = DEFAULT_REFERENCE_UNIX_NS, mode: str = "step",
) -> SyncConfig:
    """Reuse P1.4 conversion/bounds; client_offset_ms means client minus reference.

    Independent true-offset/correction/measurement inputs are deliberately absent:
    they would allow a measurement unrelated to this virtual clock. Initial error
    is whole nanoseconds (six fractional millisecond places); modeled estimates
    and corrected virtual times additionally preserve half nanoseconds.
    """
    return SyncConfig(
        initial_client_error_ns=_milliseconds_to_ns(
            "client_offset_ms", client_offset_ms, maximum_ns=MAX_OFFSET_NS, signed=True,
        ),
        forward_delay_ns=_milliseconds_to_ns("forward_ms", forward_ms, maximum_ns=MAX_DELAY_NS),
        reverse_delay_ns=_milliseconds_to_ns("reverse_ms", reverse_ms, maximum_ns=MAX_DELAY_NS),
        server_processing_ns=_milliseconds_to_ns(
            "processing_ms", processing_ms, maximum_ns=MAX_PROCESSING_NS,
        ),
        reference_unix_ns=reference_unix_ns, mode=mode,
    )


@dataclass(frozen=True, slots=True)
class ClockSnapshot:
    reference_unix_ns: int
    virtual_client_unix_ns: Fraction

    def __post_init__(self) -> None:
        _reference_ns(self.reference_unix_ns)
        object.__setattr__(self, "virtual_client_unix_ns", _exact_ns(
            "virtual_client_unix_ns", self.virtual_client_unix_ns,
        ))

    @property
    def client_error_ns(self) -> Fraction:
        return self.virtual_client_unix_ns - self.reference_unix_ns


@dataclass(frozen=True, slots=True)
class VirtualClock:
    client_error_ns: Fraction

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_error_ns", _exact_ns("client_error_ns", self.client_error_ns))

    def read_at(self, reference_unix_ns: int) -> ClockSnapshot:
        _reference_ns(reference_unix_ns)
        return ClockSnapshot(reference_unix_ns, reference_unix_ns + self.client_error_ns)

    def step(self, correction_ns: Fraction) -> "VirtualClock":
        return VirtualClock(self.client_error_ns + _exact_ns("correction_ns", correction_ns))


@dataclass(frozen=True, slots=True)
class CorrectionEvent:
    before: ClockSnapshot
    after: ClockSnapshot
    applied_correction_ns: Fraction

    def __post_init__(self) -> None:
        if not isinstance(self.before, ClockSnapshot) or not isinstance(self.after, ClockSnapshot):
            raise InvalidInputError("a correction event requires before/after clock snapshots")
        object.__setattr__(self, "applied_correction_ns", _exact_ns(
            "applied_correction_ns", self.applied_correction_ns,
        ))
        if self.before.reference_unix_ns != self.after.reference_unix_ns:
            raise InvalidInputError("step snapshots must use the same reference instant")
        if self.after.virtual_client_unix_ns != self.before.virtual_client_unix_ns + self.applied_correction_ns:
            raise InvalidInputError("step snapshots disagree with the applied correction")

    @property
    def mode(self) -> str:
        return "step"

    @property
    def reference_unix_ns(self) -> int:
        return self.before.reference_unix_ns


@dataclass(frozen=True, slots=True)
class SyncTimelinePoint:
    sequence: int
    stage: str
    snapshot: ClockSnapshot
    applied_correction_ns: Fraction

    def __post_init__(self) -> None:
        stages = ("measurement_start", "before_correction", "after_correction")
        if type(self.sequence) is not int or not 0 <= self.sequence < len(stages):
            raise InvalidInputError("invalid step timeline sequence")
        if self.stage != stages[self.sequence] or not isinstance(self.snapshot, ClockSnapshot):
            raise InvalidInputError("timeline stage/snapshot disagrees with its sequence")
        correction = _exact_ns("applied_correction_ns", self.applied_correction_ns)
        if self.sequence < 2 and correction != 0:
            raise InvalidInputError("no correction is applied before the step event")
        object.__setattr__(self, "applied_correction_ns", correction)


@dataclass(frozen=True, slots=True)
class SyncResult:
    """Derived immutable aggregate: an unrelated measurement cannot be supplied."""

    config: SyncConfig
    measurement: DelayResult = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.config, SyncConfig):
            raise InvalidInputError("synchronization requires a SyncConfig")
        object.__setattr__(self, "measurement", run_delay(self.config.to_delay_config()))

    @property
    def source(self) -> ResultSource:
        return ResultSource.SIMULATION

    @property
    def initial_client_error_ns(self) -> int:
        return self.config.initial_client_error_ns

    @property
    def true_offset_ns(self) -> int:
        return self.measurement.true_offset_ns

    @property
    def applied_correction_ns(self) -> Fraction:
        return self.measurement.metrics.estimated_offset_ns

    @property
    def final_client_error_ns(self) -> Fraction:
        return self.initial_client_error_ns + self.applied_correction_ns

    @property
    def estimation_error_ns(self) -> Fraction:
        return self.measurement.estimation_error_ns

    @property
    def correction_reference_unix_ns(self) -> int:
        # T4 is read by the uncorrected virtual client. Remove its initial error
        # to locate that same reception event on the ideal reference clock.
        return self.measurement.timestamps.t4_unix_ns - self.initial_client_error_ns

    @property
    def correction_event(self) -> CorrectionEvent:
        initial = VirtualClock(self.initial_client_error_ns)
        instant = self.correction_reference_unix_ns
        return CorrectionEvent(
            initial.read_at(instant), initial.step(self.applied_correction_ns).read_at(instant),
            self.applied_correction_ns,
        )

    @property
    def before(self) -> ClockSnapshot:
        return self.correction_event.before

    @property
    def after(self) -> ClockSnapshot:
        return self.correction_event.after

    @property
    def timeline(self) -> tuple[SyncTimelinePoint, ...]:
        event = self.correction_event
        return (
            SyncTimelinePoint(0, "measurement_start", VirtualClock(
                self.initial_client_error_ns
            ).read_at(self.config.reference_unix_ns), Fraction(0)),
            SyncTimelinePoint(1, "before_correction", event.before, Fraction(0)),
            SyncTimelinePoint(2, "after_correction", event.after, event.applied_correction_ns),
        )

    @property
    def assumptions(self) -> tuple[str, ...]:
        return MODEL_ASSUMPTIONS

    @property
    def explanation(self) -> tuple[str, ...]:
        if self.initial_client_error_ns > 0:
            initial = "The virtual client starts ahead of the reference by its configured initial error"
        elif self.initial_client_error_ns < 0:
            initial = "The virtual client starts behind the reference by its configured initial error"
        else:
            initial = "The virtual client starts aligned with the reference"
        return (
            initial,
            "The delay model supplies T1/T4 from this virtual client and T2/T3 from the reference",
            "The shared four-timestamp calculation estimates reference minus client time",
            "Add that estimated offset to virtual time: positive advances it, negative steps it backward",
            "Symmetric delay permits zero residual in the ideal model; "
            "asymmetric bias can remain or introduce error",
            "Residual client error and offset-estimation error have different definitions, even when equal here",
            "Only virtual time changes; no oscillator drift is inferred and the host OS clock is unchanged",
        )

    @property
    def conclusion(self) -> str:
        if self.final_client_error_ns == 0:
            return "The virtual client matches the ideal reference after the modeled symmetric-delay correction"
        return "Asymmetric measurement bias remains as virtual client error; the host clock is unchanged"


def run_sync(config: SyncConfig) -> SyncResult:
    """Measure this virtual clock via P1.4, then expose its exact step and snapshots."""
    if not isinstance(config, SyncConfig):
        raise InvalidInputError("config must be a SyncConfig")
    return SyncResult(config)
