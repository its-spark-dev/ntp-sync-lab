"""Pure NTPv4 base-header construction, parsing, and response validation.

No sockets, DNS, clock reads, retries, or rate limiting live here. A P1.3 adapter
supplies numeric expected/actual peers and its captured T4. Peer/originate checks
associate a response with a request; they do not authenticate network traffic.
"""

import ipaddress
import struct
from dataclasses import dataclass
from fractions import Fraction

from ntp_sync_lab.core.calculations import calculate_exchange
from ntp_sync_lab.core.timestamps import (
    NS_PER_SECOND,
    NtpTimestamp,
    decode_timestamp,
    encode_timestamp,
    unfold_timestamp,
)
from ntp_sync_lab.errors import (
    InvalidInputError,
    InvalidTimingError,
    MalformedPacketError,
    OriginMismatchError,
    PeerMismatchError,
    ServerControlError,
    ServerUnsynchronizedError,
    UnsupportedResponseError,
)
from ntp_sync_lab.models import ExchangeMetrics, TimestampQuad

PACKET_SIZE = 48
_HEADER = struct.Struct("!BBbbiI4s8s8s8s8s")


@dataclass(frozen=True, slots=True)
class NtpPeer:
    """Numeric address/port identity; an adapter supplies IPv6 scope when needed.

    No hostname resolution is performed. IPv6 flow labels are not peer identity.
    IPv4-mapped IPv6 and native IPv4 addresses remain distinct socket families.
    """

    address: str
    port: int
    scope_id: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.address, str) or "%" in self.address:
            raise InvalidInputError("peer address must be numeric; supply scope_id separately")
        try:
            address = ipaddress.ip_address(self.address)
        except ValueError as error:
            raise InvalidInputError("peer address must be a numeric IPv4 or IPv6 address") from error
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise InvalidInputError("peer port must be an integer from 1 to 65535")
        if type(self.scope_id) is not int or self.scope_id < 0:
            raise InvalidInputError("scope_id must be a nonnegative integer")
        if address.version == 4 and self.scope_id != 0:
            raise InvalidInputError("IPv4 peers cannot have an IPv6 scope_id")
        object.__setattr__(self, "address", str(address))


@dataclass(frozen=True, slots=True)
class ClientRequest:
    """The exact request datagram and the local T1 sample used to construct it."""

    packet: bytes
    sampled_t1_unix_ns: int

    def __post_init__(self) -> None:
        timestamp = encode_timestamp(self.sampled_t1_unix_ns)
        if timestamp.is_zero:
            raise InvalidInputError("request T1 encodes as the reserved zero timestamp")
        if (
            not isinstance(self.packet, bytes)
            or len(self.packet) != PACKET_SIZE
            or self.packet[0] != 0x23
            or self.packet[40:48] != timestamp.to_bytes()
        ):
            raise InvalidInputError("request must be v4 mode 3 with transmit bytes matching T1")

    @property
    def transmit_bytes(self) -> bytes:
        return self.packet[40:48]

    @property
    def transmit_timestamp(self) -> NtpTimestamp:
        return NtpTimestamp.from_bytes(self.transmit_bytes)

    @property
    def t1_unix_ns(self) -> int:
        """Decoded sent T1, with the unquantized local sample retained separately."""
        return decode_timestamp(self.transmit_timestamp, self.sampled_t1_unix_ns)


@dataclass(frozen=True, slots=True)
class NtpPacket:
    """Parsed base header with raw fixed-point metadata and timestamp words.

    Parsing does not assert that this is an acceptable server response.
    Reference ID stays bytes: it is not universally an IPv4 address or text.
    """

    raw: bytes
    leap_indicator: int
    version: int
    mode: int
    stratum: int
    poll_exponent: int
    precision_exponent: int
    root_delay_raw: int
    root_dispersion_raw: int
    reference_id: bytes
    reference_timestamp: NtpTimestamp
    originate_timestamp: NtpTimestamp
    receive_timestamp: NtpTimestamp
    transmit_timestamp: NtpTimestamp

    @property
    def root_delay_ns(self) -> Fraction:
        return Fraction(self.root_delay_raw * NS_PER_SECOND, 1 << 16)

    @property
    def root_dispersion_ns(self) -> Fraction:
        return Fraction(self.root_dispersion_raw * NS_PER_SECOND, 1 << 16)


@dataclass(frozen=True, slots=True)
class ValidatedResponse:
    packet: NtpPacket
    peer: NtpPeer
    timestamps: TimestampQuad
    metrics: ExchangeMetrics


def build_request(t1_unix_ns: int) -> ClientRequest:
    """Construct a 48-byte v4 mode-3 request without reading any clock.

    LI=0, stratum=0, poll=6 (64 seconds), precision=0 (conservative one-second
    declaration, not a claim of measured local resolution); unused fields zero.
    The caller enforces actual polling policy, regardless of the header value.
    """
    timestamp = encode_timestamp(t1_unix_ns)
    packet = bytes((0x23, 0, 6, 0)) + bytes(36) + timestamp.to_bytes()
    return ClientRequest(packet=packet, sampled_t1_unix_ns=t1_unix_ns)


