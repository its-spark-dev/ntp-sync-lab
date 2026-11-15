import errno
import socket

import pytest

from ntp_sync_lab.core.packet import NtpPeer
from ntp_sync_lab.core.transport import ResolvedTarget, SystemResolver, UdpTransport
from ntp_sync_lab.errors import DnsFailureError, NetworkError, NtpTimeoutError
from tests.helpers import TARGET


def test_resolver_selects_one_ipv4_address_and_port_123_without_probing():
    calls = []
    def lookup(*args):
        calls.append(args)
        return [(socket.AF_INET6, socket.SOCK_DGRAM, 17, '', ('2001:db8::1', 123, 0, 0)),
                (socket.AF_INET, socket.SOCK_DGRAM, 17, '', ('192.0.2.1', 123)),
                (socket.AF_INET, socket.SOCK_DGRAM, 17, '', ('192.0.2.2', 123))]
    assert SystemResolver(lookup).resolve('fixture') == TARGET
    assert calls == [('fixture', 123, socket.AF_UNSPEC, socket.SOCK_DGRAM, socket.IPPROTO_UDP)]


def test_resolver_preserves_ipv6_scope_without_falling_back():
    def lookup(*args):
        return [(socket.AF_INET6, socket.SOCK_DGRAM, 17, '', ('fe80::1', 123, 0, 7))]
    target = SystemResolver(lookup).resolve('fixture')
    assert target.peer == NtpPeer('fe80::1', 123, 7)
    assert target.sockaddr == ('fe80::1', 123, 0, 7)


def test_dns_failure_and_empty_response_are_distinct_from_udp_timeout():
    def lookup(*args):
        raise socket.gaierror(socket.EAI_NONAME, 'fixture missing')
    with pytest.raises(DnsFailureError) as error:
        SystemResolver(lookup).resolve('fixture')
    assert error.value.details['errno'] == socket.EAI_NONAME
    with pytest.raises(DnsFailureError):
        SystemResolver(lambda *args: []).resolve('fixture')


class SocketFixture:
    def __init__(self, failure=None, partial=False):
        self.failure = failure
        self.partial = partial
        self.closed = False
        self.sent = []
        self.timeouts = []

    def settimeout(self, seconds):
        self.timeouts.append(seconds)

    def sendto(self, data, address):
        self.sent.append((data, address))
        if self.failure == 'send':
            raise OSError(errno.ENETUNREACH, 'fixture unreachable')
        return len(data) - 1 if self.partial else len(data)

    def recvfrom(self, size):
        assert size == 65535  # do not truncate a larger-than-supported reply to 48 bytes
        if self.failure == 'timeout':
            raise TimeoutError('fixture timeout')
        if self.failure == 'receive':
            raise OSError(errno.ECONNREFUSED, 'fixture refused')
        return b'response', TARGET.sockaddr

    def getsockname(self):
        return ('0.0.0.0', 54321)

    def close(self):
        self.closed = True


def test_udp_adapter_uses_ephemeral_source_and_preserves_bytes():
    fixture = SocketFixture()
    def factory(*args):
        assert args == (socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        return fixture
    with UdpTransport(factory).open(TARGET) as session:
        session.send(b'request', 3)
        result = session.receive(2)
        assert result.data == b'response' and result.address == TARGET.sockaddr
        assert session.local_peer().port == 54321
    assert fixture.sent == [(b'request', TARGET.sockaddr)]
    assert fixture.timeouts == [3, 2] and fixture.closed
    # Fixture has no bind/connect methods: use would fail, rather than silently bind port 123.


@pytest.mark.parametrize('failure,expected', [('send', NetworkError), ('receive', NetworkError), ('timeout', NtpTimeoutError)])
def test_socket_is_closed_in_each_failure_path(failure, expected):
    fixture = SocketFixture(failure)
    with pytest.raises(expected):
        with UdpTransport(lambda *args: fixture).open(TARGET) as session:
            session.send(b'request', 3)
            session.receive(3)
    assert fixture.closed and len(fixture.sent) == 1


def test_open_error_and_partial_send_are_reported_without_retry():
    def factory(*args):
        raise OSError(errno.EAFNOSUPPORT, 'fixture unsupported')
    with pytest.raises(NetworkError) as error:
        with UdpTransport(factory).open(TARGET):
            pass
    assert error.value.details['stage'] == 'open'
    fixture = SocketFixture(partial=True)
    with pytest.raises(NetworkError, match='partial'):
        with UdpTransport(lambda *args: fixture).open(TARGET) as session:
            session.send(b'request', 3)
    assert fixture.closed and len(fixture.sent) == 1


def test_close_failure_is_typed_and_does_not_mask_original_failure():
    class BadClose(SocketFixture):
        def close(self):
            self.closed = True
            raise OSError('fixture close failure')
    with pytest.raises(NetworkError) as error:
        with UdpTransport(lambda *args: BadClose()).open(TARGET):
            pass
    assert error.value.details['stage'] == 'close'
    with pytest.raises(NtpTimeoutError) as error:
        with UdpTransport(lambda *args: BadClose('timeout')).open(TARGET) as session:
            session.receive(1)
    assert 'socket_close_error' in error.value.details


def test_default_test_suite_forbids_actual_public_resolution_and_datagrams():
    with pytest.raises(AssertionError, match='Public networking'):
        socket.getaddrinfo('pool.ntp.org', 123)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        with pytest.raises(AssertionError, match='Public networking'):
            sock.sendto(b'not actually sent', ('192.0.2.1', 123))
