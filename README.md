# ntp-sync-lab

Interactive NTP clock synchronization lab with real-time measurements, packet visualization, and clock correction simulations.

Current scope: **Phase 1, P1.7 backend validation complete; awaiting review**.
The package provides immutable timestamp/result models, exact four-timestamp
calculations, version-1 JSON serialization, an integer NTP timestamp codec, and
pure request construction, response parsing/validation, UDP/DNS adapters, clock
capture, guarded measurements, and bounded sequential measurement batches.
The deterministic delay engine provides four presets and controlled sweeps.
The virtual clock engine applies a modeled offset estimate as an exact step.
The standalone CLI runs all three experiments and validates, exports, and replays results.
P1.7 verified 563 automated tests and 50 installed CLI acceptance checks.
Start with the [team review bundle](docs/TEAM_REVIEW.md) and
[validation report](docs/BACKEND_VALIDATION.md).
Web development requires the later team review gate.

Use Python 3.11 or later. Create a local environment and install the package with
its test dependencies (the runtime itself uses only the standard library):

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

Both entry points use the same CLI, including help:

```sh
.venv/bin/ntp-sync-lab --help
.venv/bin/python -m ntp_sync_lab --help
```

For the following examples, activate the environment first:

```sh
source .venv/bin/activate
ntp-sync-lab scenarios list
ntp-sync-lab replay --scenario captured-public-ntp
ntp-sync-lab delay --preset asymmetric-forward
python -m ntp_sync_lab sync --client-offset-ms 120 --forward-ms 60 --reverse-ms 20
```

These commands are entirely offline. The first experiment replays the genuine
P1.3 public capture with its original date and **REPLAY (original LIVE)** label;
it sends no request. Delay/synchronization examples are labeled **SIMULATION**.
The delay example estimates +120 ms from known +100 ms truth (error +20 ms).
The virtual client starts +120 ms ahead, applies the modeled estimate -100 ms,
and retains +20 ms residual. Both show why RTT and estimation error differ.

Every experiment prints objective, conditions/source, correctly owned T1–T4
timestamps, formula substitutions, results, assumptions, and conclusion. Exact
Unix-nanosecond values accompany UTC labels. Offset means **server minus client**;
`--client-offset-ms` means **client minus reference**, with the opposite sign.

An actual public measurement requires an explicit command:

```sh
ntp-sync-lab measure --server pool.ntp.org --count 1 --timeout-seconds 3
```

It uses the original safe measurement service. Startup, help, scenarios, delay,
sync, and replay never resolve or probe public servers. Do not rapidly rerun a
measurement or change polling-state paths to bypass the 64-second minimum.
An explicitly requested batch (`--count 3 --interval-seconds 64`) may take more
than two minutes, longer after timeouts; Ctrl-C preserves completed attempts.
DNS is outside the UDP timeout. The demo runbook recommends a single preflighted
live request plus offline material rather than waiting for a batch on stage.

More controlled offline comparisons:

```sh
ntp-sync-lab delay --preset symmetric-high
ntp-sync-lab delay --true-offset-ms 100 --forward-ms 20 --reverse-ms 60 --processing-ms 5
ntp-sync-lab delay --round-trip-ms 80 --sweep-points 9
ntp-sync-lab delay --preset symmetric-low --increments-ms 0 60
```

Sweeps print one worked example and a complete metric comparison table. All
point quartets remain available in JSON. Presets cannot be mixed with custom
base values; fixed-RTT mode excludes individual delays and equal-increase mode.
Use `--reference-unix-ns` for an explicit modeled epoch. Units/bounds are listed
in command help and enforced by the existing engine.

Export and replay without losing precision or provenance:

```sh
ntp-sync-lab delay --preset asymmetric-forward --format json --output artifacts/delay.json
ntp-sync-lab replay --file artifacts/delay.json
ntp-sync-lab replay --scenario symmetric-low --format json
ntp-sync-lab sync --format text --output artifacts/sync.json
```

