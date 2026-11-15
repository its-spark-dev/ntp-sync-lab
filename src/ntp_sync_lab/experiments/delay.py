"""Deterministic delay/asymmetry model. No networking, clock reads, or sleeps.

Offset is server minus client. The server is the model reference; the client
reads reference minus true_offset_ns. Only timestamp generation belongs here:
authoritative offset/delay calculations remain in core.calculations.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from types import MappingProxyType

from ntp_sync_lab.core.calculations import calculate_exchange
from ntp_sync_lab.errors import InvalidInputError
from ntp_sync_lab.models import ExchangeMetrics, ResultSource, TimestampQuad

DEFAULT_REFERENCE_UNIX_NS = 1_700_000_000_000_000_000
MAX_OFFSET_NS = 60_000_000_000
MAX_DELAY_NS = 2_000_000_000
MAX_PROCESSING_NS = 500_000_000
MODEL_VERSION = "1"
MODEL_ASSUMPTIONS = (
    "The server is an ideal reference within this controlled simulation",
    "Clocks have equal rates and a constant server-minus-client offset",
    "Forward and reverse delays are fixed configured values, not Internet observations",
    "Server processing time is known and constant",
    "No packet loss, jitter, oscillator drift, or clock correction is modeled",
    "Symmetric delay introduces no offset-estimation bias under these assumptions",
    "Actual public NTP exchanges do not reveal true clock offset or true one-way delays",
)
_PRESET_DELAYS = MappingProxyType({
    "symmetric-low": (20_000_000, 20_000_000),
    "symmetric-high": (80_000_000, 80_000_000),
    "asymmetric-forward": (60_000_000, 20_000_000),
    "asymmetric-reverse": (20_000_000, 60_000_000),
})

Milliseconds = str | Decimal | int


def _bounded_ns(name: str, value: int, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise InvalidInputError(f"{name} must be integer nanoseconds from {minimum} to {maximum}")


def _milliseconds_to_ns(name: str, value: Milliseconds, *, maximum_ns: int,
                        signed: bool = False) -> int:
    """Convert exactly, independent of the caller's Decimal precision/context.

    Accept strings, Decimal, or integers only; floats/bools are ambiguous inputs.
    At most six fractional millisecond places are supported, including trailing
    zero places. Scientific notation is allowed subject to the same bound.
    """
    if type(value) not in (str, Decimal, int):
        raise InvalidInputError(f"{name} must be a decimal string, Decimal, or integer milliseconds")
    try:
        decimal = Decimal(value)
    except InvalidOperation as error:
        raise InvalidInputError(f"{name} must be a valid decimal millisecond value") from error
    if not decimal.is_finite():
        raise InvalidInputError(f"{name} must be finite")
    if decimal.as_tuple().exponent < -6:
        raise InvalidInputError(f"{name} supports at most six fractional millisecond places")
    if decimal.copy_abs() > Decimal(maximum_ns // 1_000_000):
        raise InvalidInputError(f"{name} exceeds the supported millisecond range")
    numerator, denominator = decimal.as_integer_ratio()
    ns, remainder = divmod(numerator * 1_000_000, denominator)
    if remainder:
        raise InvalidInputError(f"{name} must resolve to whole nanoseconds")
    _bounded_ns(name, ns, -maximum_ns if signed else 0, maximum_ns)
    return ns


@dataclass(frozen=True, slots=True)
class DelayConfig:
    true_offset_ns: int = 100_000_000
    forward_delay_ns: int = 20_000_000
    reverse_delay_ns: int = 20_000_000
    server_processing_ns: int = 5_000_000
    reference_unix_ns: int = DEFAULT_REFERENCE_UNIX_NS
    preset_id: str | None = None

    def __post_init__(self) -> None:
        _bounded_ns("true_offset_ns", self.true_offset_ns, -MAX_OFFSET_NS, MAX_OFFSET_NS)
        _bounded_ns("forward_delay_ns", self.forward_delay_ns, 0, MAX_DELAY_NS)
        _bounded_ns("reverse_delay_ns", self.reverse_delay_ns, 0, MAX_DELAY_NS)
        _bounded_ns("server_processing_ns", self.server_processing_ns, 0, MAX_PROCESSING_NS)
        if type(self.reference_unix_ns) is not int:
            raise InvalidInputError("reference_unix_ns must be integer Unix nanoseconds")
        if self.preset_id is not None:
            if not isinstance(self.preset_id, str) or self.preset_id not in _PRESET_DELAYS:
                raise InvalidInputError("unknown delay preset")
            if (
                (self.forward_delay_ns, self.reverse_delay_ns) != _PRESET_DELAYS[self.preset_id]
                or self.true_offset_ns != 100_000_000 or self.server_processing_ns != 5_000_000
                or self.reference_unix_ns != DEFAULT_REFERENCE_UNIX_NS
            ):
                raise InvalidInputError("preset identity conflicts with custom parameters")


DELAY_PRESETS = MappingProxyType({
    name: DelayConfig(forward_delay_ns=forward, reverse_delay_ns=reverse, preset_id=name)
    for name, (forward, reverse) in _PRESET_DELAYS.items()
})


def make_delay_config(
    *, preset: str | None = None, true_offset_ms: Milliseconds | None = None,
    forward_ms: Milliseconds | None = None, reverse_ms: Milliseconds | None = None,
    processing_ms: Milliseconds | None = None, reference_unix_ns: int | None = None,
) -> DelayConfig:
    """Validate preset/custom selection for future CLI/API boundaries.

    An explicit preset is mutually exclusive with every explicit custom value.
    Without a preset, omitted fields use 100/20/20/5 ms and the fixed reference.
    No arguments selects the named symmetric-low preset.
    """
    custom = (true_offset_ms, forward_ms, reverse_ms, processing_ms, reference_unix_ns)
    if preset is not None:
        if any(value is not None for value in custom):
            raise InvalidInputError("preset and custom delay parameters are mutually exclusive")
        if not isinstance(preset, str) or preset not in DELAY_PRESETS:
            raise InvalidInputError("unknown delay preset")
        return DELAY_PRESETS[preset]
    if all(value is None for value in custom):
        return DELAY_PRESETS["symmetric-low"]
    return DelayConfig(
        true_offset_ns=_milliseconds_to_ns(
            "true_offset_ms", 100 if true_offset_ms is None else true_offset_ms,
            maximum_ns=MAX_OFFSET_NS, signed=True,
        ),
        forward_delay_ns=_milliseconds_to_ns(
            "forward_ms", 20 if forward_ms is None else forward_ms, maximum_ns=MAX_DELAY_NS,
        ),
        reverse_delay_ns=_milliseconds_to_ns(
            "reverse_ms", 20 if reverse_ms is None else reverse_ms, maximum_ns=MAX_DELAY_NS,
        ),
        server_processing_ns=_milliseconds_to_ns(
            "processing_ms", 5 if processing_ms is None else processing_ms,
            maximum_ns=MAX_PROCESSING_NS,
        ),
        reference_unix_ns=(DEFAULT_REFERENCE_UNIX_NS if reference_unix_ns is None else reference_unix_ns),
    )


@dataclass(frozen=True, slots=True)
class DelayResult:
    config: DelayConfig
    timestamps: TimestampQuad
    metrics: ExchangeMetrics

    @property
    def source(self) -> ResultSource:
        return ResultSource.SIMULATION

    @property
    def true_offset_ns(self) -> int:
        return self.config.true_offset_ns

    @property
    def estimation_error_ns(self) -> Fraction:
        return self.metrics.estimated_offset_ns - self.true_offset_ns

    @property
    def assumptions(self) -> tuple[str, ...]:
        return MODEL_ASSUMPTIONS

    @property
    def conclusion(self) -> str:
        if self.config.forward_delay_ns == self.config.reverse_delay_ns:
            return "Symmetric delay cancels from the offset estimate in this ideal model; RTT is separate"
        direction = "positive" if self.config.forward_delay_ns > self.config.reverse_delay_ns else "negative"
        return (
            f"Asymmetric delay creates {direction} offset-estimation bias; "
            "RTT and estimation error are different quantities"
        )


def run_delay(config: DelayConfig) -> DelayResult:
    """Generate the modeled quartet, then delegate all NTP metrics to the core."""
    if not isinstance(config, DelayConfig):
        raise InvalidInputError("config must be a DelayConfig")
    r0 = config.reference_unix_ns
    theta = config.true_offset_ns
    df = config.forward_delay_ns
    dr = config.reverse_delay_ns
    p = config.server_processing_ns
    timestamps = TimestampQuad(r0 - theta, r0 + df, r0 + df + p, r0 + df + p + dr - theta)
    return DelayResult(config, timestamps, calculate_exchange(timestamps))


def _validate_points(points: int) -> None:
    if type(points) is not int or not 2 <= points <= 200:
        raise InvalidInputError("a delay sweep must contain 2–200 points")


def fixed_rtt_sweep(
    *, round_trip_ms: Milliseconds, points: int = 9,
    true_offset_ms: Milliseconds = 100, processing_ms: Milliseconds = 5,
    reference_unix_ns: int = DEFAULT_REFERENCE_UNIX_NS,
) -> tuple[DelayResult, ...]:
    """Ordered all-reverse to all-forward grid at exactly the requested RTT.

    Endpoint support limits total RTT to 2000 ms (each one-way bound). Round each
    forward point once to whole nanoseconds, ties to even; reverse = total minus
    forward. Tiny totals can produce repeated points, never a changed total.
    This interface has no preset or individual forward/reverse arguments.
    """
    _validate_points(points)
    total = _milliseconds_to_ns("round_trip_ms", round_trip_ms, maximum_ns=MAX_DELAY_NS)
    base = make_delay_config(
        true_offset_ms=true_offset_ms, forward_ms=0, reverse_ms=0,
        processing_ms=processing_ms, reference_unix_ns=reference_unix_ns,
    )
    return tuple(
        run_delay(replace(base, forward_delay_ns=forward, reverse_delay_ns=total - forward))
        for forward in (round(Fraction(total * i, points - 1)) for i in range(points))
    )


def equal_increase_sweep(
    config: DelayConfig, *, increments_ms: Sequence[Milliseconds],
) -> tuple[DelayResult, ...]:
    """Add each nonnegative increment to both delays, preserving any asymmetry.

    Increments must be strictly increasing, 2–200 points. Every resulting one-way
    delay must remain within 2000 ms; reject the whole request rather than clip.
    """
    if not isinstance(config, DelayConfig):
        raise InvalidInputError("config must be a DelayConfig")
    if not isinstance(increments_ms, Sequence) or isinstance(increments_ms, (str, bytes)):
        raise InvalidInputError("increments_ms must be an ordered sequence of decimal values")
    _validate_points(len(increments_ms))
    increments = tuple(
        _milliseconds_to_ns("increment_ms", value, maximum_ns=MAX_DELAY_NS)
        for value in increments_ms
    )
    if any(a >= b for a, b in zip(increments, increments[1:])):
        raise InvalidInputError("equal-delay increments must be strictly increasing")
    configs = tuple(replace(
        config, forward_delay_ns=config.forward_delay_ns + increment,
        reverse_delay_ns=config.reverse_delay_ns + increment, preset_id=None,
    ) for increment in increments)
    return tuple(run_delay(item) for item in configs)
