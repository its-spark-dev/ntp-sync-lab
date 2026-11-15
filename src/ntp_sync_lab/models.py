"""Immutable domain foundations; no networking, clocks, or presentation code.

Absolute timestamps are integer Unix nanoseconds, already decoded from any wire
format. NTP offset is server minus client. Virtual client error uses the opposite
sign (client minus reference); virtual correction lives in experiments.synchronization.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from fractions import Fraction

from ntp_sync_lab.errors import InvalidInputError


class ResultSource(str, Enum):
    """Origins supported by the exchange foundation; replay is added in P1.6."""

    LIVE = "live"
    SIMULATION = "simulation"


class Experiment(str, Enum):
    """Stable experiment identifiers used by the shared versioned envelope."""

    REAL_EXCHANGE = "real_exchange"
    NETWORK_DELAY = "network_delay"
    CLOCK_SYNC = "clock_sync"


def _require_integer_ns(name: str, value: object) -> None:
    # bool is an int subclass but is never a timestamp or a duration.
    if type(value) is not int:
        raise InvalidInputError(f"{name} must be an integer number of nanoseconds")


@dataclass(frozen=True, slots=True)
class TimestampQuad:
    """T1/T4 belong to the client clock; T2/T3 belong to the server clock.

    Negative Unix timestamps and arbitrary integer magnitudes are allowed.
    Cross-clock chronological ordering cannot be inferred from their values.
    Within-clock timing checks belong to calculate_exchange, not wire parsing.
    """

    t1_unix_ns: int
    t2_unix_ns: int
    t3_unix_ns: int
    t4_unix_ns: int

    def __post_init__(self) -> None:
        for name in ("t1_unix_ns", "t2_unix_ns", "t3_unix_ns", "t4_unix_ns"):
            _require_integer_ns(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class ExchangeMetrics:
    """Exact four-timestamp results, all in nanosecond units.

    A positive estimated_offset_ns means the client is behind the server.
    Offset can have a half-nanosecond fraction; the other intervals are integers.
    A consistent interval decomposition is required, not an accuracy guarantee.
    """

    estimated_offset_ns: Fraction
    round_trip_delay_ns: int
    client_elapsed_ns: int
    server_processing_ns: int

    def __post_init__(self) -> None:
        if not isinstance(self.estimated_offset_ns, Fraction):
            raise InvalidInputError("estimated_offset_ns must be an exact Fraction")
        if self.estimated_offset_ns.denominator not in (1, 2):
            raise InvalidInputError("estimated_offset_ns must be a whole or half nanosecond")
        for name in ("round_trip_delay_ns", "client_elapsed_ns", "server_processing_ns"):
            value = getattr(self, name)
            _require_integer_ns(name, value)
            if value < 0:
                raise InvalidInputError(f"{name} must be nonnegative")
        if self.client_elapsed_ns != self.round_trip_delay_ns + self.server_processing_ns:
            raise InvalidInputError("client elapsed time must equal network delay plus processing")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExchangeResult:
    """Immutable input to the versioned exchange serializer.

    Metadata is supplied by the caller: constructing/serializing this result
    never reads a clock, creates a random ID, or sends a request. Metrics and
    estimation error are derived at serialization time by the shared calculator,
    so callers cannot supply inconsistent calculated values. This is not yet a
    complete live measurement or a replay/recording model.
    """

    timestamps: TimestampQuad
    experiment: Experiment
    source: ResultSource
    result_id: str
    created_at_utc: datetime
    provenance: str
    assumptions: tuple[str, ...] = ()
    true_offset_ns: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.timestamps, TimestampQuad):
            raise InvalidInputError("timestamps must be a TimestampQuad")
        if not isinstance(self.experiment, Experiment):
            raise InvalidInputError("experiment must be an Experiment")
        if not isinstance(self.source, ResultSource):
            raise InvalidInputError("source must be a ResultSource")
        for name in ("result_id", "provenance"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidInputError(f"{name} must be a nonempty string")
        if (
            not isinstance(self.created_at_utc, datetime)
            or self.created_at_utc.utcoffset() != timedelta(0)
        ):
            raise InvalidInputError("created_at_utc must be a timezone-aware UTC datetime")
        if not isinstance(self.assumptions, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.assumptions
        ):
            raise InvalidInputError("assumptions must be a tuple of nonempty strings")
        if self.true_offset_ns is not None:
            _require_integer_ns("true_offset_ns", self.true_offset_ns)
        if self.source is ResultSource.LIVE:
            if self.experiment is not Experiment.REAL_EXCHANGE:
                raise InvalidInputError("live results must describe a real exchange")
            if self.true_offset_ns is not None:
                raise InvalidInputError("live ground truth is unknown and must remain None")