`--format` controls stdout; `--output` always writes complete JSON. Paths refuse
overwrite unless `--overwrite` is explicitly given. Output is written atomically;
status/progress goes to stderr so JSON stdout stays parseable. If saving fails
after a result exists, text mode still displays it; JSON errors retain it as
`partial_result`. Do not repeat a public probe merely to recreate a failed export.

Replay accepts the supported schema-1 experiment, series, batch, and replay
envelopes. It validates structure/units, modeled results through the existing
engines, live raw packets/quartets, and valid-only batch summaries. Original
documents/capture dates/source labels remain unchanged inside a replay wrapper;
the wrapper adds replay time and original source. Synthetic scenario timestamps
are model/definition metadata, never network capture dates. Files are limited to
1 MiB and nesting depth 12. Invalid versions, unknown fields, duplicate JSON
keys, nonfinite values, or inconsistent calculations are rejected. Validation
establishes internal consistency, not cryptographic authenticity of a capture.

Exit codes: **0** success, **2** invalid arguments/inputs, **3** live operational
or partial-batch failure, **4** recording/file failure, **130** interruption.
Help is always human-readable. The scenario catalog supports `--format json`;
its catalog listing is not an experiment recording.

See the [demo runbook](docs/DEMO_RUNBOOK.md) and generated examples:
[recorded exchange](docs/examples/replay-public.txt),
[delay](docs/examples/delay.txt), [virtual correction](docs/examples/sync.txt),
and [replayable JSON](docs/examples/delay-asymmetric.json).

`TimestampQuad` stores integer Unix nanoseconds. `calculate_exchange` returns
server-minus-client offset as an exact `Fraction` of a nanosecond and network
round-trip delay as integer nanoseconds. Positive offset means the client is
behind the server. JSON timestamps and durations are decimal strings; unknown
live true offset and estimation error are `null`.

`encode_timestamp` / `decode_timestamp` retain raw 32-bit NTP words and use integer
nearest/ties-to-even rounding. Decoding requires an explicit reference date within
half an era (about 68 years); an exactly ambiguous midpoint is rejected, while a
wrong-era reference can silently choose a wrong date. Raw all-zero timestamps are
mathematically decodable but reserved in packets, so request construction and
required server timestamp validation reject that sentinel.

`build_request` creates a 48-byte NTPv4 mode-3 request. `parse_packet` preserves
the base header and raw timestamps; `validate_response` takes that parsed packet,
the request, numeric expected/actual peers, and locally captured T4. It checks
correlation, server status/control replies, and timing, then reuses
`calculate_exchange`. Peer/originate checks do not authenticate the sender.
Trailing bytes and non-v4/mode-4 replies are reported as unsupported. The single
P1.3 public probe successfully exercised this profile; see the
[interoperability report](docs/INTEROPERABILITY.md) and its raw evidence.

`measure_once(MeasurementConfig(server), ...)` returns a structured measurement
or a domain error. `run_measurements` supports 1–10 sequential attempts, preserving
failures and completed results on interruption. The default UDP timeout is 3 s;
system DNS is outside that deadline. T1/T4 are application-level timestamps, not
hardware packet timestamps. Significant wall/monotonic disagreement invalidates
a sample. Descriptive offset variation does not establish synchronization accuracy.

The local cooldown guard reserves each numeric destination before transmission,
uses a minimum 64 s interval from send completion, persists 128/256/.../1024 s
timeout backoff, and blocks a destination after a stratum-zero control response.
It uses a small JSON record and brief POSIX file lock, shared across processes in
`$XDG_CACHE_HOME/ntp-sync-lab/polling` or `~/.cache/ntp-sync-lab/polling`.
Initial/crashed reservations retain a conservative 74 s cooldown. State corruption
blocks live requests. Do not change/delete state to bypass cooldowns. Recovery
after a control reply requires operator review of server policy; there is no
automatic unblock command. macOS/Linux are supported by this guard; Windows fails
closed pending a lock adapter. Cross-machine coordination is outside scope, and
persisted timing assumes a stable wall clock across invocations.

