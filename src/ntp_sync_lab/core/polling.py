"""Small per-destination cooldown records, shared by local processes.

POSIX flock serializes only short JSON state transactions, never a socket wait.
Reserve before sending; publish atomically before allowing network I/O. The
default shared directory must not be changed to bypass policy. This is a local
educational guard, not a daemon, distributed limiter, or adversarial security
boundary. Windows needs a separately reviewed lock adapter; fail closed there.
"""

import hashlib
import ipaddress
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

try:
    import fcntl
except ImportError:  # pragma: no cover - no unsafe unlocked fallback on Windows
    fcntl = None

from ntp_sync_lab.core.clock import ClockReading, ClockSource
from ntp_sync_lab.core.packet import NtpPeer
from ntp_sync_lab.errors import LiveStateUnavailableError, RateLimitedError, ServerControlError

MIN_INTERVAL_NS = 64_000_000_000


@dataclass(frozen=True, slots=True)
class PollReservation:
    peer: NtpPeer
    token: str
    wall_ns: int
    monotonic_ns: int


class PollGuard:
    def __init__(self, clock: ClockSource, directory: Path | None = None) -> None:
        self.clock = clock
        if directory is None:
            root = os.environ.get("XDG_CACHE_HOME")
            directory = (Path(root) if root and Path(root).is_absolute() else Path.home() / ".cache")
            directory = directory / "ntp-sync-lab" / "polling"
        self.directory = Path(directory)
        self._monotonic_due: dict[str, int] = {}

    def _key(self, peer: NtpPeer) -> str:
        address = ipaddress.ip_address(peer.address)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        identity = f"{address}|{peer.port}|{peer.scope_id}"
        return hashlib.sha256(identity.encode("ascii")).hexdigest()

    @contextmanager
    def _locked(self, key: str, *, wait: bool = False) -> Iterator[Path]:
        if fcntl is None:
            raise LiveStateUnavailableError("safe live polling requires POSIX file locking")
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (self.directory / f"{key}.lock").open("a+b") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
                except BlockingIOError as error:
                    raise RateLimitedError(
                        "another local caller is updating this destination", retry_after_ns=1_000_000_000
                    ) from error
                try:
                    yield self.directory / f"{key}.json"
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as error:
            raise LiveStateUnavailableError(f"polling state unavailable: {error}") from error

    def _read(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            state = json.loads(path.read_text())
            if not isinstance(state, dict) or state["schema_version"] != "1":
                raise ValueError("invalid state schema")
            for field in ("last_wall_ns", "next_wall_ns", "timeouts"):
                if type(state[field]) is not int:
                    raise ValueError("invalid state integer")
            if state["next_wall_ns"] < state["last_wall_ns"] + MIN_INTERVAL_NS:
                raise ValueError("invalid cooldown")
            if not 0 <= state["timeouts"] <= 4:
                raise ValueError("invalid timeout count")
            if not isinstance(state["token"], str) or not state["token"]:
                raise ValueError("missing reservation token")
            block = state["control_hex"]
            if block is not None and not (isinstance(block, str) and len(bytes.fromhex(block)) == 4):
                raise ValueError("invalid control code")
            return state
        except (ValueError, KeyError, TypeError) as error:
            raise LiveStateUnavailableError("polling state is corrupt; live requests blocked") from error

    def _write(self, path: Path, state: dict) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(state, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _remaining(self, key: str, state: dict | None) -> int:
        if state is None:
            return 0
        if state["control_hex"] is not None:
            error = ServerControlError(bytes.fromhex(state["control_hex"]))
            error.details["cached_control"] = True
            raise error
        now = self.clock.wall_time_ns()
        if now < state["last_wall_ns"]:
            raise LiveStateUnavailableError("wall clock moved backward since last public probe")
        return max(
            0, state["next_wall_ns"] - now,
            self._monotonic_due.get(key, 0) - self.clock.monotonic_ns(),
        )

    def remaining_ns(self, peer: NtpPeer) -> int:
        key = self._key(peer)
        with self._locked(key) as path:
            return self._remaining(key, self._read(path))

    def reserve(self, peer: NtpPeer) -> PollReservation:
        key = self._key(peer)
        with self._locked(key) as path:
            state = self._read(path)
            remaining = self._remaining(key, state)
            if remaining:
                raise RateLimitedError("destination is in cooldown", retry_after_ns=remaining)
            reservation = PollReservation(
                peer, uuid4().hex, self.clock.wall_time_ns(), self.clock.monotonic_ns()
            )
            self._write(path, {
                "schema_version": "1", "token": reservation.token,
                "last_wall_ns": reservation.wall_ns,
                # Cover the maximum 10 s send deadline even if the process
                # dies before recording the actual completed-send time.
                "next_wall_ns": reservation.wall_ns + MIN_INTERVAL_NS + 10_000_000_000,
                "timeouts": 0 if state is None else state["timeouts"], "control_hex": None,
            })
            self._monotonic_due[key] = reservation.monotonic_ns + MIN_INTERVAL_NS + 10_000_000_000
            return reservation

    def finish(self, reservation: PollReservation, *, sent_at: ClockReading | None = None,
               timeout: bool = False,
               control: ServerControlError | None = None) -> None:
        key = self._key(reservation.peer)
        # A completed probe's backoff/control outcome must not be lost merely
        # because another cooperating caller is briefly reading the same state.
        with self._locked(key, wait=True) as path:
            state = self._read(path)
            if state is None or state["token"] != reservation.token:
                raise LiveStateUnavailableError("poll reservation no longer matches persisted state")
            state["timeouts"] = min(4, state["timeouts"] + 1) if timeout else 0
            interval = MIN_INTERVAL_NS * 2 ** state["timeouts"]
            base_wall = reservation.wall_ns if sent_at is None else sent_at.wall_ns
            base_mono = reservation.monotonic_ns if sent_at is None else sent_at.monotonic_ns
            state["last_wall_ns"] = base_wall
            state["next_wall_ns"] = base_wall + interval
            state["control_hex"] = None if control is None else control.reference_id.hex()
            self._write(path, state)
            self._monotonic_due[key] = base_mono + interval
