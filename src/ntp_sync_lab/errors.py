"""Framework-independent validation errors with stable machine-readable codes."""


class NtpSyncLabError(ValueError):
    """Base class for expected domain validation failures."""

    code: str

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.details = details


class InvalidInputError(NtpSyncLabError):
    """An input has an unsupported type, unit, or semantic value."""

    code = "INVALID_INPUT"


class InvalidTimingError(NtpSyncLabError):
    """An exchange violates the lab's within-clock timing assumptions."""

    code = "INVALID_TIMING"


class ProtocolError(NtpSyncLabError):
    """A protocol failure with diagnostic metadata, independent of any adapter."""



class MalformedPacketError(ProtocolError):
    code = "MALFORMED_PACKET"


class UnsupportedResponseError(ProtocolError):
    code = "UNSUPPORTED_RESPONSE"


class PeerMismatchError(ProtocolError):
    code = "PEER_MISMATCH"


class OriginMismatchError(ProtocolError):
    code = "ORIGIN_MISMATCH"


class ServerUnsynchronizedError(ProtocolError):
    code = "SERVER_UNSYNCHRONIZED"


class ServerControlError(ProtocolError):
    """Stratum-zero reply: stop this target's run, including unknown kiss codes.

    Recognition does not authenticate the sender. Peer and originate validation
    must happen before a response is allowed to produce this error.
    """

    code = "SERVER_CONTROL"
    stop_polling = True

    def __init__(self, reference_id: bytes) -> None:
        self.reference_id = reference_id
        text = reference_id.rstrip(b"\x00")
        self.kiss_code = (
            text.decode("ascii") if text and all(32 <= byte <= 126 for byte in text) else None
        )
        label = self.kiss_code or reference_id.hex()
        super().__init__(
            f"stratum-zero control response ({label}); stop polling this target",
            kiss_code=self.kiss_code,
            reference_id_hex=reference_id.hex(),
        )


class DnsFailureError(NtpSyncLabError):
    code = "DNS_FAILURE"


class NetworkError(NtpSyncLabError):
    code = "NETWORK_UNREACHABLE"


class NtpTimeoutError(NtpSyncLabError):
    code = "NTP_TIMEOUT"


class LocalClockDiscontinuityError(NtpSyncLabError):
    code = "LOCAL_CLOCK_DISCONTINUITY"


class RateLimitedError(NtpSyncLabError):
    code = "RATE_LIMITED"


class LiveStateUnavailableError(NtpSyncLabError):
    code = "LIVE_STATE_UNAVAILABLE"


class InvalidRecordingError(NtpSyncLabError):
    code = "INVALID_RECORDING"
