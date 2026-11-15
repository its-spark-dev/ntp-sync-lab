import json
import multiprocessing
import threading
from pathlib import Path

import pytest

from ntp_sync_lab.core.clock import SystemClock, capture_clock
from ntp_sync_lab.core.packet import NtpPeer
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.errors import (
    LiveStateUnavailableError, NtpSyncLabError, RateLimitedError, ServerControlError,
)
from tests.helpers import FakeClock, TARGET


def test_completed_send_has_64_second_restart_safe_cooldown(tmp_path):
    clock = FakeClock()
    guard = PollGuard(clock, tmp_path)
    reservation = guard.reserve(TARGET.peer)
    assert guard.remaining_ns(TARGET.peer) == 74_000_000_000  # crash/send grace
    clock.advance(2_000_000)
    guard.finish(reservation, sent_at=capture_clock(clock))
    other_invocation = PollGuard(clock, tmp_path)
    assert other_invocation.remaining_ns(TARGET.peer) == 64_000_000_000
    with pytest.raises(RateLimitedError):
        other_invocation.reserve(TARGET.peer)
    clock.advance(64_000_000_000)
    assert other_invocation.reserve(TARGET.peer)


def test_timeout_backoff_is_persisted_capped_and_success_resets_it(tmp_path):
    clock = FakeClock()
    for interval in [128, 256, 512, 1024, 1024]:
        guard = PollGuard(clock, tmp_path)
        reservation = guard.reserve(TARGET.peer)
        guard.finish(reservation, timeout=True)
        assert guard.remaining_ns(TARGET.peer) == interval * 10**9
        clock.advance(interval * 10**9)
    guard.finish(guard.reserve(TARGET.peer))
    assert guard.remaining_ns(TARGET.peer) == 64 * 10**9


@pytest.mark.parametrize("code", [b"RATE", b"DENY", b"RSTR", b"XXXX"])
def test_control_blocks_future_invocations_without_automatic_expiry(tmp_path, code):
    clock = FakeClock()
    guard = PollGuard(clock, tmp_path)
    guard.finish(guard.reserve(TARGET.peer), control=ServerControlError(code))
    clock.advance(10_000 * 10**9)
    with pytest.raises(ServerControlError) as error:
        PollGuard(clock, tmp_path).reserve(TARGET.peer)
    assert error.value.details["cached_control"] is True
    assert error.value.reference_id == code


def test_corrupt_state_fails_closed_and_other_targets_are_independent(tmp_path):
    clock = FakeClock()
    guard = PollGuard(clock, tmp_path)
    guard.reserve(TARGET.peer)
    next(tmp_path.glob('*.json')).write_text('{broken')
    with pytest.raises(LiveStateUnavailableError):
        guard.reserve(TARGET.peer)
    assert guard.reserve(NtpPeer("192.0.2.2", 123))


@pytest.mark.parametrize("field,value", [("timeouts", True), ("next_wall_ns", -1), ("schema_version", "2")])
def test_invalid_state_is_rejected_without_relying_on_assert_statements(tmp_path, field, value):
    guard = PollGuard(FakeClock(), tmp_path)
    guard.reserve(TARGET.peer)
    path = next(tmp_path.glob('*.json'))
    state = json.loads(path.read_text())
    state[field] = value
    path.write_text(json.dumps(state))
    with pytest.raises(LiveStateUnavailableError):
        guard.reserve(TARGET.peer)


def test_backward_wall_clock_blocks_and_same_process_forward_step_does_not_shorten_wait(tmp_path):
    clock = FakeClock()
    clock.wall = 100_000_000_000
    guard = PollGuard(clock, tmp_path)
    guard.finish(guard.reserve(TARGET.peer))
    clock.wall += 1000 * 10**9
    assert guard.remaining_ns(TARGET.peer) == 64 * 10**9
    clock.wall = 0
    with pytest.raises(LiveStateUnavailableError):
        guard.reserve(TARGET.peer)


def test_mapped_ipv4_alias_cannot_bypass_same_destination_guard(tmp_path):
    clock = FakeClock()
    guard = PollGuard(clock, tmp_path)
    guard.reserve(TARGET.peer)
    with pytest.raises(RateLimitedError):
        PollGuard(clock, tmp_path).reserve(NtpPeer("::ffff:192.0.2.1", 123))


def test_unavailable_state_directory_and_lock_adapter_fail_closed(tmp_path, monkeypatch):
    import ntp_sync_lab.core.polling as polling
    path = tmp_path / 'not-a-directory'
    path.write_text('fixture')
    with pytest.raises(LiveStateUnavailableError):
        PollGuard(FakeClock(), path).reserve(TARGET.peer)
    monkeypatch.setattr(polling, 'fcntl', None)
    with pytest.raises(LiveStateUnavailableError, match='POSIX'):
        PollGuard(FakeClock(), tmp_path).reserve(TARGET.peer)


def _reserve_in_process(directory, barrier, queue):
    barrier.wait(timeout=3)
    try:
        PollGuard(SystemClock(), Path(directory)).reserve(TARGET.peer)
    except NtpSyncLabError as error:
        queue.put(error.code)
    else:
        queue.put("reserved")


def test_concurrent_processes_cannot_both_reserve_same_target(tmp_path):
    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    queue = context.Queue()
    processes = [context.Process(target=_reserve_in_process, args=(str(tmp_path), barrier, queue)) for _ in range(2)]
    for process in processes:
        process.start()
    try:
        outcomes = [queue.get(timeout=3) for _ in processes]
        assert sorted(outcomes) == ["RATE_LIMITED", "reserved"]
    finally:
        for process in processes:
            process.join(timeout=3)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
    assert all(process.exitcode == 0 for process in processes)


@pytest.mark.parametrize('outcome', ['control', 'timeout'])
def test_outcome_persistence_survives_brief_competing_state_transaction(tmp_path, outcome):
    clock = FakeClock()
    guard = PollGuard(clock, tmp_path)
    reservation = guard.reserve(TARGET.peer)
    started, finished = threading.Event(), threading.Event()
    errors = []

    def finish():
        started.set()
        try:
            guard.finish(reservation, timeout=outcome == 'timeout',
                         control=ServerControlError(b'RATE') if outcome == 'control' else None)
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    with guard._locked(guard._key(TARGET.peer)):
        worker = threading.Thread(target=finish)
        worker.start()
        assert started.wait(1)
        completed_while_locked = finished.wait(0.05)
    worker.join(timeout=1)
    assert not worker.is_alive() and not errors
    assert not completed_while_locked
    fresh = PollGuard(clock, tmp_path)
    if outcome == 'control':
        with pytest.raises(ServerControlError):
            fresh.reserve(TARGET.peer)
    else:
        assert fresh.remaining_ns(TARGET.peer) == 128_000_000_000
