"""CLI integration with strict offline subprocess guards or injected live services."""

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ntp_sync_lab.cli.main import main
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.errors import DnsFailureError, NtpTimeoutError
from ntp_sync_lab.experiments.measurement import run_measurements
from ntp_sync_lab.experiments.replay import load_recording
from tests.helpers import Delivery, FakeClock, FakeTransport, StaticResolver, TARGET, response_bytes

GUARDED = '''
import sys
def guard(event,args):
    if event.startswith('socket.'):
        raise AssertionError('Offline CLI attempted a network operation: '+event)
sys.addaudithook(guard)
from ntp_sync_lab.cli.main import main
code=main(sys.argv[1:])
assert 'ntp_sync_lab.core.client' not in sys.modules
assert 'ntp_sync_lab.core.transport' not in sys.modules
raise SystemExit(code)
'''


def offline(args, cwd):
    return subprocess.run([sys.executable, '-I', '-c', GUARDED, *args], cwd=cwd,
                          capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize('args', [[], ['--help'], ['measure', '--help'], ['delay', '--help'],
                                   ['sync', '--help'], ['replay', '--help'], ['scenarios', '--help']])
def test_startup_and_help_are_offline_outside_checkout(args, tmp_path):
    result = offline(args, tmp_path)
    assert result.returncode == 0 and 'usage:' in result.stdout and not result.stderr


@pytest.mark.parametrize('args,experiment', [
    (['delay', '--preset', 'symmetric-low'], 'network_delay'),
    (['delay', '--true-offset-ms', '-100', '--forward-ms', '60', '--reverse-ms', '20'], 'network_delay'),
    (['sync', '--client-offset-ms', '-120'], 'clock_sync'),
    (['sync', '--client-offset-ms', '0.000001', '--forward-ms', '0.000001', '--reverse-ms', '0'], 'clock_sync'),
])
def test_experiment_json_is_parseable_and_uses_existing_contract(args, experiment, tmp_path):
    result = offline([*args, '--format', 'json'], tmp_path)
    assert result.returncode == 0 and not result.stderr
    payload = json.loads(result.stdout)
    assert payload['source'] == 'simulation' and payload['experiment'] == experiment
    assert payload['schema_version'] == '1'


@pytest.mark.parametrize('args', [
    ['delay', '--preset', 'asymmetric-forward'], ['sync', '--forward-ms', '20', '--reverse-ms', '60'],
    ['replay', '--scenario', 'captured-public-ntp'],
])
def test_text_output_includes_every_educational_section(args, tmp_path):
    result = offline(args, tmp_path)
    assert result.returncode == 0
    for heading in ('Experiment Objective', 'Inputs & Conditions', 'Four NTP Timestamps',
                    'Calculations', 'Results', 'Assumptions & Limitations', 'Conclusion'):
        assert heading in result.stdout
    for label in ('T1 Client transmission', 'T2 Server reception', 'T3 Server transmission', 'T4 Client reception'):
        assert label in result.stdout
    assert 'UTC' in result.stdout and 'server minus client' in result.stdout
    if args[0] == 'replay':
        assert 'REPLAY (original LIVE; no request sent)' in result.stdout
        assert 'True offset: unknown' in result.stdout
        assert '2026-11-15T09:30:25.203822Z' in result.stdout


def test_sweeps_use_exact_totals_and_export_replayable_results(tmp_path):
    for args in [
        ['delay', '--round-trip-ms', '80', '--sweep-points', '9'],
        ['delay', '--preset', 'symmetric-low', '--increments-ms', '0', '60'],
    ]:
        path = tmp_path / 'sweep.json'
        result = offline([*args, '--format', 'json', '--output', str(path), '--overwrite'], tmp_path)
        assert result.returncode == 0
        payload = load_recording(path)
        assert payload == json.loads(result.stdout)
        points = payload['data']['points']
        if '--round-trip-ms' in args:
            assert len(points) == 9
            assert all(p['data']['round_trip_delay_ns'] == '80000000' for p in points)
        else:
            assert [p['data']['round_trip_delay_ns'] for p in points] == ['40000000', '160000000']
        assert offline(['replay', '--file', str(path)], tmp_path).returncode == 0


def test_text_sweep_has_one_worked_example_and_compact_complete_comparison(tmp_path):
    result = offline(['delay', '--round-trip-ms', '80', '--sweep-points', '9'], tmp_path)
    assert result.returncode == 0
    assert result.stdout.count('Experiment Objective') == 1
    assert 'Worked first point' in result.stdout and 'Sweep comparison' in result.stdout
    assert '60 | -40' in result.stdout  # first estimate and error
    assert '140 | 40' in result.stdout  # last estimate and error
    assert 'every point quartet' in result.stdout


def test_export_is_json_even_when_stdout_is_text_and_no_overwrite_is_default(tmp_path):
    path = tmp_path / 'result.json'
    first = offline(['delay', '--output', str(path)], tmp_path)
    assert first.returncode == 0 and first.stdout.startswith('SIMULATION')
    assert load_recording(path)['source'] == 'simulation'
    saved = path.read_bytes()
    second = offline(['sync', '--output', str(path), '--format', 'json'], tmp_path)
    assert second.returncode == 4 and json.loads(second.stdout)['error']['code'] == 'FILE_IO'
    assert path.read_bytes() == saved and 'Traceback' not in second.stderr
    third = offline(['sync', '--output', str(path), '--overwrite'], tmp_path)
    assert third.returncode == 0 and load_recording(path)['experiment'] == 'clock_sync'


def test_replay_of_export_preserves_original_metadata_and_exports_again(tmp_path):
    source = tmp_path / 'source.json'
    offline(['sync', '--output', str(source)], tmp_path)
    replay = tmp_path / 'replay.json'
    result = offline(['replay', '--file', str(source), '--format', 'json', '--output', str(replay)], tmp_path)
    assert result.returncode == 0
    payload = load_recording(replay)
    assert payload['source'] == 'replay'
    assert payload['recording'] == load_recording(source)
    assert payload['provenance']['original_source'] == 'simulation'
    assert offline(['replay', '--file', str(replay)], tmp_path).returncode == 0


def test_scenario_catalog_and_deterministic_scenario_replay(tmp_path):
    catalog = offline(['scenarios', 'list', '--format', 'json'], tmp_path)
    entries = json.loads(catalog.stdout)['scenarios']
    assert len(entries) == 10 and {e['source'] for e in entries} == {'live', 'simulation'}
    a = json.loads(offline(['replay', '--scenario', 'symmetric-low', '--format', 'json'], tmp_path).stdout)
    b = json.loads(offline(['replay', '--scenario', 'symmetric-low', '--format', 'json'], tmp_path).stdout)
    assert a['recording'] == b['recording']
    assert a['provenance']['original_source'] == 'simulation'


@pytest.mark.parametrize('args', [
    ['measure', '--count', '0'], ['measure', '--count', '1' * 1000],
    ['measure', '--timeout-seconds', 'nan'], ['measure', '--interval-seconds', '1'],
    ['delay', '--preset', 'symmetric-low', '--forward-ms', '20'],
    ['delay', '--round-trip-ms', '80', '--reverse-ms', '20'],
    ['delay', '--round-trip-ms', '80', '--increments-ms', '0', '20'],
    ['delay', '--sweep-points', '9'], ['delay', '--round-trip-ms', '2001'],
    ['sync', '--client-offset-ms', 'Infinity'], ['sync', '--client-offset-ms', '0.0000001'],
    ['delay', '--overwrite'], ['replay'], ['replay', '--file', 'a', '--scenario', 'b'],
    ['replay', '--scenario', 'missing'], ['scenarios'], ['unknown'],
])
def test_argument_and_validation_errors_have_stable_exit_and_json(args, tmp_path):
    result = offline([*args, '--format', 'json'], tmp_path)
    assert result.returncode == 2
    assert json.loads(result.stdout)['error']['code'] == 'INVALID_INPUT'
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('content', ['{broken', '{"schema_version":"2"}', '{"schema_version":"1","source":"live"}'])
def test_bad_recordings_use_exit_four(content, tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text(content)
    result = offline(['replay', '--file', str(path), '--format', 'json'], tmp_path)
    assert result.returncode == 4 and json.loads(result.stdout)['error']['code'] == 'INVALID_RECORDING'
    assert 'Traceback' not in result.stderr


def inject_service(monkeypatch, tmp_path, scenarios, *, interrupt=False, dns=False, blocked=False):
    import ntp_sync_lab.experiments.measurement as module
    original = run_measurements
    calls = []
    def service(config, **kwargs):
        calls.append((config, kwargs))
        clock = FakeClock()
        clock.interrupt_sleep = interrupt
        guard = PollGuard(clock, tmp_path / 'state')
        if blocked:
            guard.reserve(TARGET.peer)
        return original(replace(config, provenance_label='Injected CLI test fixture; not public NTP'),
                        clock=clock, resolver=StaticResolver(DnsFailureError('fixture DNS') if dns else TARGET),
                        transport=FakeTransport(clock, scenarios), guard=guard, **kwargs)
    monkeypatch.setattr(module, 'run_measurements', service)
    return calls


def test_measure_dispatch_uses_service_and_exports_partial_results(monkeypatch, tmp_path, capsys):
    calls = inject_service(monkeypatch, tmp_path, [[Delivery()], [NtpTimeoutError('fixture timeout')], [Delivery()]])
    path = tmp_path / 'partial.json'
    assert main(['measure', '--server', 'fixture', '--count', '3', '--format', 'json', '--output', str(path)]) == 3
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == load_recording(path)
    assert len(payload['attempts']) == 3 and payload['summary']['valid_count'] == 2
    assert payload['attempts'][1]['error']['code'] == 'NTP_TIMEOUT'
    assert 'LIVE:' in captured.err and calls[0][1]['interval_seconds'] == 64


def test_successful_measure_text_is_educational_and_explicitly_fixture_sourced(monkeypatch, tmp_path, capsys):
    inject_service(monkeypatch, tmp_path, [[Delivery()]])
    assert main(['measure', '--server', 'fixture']) == 0
    output = capsys.readouterr()
    assert 'Injected CLI test fixture; not public NTP' in output.out
    assert 'Estimated NTP offset: 100 ms' in output.out
    assert 'Network RTT: 40 ms' in output.out and 'True offset: unknown' in output.out
    assert 'T1 Client transmission' in output.out and 'Four NTP Timestamps' in output.out


def test_fractional_virtual_time_is_readable_without_rounding():
    from ntp_sync_lab.cli.formatting import timestamp
    assert '1970-01-01 00:00:00.0000000005 UTC' in timestamp('0.5')
    assert '1969-12-31 23:59:59.9999999995 UTC' in timestamp('-0.5')


def test_symlink_output_does_not_silently_overwrite_target(tmp_path):
    target = tmp_path/'original.txt'
    target.write_text('keep')
    link = tmp_path/'link.json'
    link.symlink_to(target)
    assert offline(['delay', '--output', str(link)], tmp_path).returncode == 4
    assert target.read_text() == 'keep'
    assert offline(['delay', '--output', str(link), '--overwrite'], tmp_path).returncode == 0
    assert not link.is_symlink() and target.read_text() == 'keep'


@pytest.mark.parametrize('mode,code', [('timeout', 'NTP_TIMEOUT'), ('dns', 'DNS_FAILURE'), ('blocked', 'RATE_LIMITED')])
def test_live_failures_are_actionable_and_do_not_invent_timestamps(monkeypatch, tmp_path, capsys, mode, code):
    inject_service(monkeypatch, tmp_path, [[NtpTimeoutError('fixture timeout')]], dns=mode=='dns', blocked=mode=='blocked')
    assert main(['measure', '--server', 'fixture']) == 3
    output = capsys.readouterr()
    assert code in output.out and 'No validated quartet' in output.out
    assert 'Traceback' not in output.err
    if mode == 'blocked':
        assert 'Retry after at least' in output.out


def test_interrupt_preserves_completed_attempt_and_exit_130(monkeypatch, tmp_path, capsys):
    inject_service(monkeypatch, tmp_path, [[Delivery()], [Delivery()]], interrupt=True)
    assert main(['measure', '--server', 'fixture', '--count', '2', '--format', 'json']) == 130
    payload = json.loads(capsys.readouterr().out)
    assert payload['interrupted'] and len(payload['attempts']) == 1


def test_existing_export_file_prevents_even_calling_live_service(monkeypatch, tmp_path, capsys):
    calls = inject_service(monkeypatch, tmp_path, [[Delivery()]])
    path = tmp_path / 'existing.json'
    path.write_text('keep')
    assert main(['measure', '--output', str(path), '--format', 'json']) == 4
    assert not calls and path.read_text() == 'keep'
    json.loads(capsys.readouterr().out)


def test_export_race_preserves_one_json_document_and_completed_result(monkeypatch, tmp_path, capsys):
    def conflict(*args):
        raise FileExistsError('fixture concurrent file creation')
    monkeypatch.setattr(os, 'link', conflict)
    assert main(['delay', '--output', str(tmp_path/'race.json'), '--format', 'json']) == 4
    output = json.loads(capsys.readouterr().out)
    assert output['error']['code'] == 'FILE_IO'
    assert output['partial_result']['source'] == 'simulation'


def test_text_export_failure_still_displays_completed_experiment(monkeypatch, tmp_path, capsys):
    def conflict(*args):
        raise FileExistsError('fixture concurrent file creation')
    monkeypatch.setattr(os, 'link', conflict)
    assert main(['sync', '--output', str(tmp_path/'race.json')]) == 4
    captured = capsys.readouterr()
    assert 'Final residual client error: 0 ms' in captured.out
    assert 'FILE_IO' in captured.err and 'Traceback' not in captured.err


@pytest.mark.parametrize('command', ['console', 'module'])
def test_both_installed_entry_points_find_resources_outside_checkout(command, tmp_path):
    executable = [str(Path(sys.executable).parent/'ntp-sync-lab')] if command == 'console' else [sys.executable, '-m', 'ntp_sync_lab']
    result = subprocess.run([*executable, 'replay', '--scenario', 'sync-symmetric', '--format', 'json'],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert json.loads(result.stdout)['recording']['data']['final_client_error_ns'] == '0'
