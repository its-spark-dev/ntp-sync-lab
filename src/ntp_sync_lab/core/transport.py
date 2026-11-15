"""UDP/resolver adapters. No NTP parsing, calculations, or retry policy."""

import socket
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Protocol

from ntp_sync_lab.core.packet import NtpPeer
from ntp_sync_lab.errors import (
    DnsFailureError, InvalidInputError, NetworkError, NtpSyncLabError, NtpTimeoutError,
)


def peer_from_sockaddr(address: tuple) -> NtpPeer:
    # getaddrinfo/recvfrom supply numeric addresses, including a separate IPv6 scope.
    return NtpPeer(address[0].split("%", 1)[0], address[1], address[3] if len(address) == 4 else 0)


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    peer: NtpPeer
    family: int

    def __post_init__(self) -> None:
        if self.family not in (socket.AF_INET, socket.AF_INET6):
            raise InvalidInputError("only IPv4 and IPv6 UDP targets are supported")
        if (":" in self.peer.address) != (self.family == socket.AF_INET6):
            raise InvalidInputError("resolved address and socket family disagree")

    @property
    def sockaddr(self) -> tuple:
        if self.family == socket.AF_INET6:
            return (self.peer.address, self.peer.port, 0, self.peer.scope_id)
        return (self.peer.address, self.peer.port)


class Resolver(Protocol):
    def resolve(self, server: str) -> ResolvedTarget: ...


class SystemResolver:
    def __init__(self, lookup: Callable = socket.getaddrinfo) -> None:
        self.lookup = lookup

    def resolve(self, server: str) -> ResolvedTarget:
        """Select one address, preferring IPv4; never probe/fail over automatically.

        The system resolver is outside the UDP timeout. DNS may take longer.
        Production always resolves destination port 123; loopback tests inject
        a resolver returning an explicitly labeled unprivileged-port target.
        """
        try:
            addresses = self.lookup(
                server, 123, socket.AF_UNSPEC, socket.SOCK_DGRAM, socket.IPPROTO_UDP
            )
        except OSError as error:
            raise DnsFailureError(
                f"could not resolve NTP server {server}: {error}", server=server,
                errno=error.errno,
            ) from error
        candidates = [a for a in addresses if a[0] in (socket.AF_INET, socket.AF_INET6)]
        candidates.sort(key=lambda a: a[0] != socket.AF_INET)
        if not candidates:
            raise DnsFailureError("resolver returned no IPv4/IPv6 UDP addresses", server=server)
        family, _, _, _, address = candidates[0]
        return ResolvedTarget(peer_from_sockaddr(address), family)


@dataclass(frozen=True, slots=True)
class ReceivedDatagram:
    data: bytes
    address: tuple


class DatagramSession(Protocol):
    def send(self, data: bytes, timeout_seconds: float) -> None: ...
    def receive(self, timeout_seconds: float) -> ReceivedDatagram: ...
    def local_peer(self) -> NtpPeer: ...


class Transport(Protocol):
    def open(self, target: ResolvedTarget) -> AbstractContextManager[DatagramSession]: ...


class _UdpSession:
    def __init__(self, sock: socket.socket, target: ResolvedTarget) -> None:
        self.sock = sock
        self.target = target

    def send(self, data: bytes, timeout_seconds: float) -> None:
        try:
            self.sock.settimeout(timeout_seconds)
            sent = self.sock.sendto(data, self.target.sockaddr)
            if sent != len(data):
                raise NetworkError("partial UDP datagram send", stage="send")
        except OSError as error:
            raise NetworkError(
                f"UDP send failed: {error}", stage="send", errno=error.errno
            ) from error

    def receive(self, timeout_seconds: float) -> ReceivedDatagram:
        try:
            self.sock.settimeout(timeout_seconds)
            data, address = self.sock.recvfrom(65535)
            # Only wrap the raw return value. The client captures T4 before peer
            # normalization, parsing, validation, or any other expensive work.
            return ReceivedDatagram(data, address)
        except TimeoutError as error:
            raise NtpTimeoutError("no matching NTP response before UDP deadline") from error
        except OSError as error:
            raise NetworkError(
                f"UDP receive failed: {error}", stage="receive", errno=error.errno
            ) from error

    def local_peer(self) -> NtpPeer:
        try:
            return peer_from_sockaddr(self.sock.getsockname())
        except OSError as error:
            raise NetworkError(f"could not inspect local UDP endpoint: {error}", stage="local_peer") from error


class UdpTransport:
    def __init__(self, socket_factory: Callable = socket.socket) -> None:
        self.socket_factory = socket_factory

    @contextmanager
    def open(self, target: ResolvedTarget) -> Iterator[DatagramSession]:
        try:
            sock = self.socket_factory(target.family, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        except OSError as error:
            raise NetworkError(
                f"could not open UDP socket: {error}", stage="open", errno=error.errno
            ) from error
        active_error = None
        try:
            # No bind: sendto lets the OS choose an ephemeral source port.
            yield _UdpSession(sock, target)
        except BaseException as error:
            active_error = error
            raise
        finally:
            try:
                sock.close()
            except OSError as error:
                if active_error is None:
                    raise NetworkError(f"could not close UDP socket: {error}", stage="close") from error
                if isinstance(active_error, NtpSyncLabError):
                    active_error.details["socket_close_error"] = str(error)