def parse_packet(data: bytes) -> NtpPacket:
    """Parse exactly one base header; reject unimplemented trailing data honestly."""
    if not isinstance(data, bytes):
        raise InvalidInputError("packet data must be bytes")
    if len(data) < PACKET_SIZE:
        raise MalformedPacketError(
            "NTP base header is shorter than 48 bytes", packet_length=len(data)
        )
    if len(data) > PACKET_SIZE:
        raise UnsupportedResponseError(
            "trailing data is outside the supported base-header profile; not interpreted",
            packet_length=len(data),
            version=(data[0] >> 3) & 7,
            mode=data[0] & 7,
        )
    flags, stratum, poll, precision, delay, dispersion, refid, ref, orig, recv, tx = (
        _HEADER.unpack(data)
    )
    return NtpPacket(
        raw=data,
        leap_indicator=flags >> 6,
        version=(flags >> 3) & 7,
        mode=flags & 7,
        stratum=stratum,
        poll_exponent=poll,
        precision_exponent=precision,
        root_delay_raw=delay,
        root_dispersion_raw=dispersion,
        reference_id=refid,
        reference_timestamp=NtpTimestamp.from_bytes(ref),
        originate_timestamp=NtpTimestamp.from_bytes(orig),
        receive_timestamp=NtpTimestamp.from_bytes(recv),
        transmit_timestamp=NtpTimestamp.from_bytes(tx),
    )


def validate_response(
    response: NtpPacket,
    request: ClientRequest,
    *,
    expected_peer: NtpPeer,
    actual_peer: NtpPeer,
    t4_unix_ns: int,
) -> ValidatedResponse:
    """Validate a parsed reply and calculate metrics with locally supplied T4.

    Correlation checks precede stratum-zero control handling, which precedes
    normal timestamp/LI checks: control replies can legitimately have no usable
    server timestamps. Every stratum-zero reply stops this target's run; unknown
    codes remain diagnostic data. No timestamp from a different clock is used
    for chronological validation. P1.3 must check local clock discontinuities.
    """
    if not isinstance(response, NtpPacket) or not isinstance(request, ClientRequest):
        raise InvalidInputError("response/request must be parsed packet/request models")
    if not isinstance(expected_peer, NtpPeer) or not isinstance(actual_peer, NtpPeer):
        raise InvalidInputError("expected_peer and actual_peer must be NtpPeer values")
    if type(t4_unix_ns) is not int:
        raise InvalidInputError("t4_unix_ns must be integer Unix nanoseconds")
    if actual_peer != expected_peer:
        raise PeerMismatchError(
            "response peer does not match the requested destination",
            expected_address=expected_peer.address,
            expected_port=expected_peer.port,
            expected_scope_id=expected_peer.scope_id,
            actual_address=actual_peer.address,
            actual_port=actual_peer.port,
            actual_scope_id=actual_peer.scope_id,
        )
    metadata = {"version": response.version, "mode": response.mode, "packet_length": 48}
    if response.version != 4 or response.mode != 4:
        raise UnsupportedResponseError("expected an NTPv4 mode-4 server response", **metadata)
    if response.originate_timestamp.to_bytes() != request.transmit_bytes:
        raise OriginMismatchError(
            "originate timestamp does not exactly match request transmit bytes",
            expected_hex=request.transmit_bytes.hex(),
            actual_hex=response.originate_timestamp.to_bytes().hex(),
        )
    if response.stratum == 0:
        raise ServerControlError(response.reference_id)
    if response.stratum > 16:
        raise MalformedPacketError("reserved/invalid server stratum", stratum=response.stratum)
    if response.stratum == 16 or response.leap_indicator == 3:
        raise ServerUnsynchronizedError(
            "server reports an unsynchronized clock",
            stratum=response.stratum,
            leap_indicator=response.leap_indicator,
        )
    if response.receive_timestamp.is_zero or response.transmit_timestamp.is_zero:
        raise MalformedPacketError("server receive/transmit timestamp is unspecified (zero)")

    reference = request.sampled_t1_unix_ns
    if unfold_timestamp(response.transmit_timestamp, reference) < unfold_timestamp(
        response.receive_timestamp, reference
    ):
        raise InvalidTimingError("server transmission T3 precedes server reception T2")
    timestamps = TimestampQuad(
        t1_unix_ns=request.t1_unix_ns,
        t2_unix_ns=decode_timestamp(response.receive_timestamp, reference),
        t3_unix_ns=decode_timestamp(response.transmit_timestamp, reference),
        t4_unix_ns=t4_unix_ns,
    )
    return ValidatedResponse(
        packet=response,
        peer=actual_peer,
        timestamps=timestamps,
        metrics=calculate_exchange(timestamps),
    )
