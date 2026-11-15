"""Educational dispatch over validated services; live imports are command-local."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

from ntp_sync_lab.cli.formatting import error_text, format_document
from ntp_sync_lab.errors import InvalidInputError, InvalidRecordingError, NtpSyncLabError
from ntp_sync_lab.experiments.delay import (
    DELAY_PRESETS, MAX_DELAY_NS, _milliseconds_to_ns, equal_increase_sweep,
    fixed_rtt_sweep, make_delay_config, run_delay,
)
from ntp_sync_lab.experiments.replay import MAX_RECORDING_BYTES, load_recording, make_replay, validate_recording
from ntp_sync_lab.experiments.scenarios import list_scenarios, scenario_recording
from ntp_sync_lab.experiments.synchronization import make_sync_config, run_sync
from ntp_sync_lab.serialization import delay_to_contract, series_contract, sync_to_contract


class LabParser(argparse.ArgumentParser):
    def error(self, message):
        raise InvalidInputError(f'{message}; use --help for syntax and units')


def _bounded_number(name, lower, upper, *, integer=False):
    def parse(text):
        try:
            value = int(text) if integer else float(text)
            if (not integer and not math.isfinite(value)) or not lower <= value <= upper:
                raise ValueError()
            return value
        except ValueError as error:
            raise argparse.ArgumentTypeError(f'{name} must be between {lower} and {upper}') from error
    return parse


def _output_args(parser):
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    parser.add_argument('--output', type=Path, help='Additionally save complete versioned JSON')
    parser.add_argument('--overwrite', action='store_true', help='Explicitly replace an output file')


def build_parser():
    parser = LabParser(prog='ntp-sync-lab', description='NTP Sync Lab: live exchange, controlled delay, virtual correction.')
    commands = parser.add_subparsers(dest='command')
    measure = commands.add_parser('measure', help='Real UDP NTP; never changes the OS clock')
    measure.add_argument('--server', default='pool.ntp.org')
    measure.add_argument('--count', default=1, type=_bounded_number('count', 1, 10, integer=True))
    measure.add_argument('--timeout-seconds', default=3.0, type=_bounded_number('timeout', 0.1, 10))
    measure.add_argument('--interval-seconds', default=64, type=_bounded_number('interval', 64, 3600))
    measure.epilog = 'Public destinations require >=64 s spacing with persisted backoff/control blocks. DNS is outside the UDP timeout. True offset and one-way delays are unknown.'
    _output_args(measure)
    delay = commands.add_parser('delay', help='Offline model; server-minus-client offset')
    delay.add_argument('--preset', choices=tuple(DELAY_PRESETS))
    delay.add_argument('--true-offset-ms', help='Known SERVER MINUS CLIENT offset, signed decimal ms')
    delay.add_argument('--forward-ms', help='Client-to-server delay, decimal milliseconds')
    delay.add_argument('--reverse-ms', help='Server-to-client delay, decimal milliseconds')
    delay.add_argument('--processing-ms', help='Server processing, decimal milliseconds')
    delay.add_argument('--reference-unix-ns', type=int, help='Fixed reference, integer Unix nanoseconds')
    delay.add_argument('--round-trip-ms', help='Fixed-RTT sweep, 0–2000 ms; excludes individual delays')
    delay.add_argument('--sweep-points', type=_bounded_number('sweep points', 2, 200, integer=True))
    delay.add_argument('--increments-ms', nargs='+', help='Equal-increase sweep: 2–200 increasing increments')
    delay.epilog = 'Decimal milliseconds allow six fractional places. Presets exclude custom base values; sweep modes are mutually exclusive.'
    _output_args(delay)
    sync = commands.add_parser('sync', help='Offline virtual step; never OS synchronization')
    sync.add_argument('--client-offset-ms', default='120', help='Initial CLIENT MINUS REFERENCE error, signed decimal ms')
    sync.add_argument('--forward-ms', default='20')
    sync.add_argument('--reverse-ms', default='20')
    sync.add_argument('--processing-ms', default='5')
    sync.add_argument('--reference-unix-ns', type=int)
    sync.epilog = 'Only virtual time changes. Offset is a time difference; drift and slewing are not modeled.'
    _output_args(sync)
    scenarios = commands.add_parser('scenarios', help='Packaged offline catalog')
    listing = scenarios.add_subparsers(dest='action', required=True).add_parser('list')
    listing.add_argument('--format', choices=('text', 'json'), default='text')
    replay = commands.add_parser('replay', help='Validate and replay without DNS/UDP')
    selection = replay.add_mutually_exclusive_group(required=True)
    selection.add_argument('--scenario')
    selection.add_argument('--file', type=Path)
    _output_args(replay)
    return parser


@contextmanager
def _export_target(path, overwrite):
    if overwrite and path is None:
        raise InvalidInputError('--overwrite requires --output')
    if path is None:
        yield None
        return
    if not overwrite and os.path.lexists(path):
        raise FileExistsError(f'{path} exists; use --overwrite explicitly')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        def write(text):
            with temporary.open('w', encoding='utf-8') as handle:
                handle.write(text + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            if overwrite:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)  # atomic no-clobber, even if another caller creates the path
        yield write
    finally:
        temporary.unlink(missing_ok=True)


def _metadata():
    return dict(result_id=uuid4().hex, created_at_utc=datetime.now(timezone.utc))


def _prepare(args):
    if args.command == 'measure':
        from ntp_sync_lab.core.client import MeasurementConfig
        from ntp_sync_lab.experiments.measurement import run_measurements
        from ntp_sync_lab.serialization import batch_to_contract
        config = MeasurementConfig(args.server, timeout_seconds=args.timeout_seconds)
        def execute():
            print(f'LIVE: {args.count} requested attempt(s) at {args.server}; cooldown/backoff enforced.', file=sys.stderr)
            if args.count > 1:
                print('Batch may wait >=64 s between probes. Ctrl-C preserves completed attempts.', file=sys.stderr)
            batch = run_measurements(config, count=args.count, interval_seconds=args.interval_seconds)
            return batch_to_contract(batch), 130 if batch.interrupted else (3 if batch.failures else 0)
        return execute
    if args.command == 'delay':
        if args.round_trip_ms is not None:
            if any(v is not None for v in (args.preset, args.forward_ms, args.reverse_ms, args.increments_ms)):
                raise InvalidInputError('fixed-RTT mode excludes preset, individual delays, and equal-increase mode')
            from ntp_sync_lab.experiments.delay import DEFAULT_REFERENCE_UNIX_NS
            results = fixed_rtt_sweep(
                round_trip_ms=args.round_trip_ms, points=args.sweep_points or 9,
                true_offset_ms=args.true_offset_ms if args.true_offset_ms is not None else 100,
                processing_ms=args.processing_ms if args.processing_ms is not None else 5,
                reference_unix_ns=args.reference_unix_ns if args.reference_unix_ns is not None else DEFAULT_REFERENCE_UNIX_NS,
            )
            config = results[0].config
            params = {'sweep_kind': 'fixed_rtt', 'point_count': len(results),
                      'round_trip_ns': str(results[0].metrics.round_trip_delay_ns),
                      'true_offset_ns': str(config.true_offset_ns),
                      'server_processing_ns': str(config.server_processing_ns),
                      'reference_unix_ns': str(config.reference_unix_ns)}
            return lambda: (series_contract(results, params, **_metadata()), 0)
        if args.sweep_points is not None:
            raise InvalidInputError('--sweep-points requires --round-trip-ms')
        config = make_delay_config(preset=args.preset, true_offset_ms=args.true_offset_ms,
                                   forward_ms=args.forward_ms, reverse_ms=args.reverse_ms,
                                   processing_ms=args.processing_ms, reference_unix_ns=args.reference_unix_ns)
        if args.increments_ms is not None:
            results = equal_increase_sweep(config, increments_ms=args.increments_ms)
            params = {'sweep_kind': 'equal_increase', 'point_count': len(results),
                      'base': delay_to_contract(run_delay(config), **_metadata())['parameters'],
                      'increments_ns': [str(_milliseconds_to_ns('increment_ms', v, maximum_ns=MAX_DELAY_NS))
                                        for v in args.increments_ms]}
            return lambda: (series_contract(results, params, **_metadata()), 0)
        return lambda: (delay_to_contract(run_delay(config), **_metadata()), 0)
    if args.command == 'sync':
        values = dict(client_offset_ms=args.client_offset_ms, forward_ms=args.forward_ms,
                      reverse_ms=args.reverse_ms, processing_ms=args.processing_ms)
        if args.reference_unix_ns is not None:
            values['reference_unix_ns'] = args.reference_unix_ns
        config = make_sync_config(**values)
        return lambda: (sync_to_contract(run_sync(config), **_metadata()), 0)
    if args.command == 'replay':
        document = load_recording(args.file) if args.file is not None else scenario_recording(args.scenario)
        return lambda: (make_replay(document, replayed_at_utc=datetime.now(timezone.utc)), 0)
    raise InvalidInputError('select an experiment or use --help')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = '--format=json' in argv or any(
        v == '--format' and i + 1 < len(argv) and argv[i + 1] == 'json' for i, v in enumerate(argv))
    parser = build_parser()
    document = None
    try:
        args = parser.parse_args(argv)
        if args.command is None:
            parser.print_help()
            return 0
        if args.command == 'scenarios':
            entries = list_scenarios()
            if args.format == 'json':
                print(json.dumps({'schema_version': '1', 'scenarios': entries}, indent=2))
            else:
                print('Offline scenario catalog (source is original data, never a new probe)')
                for entry in entries:
                    print(f"{entry['id']:26} {entry['source'].upper():10} {entry['experiment']}\n  {entry['purpose']}")
            return 0
        execute = _prepare(args)
        with _export_target(args.output, args.overwrite) as export:
            document, code = execute()
            validate_recording(document)
            encoded = json.dumps(document, indent=2, sort_keys=True, allow_nan=False)
            if len(encoded.encode('utf-8')) + 1 > MAX_RECORDING_BYTES:
                raise InvalidRecordingError('formatted recording exceeds the 1 MiB replay limit')
            if export is not None:
                export(encoded)
                print(f'JSON recording saved to {args.output}', file=sys.stderr)
            print(encoded if args.format == 'json' else format_document(document))
        return code
    except SystemExit as error:
        return int(error.code)
    except (NtpSyncLabError, OSError, KeyboardInterrupt) as error:
        if isinstance(error, KeyboardInterrupt):
            code, name = 130, 'INTERRUPTED'
        elif isinstance(error, InvalidRecordingError):
            code, name = 4, error.code
        elif isinstance(error, OSError):
            code, name = 4, 'FILE_IO'
        else:
            code, name = 2, error.code
        payload = {'schema_version': '1', 'error': {
            'code': name, 'message': str(error) or 'Interrupted', 'details': getattr(error, 'details', {})}}
        if document is not None:
            payload['partial_result'] = document
        if json_mode:
            print(json.dumps(payload, indent=2, allow_nan=False))
        elif document is not None and isinstance(error, OSError):
            print(format_document(document))
        print(error_text(payload['error']), file=sys.stderr)
        return code