Tests use independently derived fixtures, fake time/transports, and real IPv4/IPv6
loopback responders on unprivileged ports. A test audit hook blocks public DNS and
UDP; no public Internet is required. See the
[architecture](docs/ARCHITECTURE.md) and
[implementation plan](docs/IMPLEMENTATION_PLAN.md) for the approved scope,
assumptions, and review boundaries.

The P1.4 experiment is entirely offline:

```python
from ntp_sync_lab.experiments.delay import (
    fixed_rtt_sweep, make_delay_config, run_delay,
)

result = run_delay(make_delay_config(preset="asymmetric-forward"))
assert result.true_offset_ns == 100_000_000
assert result.metrics.estimated_offset_ns == 120_000_000
assert result.estimation_error_ns == 20_000_000
points = fixed_rtt_sweep(round_trip_ms="80", points=9)
assert all(p.metrics.round_trip_delay_ns == 80_000_000 for p in points)
```

`DelayConfig` uses integer nanoseconds; `make_delay_config` accepts decimal
millisecond strings, `Decimal`, or integers (no floats), with at most six
fractional places. Presets and explicit custom inputs are mutually exclusive.
`equal_increase_sweep` adds strictly increasing nonnegative increments to both
one-way delays, showing RTT growth without changing existing asymmetry bias.
All sweeps contain 2–200 points. Complete-endpoint fixed-RTT sweeps accept totals
up to 2000 ms; arbitrary pairs can total 4000 ms within the per-direction bounds.
Tiny totals can yield repeated rounded points while retaining the exact total.

Every `DelayResult` contains the modeled quartet, shared `ExchangeMetrics`, known
truth, estimation error, parameters, and assumptions. `delay_to_contract` and
`delay_to_json` serialize schema version 1 with `source="simulation"`; callers
supply `result_id` and `created_at_utc` separately from the fixed modeled epoch.
No live clock reads, random IDs, sleeps, packets, or network observations are
involved in the model; the CLI supplies export IDs and creation metadata.
The model assumes equal-rate ideal clocks, constant offset, fixed
delays/processing, and no loss, jitter, or drift. Its known truth does not imply
that a public NTP exchange reveals true offset or one-way delays.

The P1.5 virtual clock experiment reuses that same modeled measurement:

```python
from ntp_sync_lab.experiments.synchronization import make_sync_config, run_sync

result = run_sync(make_sync_config(client_offset_ms="120", forward_ms="60", reverse_ms="20"))
assert result.true_offset_ns == -120_000_000  # reference minus client
assert result.applied_correction_ns == -100_000_000  # measured estimate, not -initial error
assert result.final_client_error_ns == 20_000_000
assert result.before.reference_unix_ns == result.after.reference_unix_ns
```

`SyncConfig` uses client-minus-reference initial error (default +120 ms) and the
same bounds/decimal conversion as P1.4. `SyncResult` derives its own associated
`DelayResult`; unrelated measurements, true offsets, and corrections cannot be
injected as configuration. Snapshots preserve exact whole/half-nanosecond virtual
time. The three-point timeline contains measurement start, before correction,
and after correction. The latter two share the modeled response-reception
reference instant; sequence numbers explicitly order a possibly backward step.
No elapsed animation time, progressive slewing, or clock drift is involved.

`sync_to_contract`/`sync_to_json` use schema version 1, `experiment="clock_sync"`,
and explicit simulation provenance. Callers provide ID/creation time as for P1.4.
Outputs include the nested modeled measurement, before/after clocks, correction
event, backend-generated timeline, explanations, and assumptions. A positive
step advances virtual time; a negative step moves it backward. The exact residual
is `(forward_delay - reverse_delay)/2` under these ideal assumptions. It can be
nonzero even when initial client error was zero. Only the virtual clock changes;
the OS clock is never read or modified by this experiment. Full NTP discipline,
drift modeling, public probes, and UI implementation remain outside the virtual model.
