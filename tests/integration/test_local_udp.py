"""Actual UDP loopback test fixture, never a public NTP measurement."""

import socket
import threading
import time

import pytest

from ntp_sync_lab.core.client import MeasurementConfig, measure_once
from ntp_sync_lab.core.clock import SystemClock
from ntp_sync_lab.core.packet import NtpPeer
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.core.timestamps import encode_timestamp
from ntp_sync_lab.core.transport import ResolvedTarget, UdpTransport
from tests.helpers import StaticResolver


@pytest.mark.parametrize('family,host', [(socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')])
def test_real_loopback_udp_exchange_on_unprivileged_port(tmp_path, family, host):
    try:
        server = socket.socket(family, socket.SOCK_DGRAM)
    except OSError as error:
        pytest.skip(f'loopback family unavailable: {error}')
    with server:
        try:
            server.bind((host, 0))
        except OSError as error:
            pytest.skip(f'loopback bind unavailable: {error}')
        port = server.getsockname()[1]
        assert port > 1024 and port != 123
        server.settimeout(2)
        requests, errors, sockets = [], [], []
        def respond():
            try:
                request, peer = server.recvfrom(65535)
                t2 = time.time_ns()
                requests.append((request, peer))
                prefix = b'\x24\x01\x06\xec' + bytes(8) + b'TEST' + bytes(8) + request[40:48]
                t3 = time.time_ns()
                response = prefix + encode_timestamp(t2).to_bytes() + encode_timestamp(t3).to_bytes()
                server.sendto(response, peer)
            except BaseException as error:
                errors.append(error)
        def tracked_socket(*args):
            sock = socket.socket(*args)
            sockets.append(sock)
            return sock
        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        clock = SystemClock()
        try:
            result = measure_once(
                MeasurementConfig(host, provenance_label='Actual loopback UDP test fixture; not public NTP'),
                clock=clock, resolver=StaticResolver(ResolvedTarget(NtpPeer(host, port), family)),
                transport=UdpTransport(tracked_socket), guard=PollGuard(clock, tmp_path),
            )
        finally:
            thread.join(timeout=3)
        assert not thread.is_alive() and not errors
        assert len(requests) == 1
        assert result.request.packet == requests[0][0]
        assert result.request.transmit_bytes == result.response.packet.originate_timestamp.to_bytes()
        assert result.local_peer.port == requests[0][1][1] > 1024
        assert result.target.peer.port == port
        assert result.response.packet.version == result.response.packet.mode == 4
        assert result.response.metrics.round_trip_delay_ns >= 0
        assert result.response.metrics.server_processing_ns >= 0
        assert result.exchange.true_offset_ns is None
        assert 'not public NTP' in result.exchange.provenance
        assert sockets and all(sock.fileno() == -1 for sock in sockets)
