"""Enforce the default suite's network boundary, even if an adapter is miswired."""

import ipaddress
import socket
import sys


def _loopback_only(event, args):
    if event == "socket.getaddrinfo":
        host = args[0]
    elif event in ("socket.connect", "socket.sendto"):
        if args[0].family == socket.AF_UNIX:
            return
        host = args[1][0]
    elif event in ("socket.gethostbyname", "socket.gethostbyaddr"):
        host = args[0]
    else:
        return
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise AssertionError(f"Public networking is forbidden in tests: {event} {host!r}")


sys.addaudithook(_loopback_only)
