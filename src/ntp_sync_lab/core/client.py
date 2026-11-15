"""One safely reserved NTP request, with application-level T1/T4 capture."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ntp_sync_lab.core.clock import (
    ClockInfo, ClockReading, ClockSource, SystemClock, capture_clock, check_clock_interval,
)
from ntp_sync_lab.core.packet import (
    ClientRequest, NtpPeer, ValidatedResponse, build_request, parse_packet, validate_response,
)
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.core.transport import (
    ResolvedTarget, Resolver, SystemResolver, Transport, UdpTransport, peer_from_sockaddr,
)
from ntp_sync_lab.errors import (
    InvalidInputError, InvalidTimingError, NtpSyncLabError, NtpTimeoutError,
    OriginMismatchError, ServerControlError,
)
from ntp_sync_lab.models import ExchangeResult, Experiment, ResultSource


@dataclass(frozen=True, slots=True)
class MeasurementConfig:
    server: str
    timeout_seconds: float = 3.0
    discontinuity_threshold_ns: int = 5_000_000
    provenance_label: str = "Actual UDP NTP exchange; software timestamps"

    def __post_init__(self) -> None:
        if not isinstance(self.server, str) or not self.server or any(c.isspace() for c in self.server):
            raise InvalidInputError("server must be a nonempty hostname or numeric address")
        if (
            type(self.timeout_seconds) not in (int, float)
            or not math.isfinite(self.timeout_seconds)
            or not 0.1 <= self.timeout_seconds <= 10
        ):
            raise InvalidInputError("timeout_seconds must be finite and between 0.1 and 10")
        if type(self.discontinuity_threshold_ns) is not int or self.discontinuity_threshold_ns <= 0:
            raise InvalidInputError("discontinuity threshold must be positive integer nanoseconds")
        if not isinstance(self.provenance_label, str) or not self.provenance_label.strip():
            raise InvalidInputError("provenance_label must be a nonempty string")


@dataclass(frozen=True, slots=True)
class IgnoredDatagram:
    reason: str
    peer: NtpPeer
    packet_length: int


@dataclass(frozen=True, slots=True)
class MeasurementResult:
    config: MeasurementConfig
    exchange: ExchangeResult
    request: ClientRequest
    response: ValidatedResponse
    target: ResolvedTarget
    local_peer: NtpPeer
    sent: ClockReading
    received: ClockReading
    clock_info: ClockInfo
    wall_monotonic_discrepancy_ns: int
    ignored_count: int
    ignored_datagrams: tuple[IgnoredDatagram, ...]


def measure_once(
    config: MeasurementConfig,
    *,
    clock: ClockSource | None = None,
    resolver: Resolver | None = None,
    transport: Transport | None = None,
    guard: PollGuard | None = None,
    resolved_target: ResolvedTarget | None = None,
) -> MeasurementResult:
    """Send at most one datagram; a cooldown raises rather than sleeping/retrying.

    DNS/socket creation precede T1. T4 is captured immediately after the minimal
    transport wrapper returns, before normalization/decoding. Software packing,
    system calls, scheduling, and wrapper overhead limit accuracy. An injected
    resolved_target is for batch reuse or explicitly labeled loopback fixtures;
    the production resolver always uses destination port 123.
    """
    if not isinstance(config, MeasurementConfig):
        raise InvalidInputError("config must be a MeasurementConfig")
    clock = clock if clock is not None else SystemClock()
    guard = guard if guard is not None else PollGuard(clock)
    resolver = resolver if resolver is not None else SystemResolver()
    transport = transport if transport is not None else UdpTransport()
    reservation = None
    send_completed = None
    context: dict[str, object] = {"server": config.server, "provenance": config.provenance_label}
    ignored: list[IgnoredDatagram] = []
    ignored_count = 0
    finish_attempted = False
    try:
        target = resolved_target if resolved_target is not None else resolver.resolve(config.server)
        context.update(target_address=target.peer.address, target_port=target.peer.port,
                       target_scope_id=target.peer.scope_id)
        info = clock.info()
        with transport.open(target) as session:
            reservation = guard.reserve(target.peer)
            # The reservation deadline also bounds packing/setup before send.
            deadline = reservation.monotonic_ns + int(config.timeout_seconds * 1_000_000_000)
            sent = capture_clock(clock)
            request = build_request(sent.wall_ns)
            context.update(request_hex=request.packet.hex(), t1_unix_ns=request.t1_unix_ns,
                           sent_monotonic_ns=sent.monotonic_ns)
            remaining = deadline - clock.monotonic_ns()
            if remaining <= 0:
                raise NtpTimeoutError("measurement deadline expired before transmission", sent=False)
            session.send(request.packet, remaining / 1_000_000_000)
            send_completed = capture_clock(clock)
            context["sent"] = True
            local = session.local_peer()
            context.update(local_address=local.address, local_port=local.port)
            while True:
                remaining = deadline - clock.monotonic_ns()
                if remaining <= 0:
                    raise NtpTimeoutError("no matching NTP response before UDP deadline")
                datagram = session.receive(remaining / 1_000_000_000)
                received = capture_clock(clock)
                peer = peer_from_sockaddr(datagram.address)
                context.update(
                    t4_unix_ns=received.wall_ns, response_hex=datagram.data.hex(),
                    packet_length=len(datagram.data), actual_address=peer.address,
                    actual_port=peer.port,
                )
                if datagram.data:
                    context.update(response_version=(datagram.data[0] >> 3) & 7,
                                   response_mode=datagram.data[0] & 7)
                if len(datagram.data) >= 2:
                    context["response_stratum"] = datagram.data[1]
                if len(datagram.data) >= 48:
                    context.update(receive_timestamp_hex=datagram.data[32:40].hex(),
                                   transmit_timestamp_hex=datagram.data[40:48].hex())
                if received.monotonic_ns > deadline:
                    raise NtpTimeoutError("response was captured after the original UDP deadline")
                if peer != target.peer:
                    reason = "PEER_MISMATCH"
                else:
                    packet = parse_packet(datagram.data)
                    try:
                        response = validate_response(
                            packet, request, expected_peer=target.peer,
                            actual_peer=peer, t4_unix_ns=received.wall_ns,
                        )
                    except OriginMismatchError:
                        reason = "ORIGIN_MISMATCH"
                    except InvalidTimingError:
                        # A wall step should be diagnosed even when it also
                        # makes the local quartet mathematically impossible.
                        check_clock_interval(sent, received, config.discontinuity_threshold_ns)
                        raise
                    else:
                        discrepancy = check_clock_interval(
                            sent, received, config.discontinuity_threshold_ns
                        )
                        seconds, ns = divmod(received.wall_ns, 1_000_000_000)
                        created = datetime.fromtimestamp(seconds, timezone.utc) + timedelta(
                            microseconds=ns // 1000
                        )
                        result = MeasurementResult(
                            config=config,
                            exchange=ExchangeResult(
                                timestamps=response.timestamps, experiment=Experiment.REAL_EXCHANGE,
                                source=ResultSource.LIVE, result_id=uuid4().hex,
                                created_at_utc=created, provenance=config.provenance_label,
                                assumptions=(
                                    "Software timestamps include local scheduling uncertainty",
                                    "Unknown one-way path asymmetry; live ground truth unavailable",
                                    "Peer and originate checks are not authentication",
                                ),
                            ),
                            request=request, response=response, target=target, local_peer=local,
                            sent=sent, received=received, clock_info=info,
                            wall_monotonic_discrepancy_ns=discrepancy,
                            ignored_count=ignored_count, ignored_datagrams=tuple(ignored),
                        )
                        break
                ignored_count += 1
                if len(ignored) < 20:
                    ignored.append(IgnoredDatagram(reason, peer, len(datagram.data)))
        finish_attempted = True
        guard.finish(reservation, sent_at=send_completed)
        reservation = None
        return result
    except BaseException as error:
        if reservation is not None and not finish_attempted:
            try:
                guard.finish(
                    reservation, sent_at=send_completed,
                    timeout=isinstance(error, NtpTimeoutError),
                    control=error if isinstance(error, ServerControlError) else None,
                )
            except NtpSyncLabError as state_error:
                if isinstance(error, NtpSyncLabError):
                    error.details["polling_update_error"] = str(state_error)
        if isinstance(error, NtpSyncLabError):
            error.details.update(context)
            error.details.update(ignored_count=ignored_count,
                                 ignored_codes=tuple(item.reason for item in ignored))
        raise
