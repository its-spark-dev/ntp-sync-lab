"""Explicitly synthetic clock/transport fixtures; no public measurements."""

import socket
from contextlib import contextmanager
from dataclasses import dataclass

from ntp_sync_lab.core.clock import ClockInfo
from ntp_sync_lab.core.packet import NtpPeer
from ntp_sync_lab.core.timestamps import NtpTimestamp, decode_timestamp, encode_timestamp
from ntp_sync_lab.core.transport import ReceivedDatagram, ResolvedTarget
from ntp_sync_lab.errors import NtpTimeoutError

TARGET = ResolvedTarget(NtpPeer("192.0.2.1", 123), socket.AF_INET)


class FakeClock:
    def __init__(self):
        self.wall = 0
        self.mono = 1_000_000_000
        self.sleeps = []
        self.events = []
        self.interrupt_sleep = False

    def wall_time_ns(self):
        self.events.append("wall")
        return self.wall

    def monotonic_ns(self):
        self.events.append("mono")
        return self.mono

    def advance(self, ns, wall_jump=0):
        self.wall += ns + wall_jump
        self.mono += ns

    def sleep(self, seconds):
        if self.interrupt_sleep:
            raise KeyboardInterrupt
        self.sleeps.append(seconds)
        self.advance(round(seconds * 1_000_000_000))

    def info(self):
        return ClockInfo(1, 1, True, "Deterministic fake clock fixture")


class StaticResolver:
    def __init__(self, target=TARGET):
        self.target = target
        self.calls = []

    def resolve(self, server):
        self.calls.append(server)
        if isinstance(self.target, BaseException):
            raise self.target
        return self.target


def response_bytes(request, *, offset_ns=100_000_000, processing_ns=5_000_000):
    # Independently specified scenario: df=dr=20ms, processing=5ms and true
    # server-minus-client offset=100ms. Expected RTT=40ms, client elapsed=45ms.
    # Generate server wire words, never the expected calculation or metrics.
    t1 = decode_timestamp(NtpTimestamp.from_bytes(request[40:48]), 0)
    t2 = t1 + 20_000_000 + offset_ns
    t3 = t2 + processing_ns
    return (
        bytes.fromhex("240206ec") + bytes(8) + b"TEST" + bytes(8)
        + request[40:48] + encode_timestamp(t2).to_bytes() + encode_timestamp(t3).to_bytes()
    )


@dataclass
class Delivery:
    delay_ns: int = 45_000_000
    data: object = response_bytes
    address: tuple = TARGET.sockaddr
    wall_jump_ns: int = 0


class FakeSession:
    def __init__(self, clock, events):
        self.clock = clock
        self.events = list(events)
        self.sent = []
        self.timeouts = []
        self.closed = False

    def send(self, data, timeout_seconds):
        self.sent.append((data, self.clock.monotonic_ns()))

    def receive(self, timeout_seconds):
        self.timeouts.append(timeout_seconds)
        event = self.events.pop(0) if self.events else NtpTimeoutError("fixture timeout")
        if isinstance(event, BaseException):
            if isinstance(event, NtpTimeoutError):
                self.clock.advance(round(timeout_seconds * 1_000_000_000))
            raise event
        self.clock.advance(event.delay_ns, event.wall_jump_ns)
        self.clock.events.append("received")
        data = event.data(self.sent[0][0]) if callable(event.data) else event.data
        return ReceivedDatagram(data, event.address)

    def local_peer(self):
        return NtpPeer("0.0.0.0", 54321)


class FakeTransport:
    def __init__(self, clock, scenarios=None):
        self.clock = clock
        self.scenarios = list(scenarios if scenarios is not None else [[Delivery()]])
        self.sessions = []

    @contextmanager
    def open(self, target):
        scenario = self.scenarios.pop(0)
        if isinstance(scenario, BaseException):
            raise scenario
        session = FakeSession(self.clock, scenario)
        self.sessions.append(session)
        try:
            yield session
        finally:
            session.closed = True
