# NTP Sync Lab — Architecture

Status: P3.3 is approved. P3.4 automated integrated acceptance is complete (PASS), awaiting owner review. Current authorization ends at P3.4. Phase 4 has not started.

## 1. Purpose and repository findings

NTP Sync Lab is an educational application for Ohio State CSE 3461 and a public portfolio project. It demonstrates an actual NTP exchange, explains the effect of network delay, and corrects a virtual clock. The final product is one React single-page application with three experiment tabs, backed by one Python engine.

At the Phase 0 inspection, the repository contained `README.md`, a Python-oriented `.gitignore`, and an MIT `LICENSE`, with one initial commit and no application source, tests, dependency manifests, or existing documentation conventions. The working tree was clean. No on-disk `AGENTS.md` was found in the repository or its ancestor directories; the user-supplied instructions also apply. Phase 0 added the two requested planning documents. The approved P1.1 slice adds only the Python package foundation and deterministic unit tests.

Success means a technically defensible 3–4 minute demonstration following a 2–3 minute explanation, with approximately 1–2 minutes for questions. Presentation slides are a later deliverable; none are created in Phase 0.

## 2. Approved scope and implementation decisions

The project implements a small NTPv4 client exchange and educational models. It does not implement a complete NTP daemon, server-selection algorithm, frequency discipline, or authenticated time service. The protocol boundary is deliberately narrower than a production implementation.

| Ambiguity | Proposed decision | Review consequence |
| --- | --- | --- |
| Meaning and sign of “offset” | NTP offset is reference/server minus client; virtual client error is client minus reference. Name both explicitly. | Approved convention for the mathematical fixtures. |
| Is a full NTP implementation expected? | Actual mode-3/mode-4 UDP exchange, validation, and four-timestamp calculation; simplified experiments around it. | Present this scope accurately during Q&A. |
| Source for correcting a virtual clock | A modeled exchange generated from that virtual clock and a known reference. | A host's live offset must not be applied directly to an unrelated virtual clock. |
| Correction scope | One step correction is required. Progressive correction and full NTP clock discipline are outside the required implementation scope. | Any later extension requires separate scope review. |
| Public server and campus connectivity | Operator-selected server, with `pool.ntp.org` as a proposed configurable classroom default. Confirm its usage policy and UDP reachability before rehearsal. | No server availability or accuracy promise. |
| Repeated measurements versus short demo | Safe live batches outside the demo; one live request plus saved history/replay during the demo. | No rapid polling to populate a chart. |
| Numerical representation | Integer nanoseconds for decoded timestamps; exact half-nanosecond offset arithmetic; explicit decimal-string serialization. | Backend owns conversion and rounding. |
| Frontend charting | Prefer a small SVG packet diagram and Recharts for ordinary plots; confirm suitability during Phase 3. | No frontend dependencies are installed during Phase 0 or 1. |
| Deployment | Local CLI first, then local FastAPI and React. No database, cloud hosting, or multi-user service. | Revisit access controls only if scope changes. |

Architecture review approved the three experiments, shared Python engine, CLI-first approach, and mandatory team review before web development. Polling must use the smallest reliable safeguards; real-server interoperability checks belong early in P1.3, after deterministic client validation. P1.6 gives every experiment a structured educational explanation separately from machine-readable JSON. Unrelated production features are outside scope. P1.1–P1.7 and Phase 2 team review have since been approved; current authorization covers P3.4 integrated acceptance only.

## 3. Layers and dependency direction

```text
                         Python backend
CLI -----------------> experiment services <---------------- FastAPI (Phase 3)
                              |                                   ^
                     experiment models                            | HTTP/JSON
                              |                                   |
                          NTP core                         React SPA (Phase 3)
                              |
                   clock / UDP / resolver adapters

Replay files -------> validated recording loader -------> services
```

The arrows represent permitted dependencies. The NTP core and experiment engine never import the CLI, FastAPI, Pydantic, React, or charting code. The API and CLI call the same Python services and serializer. No HTTP server is needed to run or test any experiment.

Use Python 3.11 or later as the proposed minimum, with standard-library `socket`, `struct`, `time`, `dataclasses`, `fractions`, `decimal`, `argparse`, and `json`. Pytest is a development dependency. FastAPI and its server belong to an optional dependency group introduced only after the backend review gate. Choose and record exact compatible dependency versions during the phase that introduces them.

There is one Python package, not separate CLI and web engines. Services return immutable domain results; adapters handle interaction and formatting. Exceptions carry stable error codes instead of printing or becoming HTTP responses inside the core.

## 4. Proposed repository layout

Phase 0 created the two planning documents. P1.1 added the mathematical/package foundation, P1.2 the pure wire layer, P1.3 guarded measurements, P1.4 delay, P1.5 virtual correction, P1.6 educational CLI/scenario/replay integration, and P1.7 comprehensive validation and review documentation. The tree below remains the overall target layout; team review and web work remain future phases.

```text
ntp-sync-lab/
  README.md
  LICENSE
  .gitignore
  docs/
    ARCHITECTURE.md
    IMPLEMENTATION_PLAN.md
    DEMO_RUNBOOK.md                 # later rehearsal and offline procedure
  pyproject.toml                    # Phase 1 packaging, pytest, CLI entry point
  src/ntp_sync_lab/
    __init__.py
    __main__.py                     # python -m ntp_sync_lab
    models.py                       # immutable domain records and source labels
    errors.py                       # domain errors and stable codes
    serialization.py                # versioned JSON and recording validation
    diagnostics.py                  # internal single-probe compatibility check
    core/
      timestamps.py                 # wire timestamps, epochs, eras, units
      packet.py                     # base-header codec and response validation
      calculations.py               # pure four-timestamp calculations
      clock.py                      # wall/monotonic adapter and injected clocks
      transport.py                  # UDP socket and resolver adapters
      client.py                     # one validated request/response
      polling.py                    # brief per-destination state transactions
    experiments/
      measurement.py                # safe batches, cooldowns, summaries
      delay.py                      # deterministic delay/asymmetry model
      synchronization.py            # virtual clock and correction trajectory
      scenarios.py                  # named reproducible scenarios
      replay.py                     # load recordings; no networking
    cli/
      main.py                       # argparse and command dispatch
      formatting.py                 # human-readable tables and explanations
    api/                            # Phase 3 only
      app.py
      schemas.py                    # boundary validation and OpenAPI models
      routes.py                     # thin service adapters
    fixtures/                       # packaged offline resources
      scenarios/                    # synthetic inputs, labeled as such
      recordings/                   # validated real captures when available
  tests/
    unit/                           # mathematics, codec, models, serialization
    integration/                    # CLI, fake transport, local UDP server
    fixtures/                       # malformed packets and controlled test data
  frontend/                         # Phase 3 only: React + TypeScript + Vite
    package.json
    src/
      app/                          # shell, tabs, shared result state
      api/                          # generated/checked TypeScript contracts
      components/                   # packet diagram, metrics, clock comparison
      experiments/                  # real-exchange, network-delay, clock-sync
      styles/
  artifacts/                        # later user recordings; ignored by Git
```

Keep packaged scenario inputs separate from user exports. Packaging must include offline resources so an installed CLI works outside the repository. Update ignore rules only when corresponding build files or user exports are introduced in later phases.

## 5. Time conventions and mathematical contract

### 5.1 Definitions

All clocks are expressed on a UTC-like reference timeline for these experiments. Time zones affect labels only. NTP timestamp encoding is handled explicitly at the protocol boundary.

| Symbol | Meaning |
| --- | --- |
| T1 | Client clock at request transmission |
| T2 | Server clock at request reception |
| T3 | Server clock at response transmission |
| T4 | Client clock at response reception |
| θ | True server/reference clock minus client clock, assumed constant during one exchange |
| θ̂ | Estimated server-minus-client offset |
| δ | Estimated round-trip network delay, excluding server processing |
| b | Virtual client minus reference, so `b = -θ` |
| e | Offset estimation error, `e = θ̂ - θ`; known only in the model |

The authoritative backend formulas are:

```text
θ̂ = ((T2 - T1) + (T3 - T4)) / 2
δ  = (T4 - T1) - (T3 - T2)
```

A positive θ̂ means the client is estimated to be behind the server. Add θ̂ to a virtual client's displayed time to correct it. A negative estimate moves that virtual time backward. These formulas and the four event definitions follow [RFC 5905, section 8](https://www.rfc-editor.org/rfc/rfc5905.html#section-8).

Do not compare T1 against T2, or T3 against T4, to validate event ordering: those pairs come from different clocks. Only within-clock intervals are directly comparable under the constant-rate model. Display the actual local elapsed time `T4 - T1`, server processing `T3 - T2`, and δ as distinct quantities.

### 5.2 Derivation used by the delay experiment

Let `r0` be the reference time of departure, `df` the forward delay, `dr` the reverse delay, and `p` server processing time. The model sets the server equal to the reference and the client to `reference - θ`:

```text
T1 = r0 - θ
T2 = r0 + df
T3 = r0 + df + p
T4 = r0 + df + p + dr - θ

θ̂ = θ + (df - dr) / 2
δ  = df + dr
e  = (df - dr) / 2
```

This derivation is the lab's model, not an observation of actual one-way Internet delays. Larger equal delays increase δ without introducing asymmetry bias under these assumptions. Larger delay can still matter in real networks through variable queuing, scheduling, and clock instability.

For nonnegative one-way delays and ideal clocks, asymmetry alone gives `|e| ≤ δ/2`. This is a conditional model bound, not a confidence interval or a guarantee of live UTC accuracy.

### 5.3 Representation and precision

The wire timestamp uses 32-bit seconds and a 32-bit fraction, with a 1900 epoch; the Unix epoch difference is 2,208,988,800 seconds. Keep the raw words and unfold the era using a nearby reference date before converting to integer Unix nanoseconds. The era assumption requires a local date within approximately 68 years of the server; explicitly test the 2036 rollover. [RFC 5905, section 6](https://www.rfc-editor.org/rfc/rfc5905.html#section-6) defines the timestamp representation and era arithmetic.

Proposed arithmetic rules:

1. Encode and decode using integer arithmetic, with a documented nearest-nanosecond, ties-to-even conversion where needed. Never subtract floating-point epoch seconds.
2. Preserve request transmit bytes for exact originate matching. Use the decoded value of the sent T1 in the calculation; preserve the pre-encoding local sample in diagnostics if useful.
3. Calculate offset using `Fraction` in nanosecond units, preserving a possible half nanosecond. Delay and decoded timestamps are integer nanoseconds. Wire quantization and nanosecond conversion do not imply nanosecond accuracy.
4. Serialize absolute timestamps as decimal integer strings. Serialize nanosecond durations and offsets as decimal strings, allowing `.5` for offsets. This avoids JavaScript's unsafe integer range for epoch nanoseconds.
5. Use UTC ISO-8601 strings for readable absolute time and explicitly labeled milliseconds for classroom metrics. Chart coordinates may use relative milliseconds after conversion; they never become authoritative results.
6. Obtain wall time with `time.time_ns()` and elapsed time with `time.monotonic_ns()`. Monotonic readings have no UTC epoch and cannot substitute directly for T1/T4. See [Python's time documentation](https://docs.python.org/3/library/time.html#time.time_ns).

P1.2 implements `NtpTimestamp(seconds, fraction)` in `core/timestamps.py` with immutable raw words and exact byte conversion. `encode_timestamp` rounds to the nearest 2^-32-second tick; `decode_timestamp` rounds to the nearest integer nanosecond, both ties to even. `unfold_timestamp` returns extended integer ticks to check server event ordering before rounding. Era selection uses the nearest date to the supplied integer Unix-nanosecond reference, including across 2036-02-07 06:28:16 UTC; it rejects an exactly equidistant era reference. The reference must be strictly less than 2^31 seconds from the actual timestamp. A wrong reference can silently choose the wrong era. Encoding then decoding integer nanoseconds with the correct reference recovers the input exactly; arbitrary raw timestamps lose up to 0.5 ns on decode. This representation is not a measurement-accuracy claim.

The codec can mathematically decode raw zero in any inferred era, but packet timestamps use all-zero words as an unspecified sentinel. `build_request` rejects an input T1 that encodes to zero, including the exact era boundary; it does not fabricate a substitute timestamp. Normal responses require nonzero raw T2/T3. Nonzero raw words that happen to round to an integer boundary remain usable.

Offset is a time difference; drift is a rate difference, typically expressed in ppm. Drift is zero in the required model. Do not infer oscillator drift from a short noisy series of offsets.

## 6. NTP core and measurement policy

### 6.1 Responsibilities and interfaces

| Module | Responsibility / proposed stable interface |
| --- | --- |
| `timestamps` | `encode_timestamp(unix_ns)`, `decode_timestamp(words, era_reference_ns)`; conversions and raw timestamp identity |
| `packet` | Build request, parse base header, validate response against request context; no socket access |
| `calculations` | `calculate_exchange(TimestampQuad) -> ExchangeMetrics`; no I/O or source-specific rules |
| `clock` | Injected `ClockSource.wall_time_ns()` and `.monotonic_ns()`; controlled tests and local clock metadata |
| `transport` | Resolve one address and exchange a datagram against a deadline; injectable socket/resolver behavior |
| `client` | `measure_once(MeasurementConfig, dependencies) -> MeasurementResult`; capture timestamps, validate, calculate |
| `measurement` | `run_measurements(BatchConfig, dependencies) -> MeasurementBatch`; cooldown, ordered attempts, summary |
| `delay` | `run_delay(DelayConfig) -> DelayResult`; create timestamps and reuse the core calculation |
| `synchronization` | `run_sync(SyncConfig) -> SyncResult`; obtain modeled estimate and apply virtual correction |
| `scenarios` / `replay` | List deterministic presets; validate/load recorded results with explicit provenance |
| `serialization` | `to_contract` and experiment/series serializers; versioned framework-independent contracts. `experiments/replay.py` owns `load_recording` and validation. |

Dependencies are passed as simple interfaces/callables; do not build a plugin framework or generic dependency-injection container.

### 6.2 Wire exchange and response validation

Send a unicast v4 client request to destination UDP 123, using an OS-assigned ephemeral source port. Client source-port randomization is recommended by [RFC 9109](https://www.rfc-editor.org/rfc/rfc9109.html#section-4); this application does not bind privileged local port 123 or require administrator rights.

For the proposed limited profile, use a 48-byte base header. Response acceptance requires mode 4, version 4, matching resolved peer/port and originate bytes, usable receive/transmit timestamps, synchronized leap status, and stratum 1–15. Stratum 0 is a control response handled before normal timestamp checks. Return its diagnostic code and stop polling that target. Base-header validation and Kiss-o'-Death semantics derive from [RFC 5905, sections 7–8](https://www.rfc-editor.org/rfc/rfc5905.html#section-7).

Implementation policy for this lab:

- Reject short packets as malformed and longer packets as outside the supported base-header profile, with distinct errors. Do not infer that an unparsed trailer is definitely authentication or a valid extension. Report version, mode, packet length, and the unsupported reason accurately. Evaluate real-server compatibility during P1.3 immediately after the first functioning UDP client exists; expand support only with explicit tests and scope review.
- Reject unsupported versions and unusable server status. Preserve diagnostics without presenting an invalid response as a successful measurement.
- Require `T3 ≥ T2`, nonnegative local elapsed time, and nonnegative calculated δ. Preserve rejected raw values for diagnosis; do not silently clamp them to make a plausible graph.
- Use a connected UDP socket or equivalent explicit peer check. A late/mismatched reply is ignored until the original deadline; ignored datagrams never reset it or cause another transmission. Bound receive sizes.
- Match the raw originate timestamp, not a rounded formatted timestamp. Stratum alone is not a certificate of accuracy, and source/originate checks do not authenticate UDP.
- No MAC, NTS, broadcast, control/monitoring queries, or leap-second/smear correction is implemented. Record leap metadata; exclude an exchange crossing a known leap event from the classroom accuracy discussion.

P1.2's pure interfaces are `build_request(t1_unix_ns) -> ClientRequest`, `parse_packet(data) -> NtpPacket`, and `validate_response(response, request, *, expected_peer, actual_peer, t4_unix_ns) -> ValidatedResponse`. Request context preserves the original T1 sample and exact sent bytes; its calculation T1 is decoded from those bytes. Requests declare poll exponent 6 and conservative precision exponent 0; neither field enforces polling or measures local resolution. Parsed metadata includes signed poll/precision exponents, signed 16.16 root delay, unsigned 16.16 root dispersion, raw reference ID, and all four header timestamps. Root metadata exposes exact fractional nanoseconds.

`NtpPeer` accepts numeric IPv4/IPv6 addresses, ports, and an explicit IPv6 scope ID, without DNS. The future transport converts its socket address to this value; peer/originate checks establish correlation only. Validation checks peer, v4/mode 4, and exact originate bytes before stratum-zero handling. `ServerControlError` retains raw reference ID, any printable kiss code (including unknown codes), and `stop_polling=True`, even when LI is 3 or T2/T3 are zero. Stratum 16 or LI=3 is unsynchronized; reserved strata 17–255 are malformed. Raw T3/T2 ordering is checked before integer-nanosecond calculations. The returned quartet and metrics use the unchanged P1.1 calculation contract. Clock capture/resolution and wall/monotonic diagnostics belong to P1.3, not this pure protocol layer.

T1 is sampled immediately before packing/sending; T4 immediately after receiving and before decoding. These are software timestamps at the application boundary, including local scheduling uncertainty. The animation cannot claim kernel or wire capture precision. Server T2 and T3 are reported by the server, not measured independently by this client.

Capture nearby monotonic samples as well. P1.3 brackets each wall sample with monotonic reads, using their midpoint and recording the read span. If wall-clock and monotonic elapsed times differ by more than the configured threshold (default 5 ms) plus both read spans, invalidate the sample as `LOCAL_CLOCK_DISCONTINUITY`. Record the discrepancy and clock resolution. Smaller changes, changes hidden by sampling uncertainty, and continuous OS slewing may remain undetected; this guard does not establish an accuracy bound.

P1.3 implements `SystemResolver`, `UdpTransport`, `SystemClock`, and `measure_once(MeasurementConfig, ...)`. The resolver chooses one numeric destination at UDP 123, preferring IPv4; explicit IPv6 addresses and scoped IPv6 are supported. It does not retry other returned addresses. Socket creation and policy reservation precede T1; packing and system-call overhead remain part of software timing. Immediately after the raw receive wrapper returns, capture T4 before peer normalization/decoding. Use one monotonic deadline through all receives, reject a late captured response, and ignore wrong-peer/originate datagrams without retransmission or deadline extension. Retain a total ignored count and at most 20 diagnostic entries. Sockets close on success, failure, and interruption. `local_peer` records the local binding; an unconnected socket can report a wildcard address rather than the selected outbound interface.

### 6.3 Safe polling, availability, and errors

Proposed defaults are one request, 3 s UDP timeout, no immediate retry, and a 64 s minimum spacing between sends to a public target. A live batch accepts 1–10 attempts, sequentially, with interval at least 64 s. A timeout counts as an attempt. Each request uses one resolved destination; do not spray addresses or perform bursts. Honor any stricter operator policy. NTP Pool explicitly discourages aggressive burst/minpoll behavior in its [usage guidance](https://www.ntppool.org/en/use.html).

P1.3 explicitly requires both cross-invocation protection and concurrent local callers, making in-memory state alone insufficient. `PollGuard` uses one small JSON record and one POSIX lock file per canonical numeric destination (IP/port/scope), with brief `flock` transactions and atomic JSON replacement. Reservations and cooldown reads are nonblocking; P1.7 corrects outcome persistence to wait for a competing state transaction, so a timeout backoff or control block is not lost to brief contention. That local filesystem wait has no hard deadline. IPv4-mapped aliases share the IPv4 key. Default state is under `$XDG_CACHE_HOME/ntp-sync-lab/polling` when absolute, otherwise `~/.cache/ntp-sync-lab/polling`; all local entry points use it. Persist last-send time, next-allowed time, capped timeout count, control code, and reservation token. No lock is held while waiting on UDP or between batch attempts. A simultaneous reservation fails visibly. This is the minimum persistent mechanism selected to satisfy the new requirements, not a general scheduler, lock service, or database.

Reserve before sending, initially blocking 74 s to cover the maximum 10 s send deadline if the process dies. On completion, anchor the normal minimum 64 s interval to a clock sample immediately after the send returned. Corrupt/unavailable state blocks live requests. State updates are mandatory; a failure to persist an outcome stops the batch. Local monotonic state also prevents a forward wall step from shortening an existing guard instance's wait. Across fresh invocations, persisted cooldowns use wall time: backward steps fail closed; sufficiently large forward steps can shorten the protection. This limitation assumes ordinary stable host time and is explicitly outside a production discipline/boot-state framework. Do not change cache paths, delete records, or run independent users/machines to bypass policy. Coordination covers cooperating processes sharing one cache directory, not different machines or users. The POSIX lock adapter supports macOS/Linux; live operations fail closed on platforms without it, including Windows.

On a timeout, require at least 128 s from send completion, then 256 s, 512 s, and a cap of 1,024 s. The batch also respects a longer requested interval (accepted range 64–3,600 s). A subsequent non-timeout outcome resets the timeout count; successful probes retain the normal 64 s floor. Backoff and stratum-zero control blocks survive restarts. A stratum-zero response stops the batch and blocks the target until an operator reviews server policy and deliberately repairs/resets that destination's state; there is no automatic expiry or reset CLI. [RFC 4330, sections 8–9](https://www.rfc-editor.org/rfc/rfc4330.html#section-8) provides historical simple-client guidance; RFC 5905 remains the protocol reference.

`run_measurements` resolves once and records 1–10 sequential attempts. A single call never retries a packet; a batch explicitly requests additional probes. Before subsequent probes, sleep using the injected clock until both the requested spacing and shared cooldown/backoff permit it. Initial cooldown or later reservation contention stops visibly. DNS failure stops with one failed attempt; control/state failures stop with partial results; ordinary timeout/network/protocol failures remain individual attempts. Keyboard interruption retains completed attempts. Summary fields are median offset, minimum RTT, and offset range over valid results only; no valid samples means a null summary. A median of two half-nanosecond offsets can be a quarter nanosecond, which JSON preserves exactly. These statistics are descriptive, not an NTP filter, jitter estimate, or accuracy bound.

The default 3 s monotonic UDP deadline begins at reservation, after resolution and socket creation, and includes final setup/send/receive work; configurable bounds are 0.1–10 s. System DNS is outside that deadline and may take longer. Distinguish lookup failure from UDP timeout and network failure. Numeric addresses can be used for a preflighted session; a hard DNS deadline remains a future reviewable addition, not a current guarantee.

Stable errors include `INVALID_INPUT`, `DNS_FAILURE`, `NTP_TIMEOUT`, `NETWORK_UNREACHABLE`, `MALFORMED_PACKET`, `UNSUPPORTED_RESPONSE`, `PEER_MISMATCH`, `ORIGIN_MISMATCH` (diagnostic if only mismatches arrive), `SERVER_UNSYNCHRONIZED`, `SERVER_CONTROL`, `LOCAL_CLOCK_DISCONTINUITY`, `INVALID_TIMING`, `RATE_LIMITED`, `LIVE_STATE_UNAVAILABLE`, and `INVALID_RECORDING`. Every live failure retains target and attempt context. A failure does not automatically become a successful simulation or replay.

## 7. Experiment workflows

### 7.1 Tab 1: Real NTP Exchange — observe and estimate

Objective: observe meaningful UDP networking and explain why four timestamps are needed.

1. Select a configured server and request one measurement. Show a waiting state, timeout, or remaining cooldown honestly.
2. Resolve, send, capture T1/T4, validate the returned T2/T3 and metadata, then calculate θ̂ and δ.
3. Display timestamp values, server identity/stratum, offset, network round-trip delay, processing time, and sample status. Live true offset and estimation error are unknown, represented as `null`.
4. Offer an explanatory playback using the recorded result. Draw two clock lanes and two packet arrows with T1–T4 labels. A persistent caption says “Recorded exchange playback; animation timing is illustrative.”
5. Expand the formulas with that sample's substitutions. Permit repeated measurements subject to cooldown and a bounded in-memory history, or load an explicit saved recording.

Never infer actual forward/reverse delay from the four live timestamps without knowing true clock offset. The diagram must not draw `(T2 - T1)` as a measured one-way transit duration: it also contains clock offset. Server processing and client elapsed time can be labeled from their within-clock differences. Cross-clock lane placement is schematic.

Conclusion: one exchange estimates relative time using four timestamps; software timing, server quality, and unknown path asymmetry limit the result. Repeated values show variation, not a measured truth or certified uncertainty. A batch may report median offset, minimum δ, and offset range, labeled as descriptive statistics rather than the full NTP clock filter or RFC jitter.

### 7.2 Tab 2: Network Delay & Synchronization Accuracy — control the cause

Objective: distinguish clock offset, offset estimate, and estimation error.

Inputs are true server-minus-client offset (default +100 ms), forward delay, reverse delay, and optional server processing time. Use a fixed reference epoch. Delays are nonnegative, all clock rates are equal, offset is constant, there is no loss or random jitter, and processing is known. The engine produces all four timestamps and invokes the same calculation as Tab 1; no socket or artificial sleep is involved.

Required preset comparisons, with θ = +100 ms and p = 5 ms:

| Scenario | Forward | Reverse | δ | θ̂ | e |
| --- | --- | --- | --- | --- | --- |
| `symmetric-low` | 20 ms | 20 ms | 40 ms | +100 ms | 0 ms |
| `symmetric-high` | 80 ms | 80 ms | 160 ms | +100 ms | 0 ms |
| `asymmetric-forward` | 60 ms | 20 ms | 80 ms | +120 ms | +20 ms |
| `asymmetric-reverse` | 20 ms | 60 ms | 80 ms | +80 ms | -20 ms |

For the first scenario, relative timestamps are `T1=-100`, `T2=20`, `T3=25`, `T4=-55` ms, giving client elapsed 45 ms, processing 5 ms, δ=40 ms, and θ̂=+100 ms. The displayed absolute times add the fixed epoch.

Provide a comparison chart and optional deterministic sweep returned by the backend. A sweep at fixed `df+dr` changes asymmetry while holding round-trip delay constant. A second comparison raises both delays equally. All chart points and their metrics are calculated in Python; the browser only formats and renders them.

Conclusion: symmetric delay cancels from the offset estimate in the ideal model; asymmetry biases it by half the delay difference. The known true offset exists because this is a simulation.

P1.4 implements immutable `DelayConfig`/`DelayResult`, the four-entry `DELAY_PRESETS` registry, and `run_delay` in `experiments/delay.py`. It generates the documented quartet and calls the unchanged `calculate_exchange`; estimation error is the returned estimate minus known model truth. No live-network code is imported. The default modeled reference is the fixed integer Unix nanosecond value `1700000000000000000`; a caller may supply any integer reference without changing the metrics.

`make_delay_config` validates decimal millisecond strings, `Decimal`, or integers against the approved bounds, rejecting floats, nonfinite values, and more than six fractional places (including trailing zero places). Conversion uses exact integer ratios and is independent of Decimal context precision. An explicit preset conflicts with every explicit custom field. Native nanosecond configurations enforce the same bounds.

`fixed_rtt_sweep` returns 2–200 ordered `DelayResult` points from all-reverse to all-forward. Forward delay is rounded once to integer nanoseconds using ties to even; reverse is the requested total minus forward. Because both complete endpoints must satisfy the 2000 ms one-way limit, the sweep total is 0–2000 ms; arbitrary individual-delay configurations can still total 4000 ms. Tiny totals may repeat points without changing the total. `equal_increase_sweep` accepts 2–200 strictly increasing nonnegative increments and adds each to both delays, preserving their difference; all resulting delays must satisfy the original bounds. It rejects rather than clips invalid requests. Fixed-total sweeps have a separate typed interface from presets/individual delays, so conflicting arguments cannot be silently ignored.

`delay_to_contract`/`delay_to_json` reuse schema version 1 with simulation provenance, model version, normalized nanosecond parameters, quartet, known truth, error, assumptions, and conclusion. Callers explicitly supply result ID and creation time, separately from the model reference. Pure execution/serialization therefore reads no clock, creates no random identity, and reproduces identical output for identical inputs and metadata. Sweep results are tuples of these same reusable domain results; serialization can assign explicit point IDs. No correction engine, charts, API, or CLI commands are added by P1.4.

### 7.3 Tab 3: Clock Synchronization — correct and inspect residual error

Objective: show how an offset estimate changes a virtual clock, including an imperfect correction.

1. Configure initial virtual client error `b` (default +120 ms, meaning ahead of reference) and modeled delays. Show reference and virtual clocks at a common reference instant.
2. Generate an exchange with true NTP offset `θ=-b`. Reuse `run_delay` and the core formulas. The browser does not supply a correction computed from the visible clock labels.
3. Freeze the modeled offset during this exchange and apply a step `correction = θ̂` to virtual time only.
4. Return a timeline, before/after client error, true and estimated NTP offset, correction applied, and residual. Use common reference instants so elapsed animation time cannot be mistaken for improvement.
5. Reset to the same inputs and compare symmetric and asymmetric measurement conditions.

The invariant is:

```text
b_after = b_before + θ̂ = (df - dr) / 2
```

With b=+120 ms and 20/20 ms delays, θ̂=-120 ms and b_after=0. With 60/20 ms delays, θ̂=-100 ms and b_after=+20 ms. A client starting behind reference receives a positive correction. This connects Tab 2's estimation error directly to Tab 3's residual error.

The required model has equal clock rates and no drift, loss, jitter, or operating-system intervention. Its reference is ideal within the model; an animated reference anchored to local time is not an independent UTC authority. Never call OS time-setting APIs, shell commands that change time, or privileged services.

Progressive correction, oscillator drift estimation, and full NTP clock discipline are outside the required implementation scope. Implement only the clearly labeled step model. Any later extension needs separate review of its mathematics, clock-rate constraints, and educational value.

P1.5 implements `SyncConfig`, `VirtualClock`, `ClockSnapshot`, `CorrectionEvent`, `SyncTimelinePoint`, `SyncResult`, and `run_sync` in `experiments/synchronization.py`. Its immutable result derives the associated `DelayResult` once through `run_delay` using `true_offset_ns=-initial_client_error_ns`; callers cannot supply an unrelated measurement or an independent correction. Applied correction is exactly that measurement's estimated offset. Native inputs remain integer nanoseconds with the approved bounds; `make_sync_config` reuses P1.4's exact decimal conversion. Corrected virtual times and residuals additionally retain half nanoseconds as `Fraction` values. No host-clock, network, or sleep adapters are imported.

The correction reference instant is modeled T4 minus the uncorrected client error: it is the response-reception event on the ideal reference timeline. Before/after snapshots share that exact instant. The backend timeline contains logical sequence 0 (`measurement_start` at r0), 1 (`before_correction` at reception), and 2 (`after_correction` at the same reception instant). Duplicate reference coordinates are deliberate; a negative correction can move virtual time backward. Zero-duration exchanges still contain all three ordered phases. Snapshot/event models reject mismatched reference instants, inconsistent correction values, unsupported precision, and invalid phase ordering. Timeline fields are derived from the immutable model, not accepted independently from callers.

`sync_to_contract`/`sync_to_json` add the planned `clock_sync` discriminator to schema version 1. The envelope includes T1–T4 and shared metrics, initial error, true offset, correction, residual, nested simulated measurement, before/after snapshots, a step event referencing timeline sequences 1/2, backend-generated clock pairs, explanations, and assumptions. All nanosecond values serialize as exact decimal strings, including fractional absolute virtual timestamps. IDs and creation time are explicitly supplied as in P1.4. These results demonstrate offset correction rather than oscillator drift or OS synchronization. With b=+120 ms and 20/60 ms delays, correction=-140 ms and residual=-20 ms; a zero-error client can gain error from a biased measurement. Residual and estimation error are separately named even though they coincide under this model.

## 8. Shared models and recording contract

Use frozen dataclasses for domain objects. Proposed principal types are `NtpTimestamp`, `TimestampQuad`, `ExchangeMetrics`, `MeasurementConfig`, `MeasurementResult`, `MeasurementAttempt`, `MeasurementBatch`, `DelayConfig`, `DelayResult`, `SyncConfig`, `SyncResult`, and `Recording`. Tests and adapters depend on these semantics rather than a UI framework.

The P1.1 foundation implements `TimestampQuad`, `ExchangeMetrics`, and an `ExchangeResult` envelope input only. `ExchangeResult` holds immutable caller-supplied metadata, source, timestamps, assumptions, and optional known model truth. Its serializer derives metrics through `calculate_exchange`, preventing supplied result fields from contradicting timestamps. It emits the version-1 envelope with empty parameters/warnings and description-only provenance; complete live diagnostics, replay support, experiment-specific fields, and recording validation remain future work. Sources currently supported by this foundation are `live` and `simulation`; replay is added with its loader in P1.6. No clock is read during calculation or serialization.

The serialized schema is versioned from the first implementation. Every successful single-experiment envelope contains:

| Field | Contract |
| --- | --- |
| `schema_version` | String `"1"`; unsupported versions are rejected explicitly |
| `experiment` | `real_exchange`, `network_delay`, or `clock_sync` |
| `source` | `live`, `simulation`, or `replay` |
| `result_id` | Identifier referenced by the current UI/history; not a database key |
| `created_at_utc` | Result creation time, separate from modeled event times |
| `provenance` | Live target/capture metadata, or scenario/model version; replay preserves original source and capture date and adds replay time |
| `parameters` | Validated, normalized input values and units |
| `data` | Experiment-specific payload described below |
| `warnings` | Stable code and human-readable explanation; never a substitute for invalidation |
| `assumptions` | Explicit model assumptions or measurement limitations |

`real_exchange.data` contains the quartet, raw timestamp words, `estimated_offset_ns`, `round_trip_delay_ns`, `client_elapsed_ns`, `server_processing_ns`, peer identity, header metadata, local clock diagnostics, and `true_offset_ns: null`, `estimation_error_ns: null`. A batch contains ordered attempts, including failures, and a summary computed only from valid samples. Zero valid samples means no numeric summary; partial failure remains visible.

`network_delay.data` contains the same quartet and metrics, known `true_offset_ns`, `estimation_error_ns`, and configured one-way delays. It may additionally contain bounded comparison/sweep results. `clock_sync.data` contains its modeled measurement, `initial_client_error_ns`, `applied_correction_ns`, `final_client_error_ns`, and a backend-generated series of reference and virtual time pairs. Each timestamp is a string; each duration/offset field carries its unit in the name.

A measurement payload fragment illustrating types, not a complete recording:

```json
{
  "timestamps": {
    "t1_unix_ns": "1794693600000000000",
    "t2_unix_ns": "1794693600105000000",
    "t3_unix_ns": "1794693600106000000",
    "t4_unix_ns": "1794693600011000000"
  },
  "estimated_offset_ns": "100000000",
  "round_trip_delay_ns": "10000000",
  "true_offset_ns": null,
  "estimation_error_ns": null
}
```

Errors use `{"schema_version":"1","error":{"code":"NTP_TIMEOUT","message":"...","details":{...}}}`. Include `retry_after_seconds` where meaningful. Inputs and JSON never contain NaN or Infinity. Do not encode unknown live truth as zero.

Accept decimal millisecond inputs at user boundaries and convert once using `Decimal`. Proposed bounds: offsets ±60,000 ms; each one-way delay 0–2,000 ms; server processing 0–500 ms; at most six decimal places in millisecond inputs; at most 200 sweep points. Reject out-of-range values rather than silently clipping. Live timeout is configurable from 0.1–10 s. Limits protect responsiveness and keep chart values explainable; they are product choices, not protocol limits.

Live recordings retain raw packet bytes (hex), local timestamps, target, UTC capture date, schema version, validated results, and limitations. Synthetic recordings retain modeled timestamps, scenario parameters, model version, and results, with no invented network capture metadata. Loading checks types, size, source, and formula consistency against stored timestamps. A recording made from synthetic fixtures remains synthetic. Replay changes only presentation provenance: it must not refresh the original capture date or imply a new UDP request. Loading fixtures performs zero network I/O. Include a real recording in the packaged resources only after an actual validated measurement; until then, ship labeled synthetic scenarios rather than an invented “live” capture. No database is needed.

P1.6 uses native schema-1 result, delay-series, and measurement-batch variants. The original P1.3 batch is validated and packaged byte-for-byte, without inventing missing top-level result IDs/dates. Series use `parameters.sweep_kind`, bounded point counts and normalized unit-bearing parameters, with complete native point envelopes under `data.points`. Replay uses a separate wrapper: `schema_version`, `experiment`, `source="replay"`, `provenance={original_source,replayed_at_utc,description}`, and `recording` containing the entire unchanged original document. The original source/date remains inside that document; another replay can wrap it again without refreshing a capture date. `ResultSource` continues to describe domain measurement origins; replay presentation is a recording wrapper rather than a relabeled `ExchangeResult`.

`experiments/replay.py` accepts UTF-8 JSON up to 1 MiB with nesting depth at most 12, rejects duplicate keys/nonfinite numbers, and validates known shapes/units. Simulations and sweeps are reconstructed through their existing engines and compared exactly, including metadata/assumptions/clock timelines. Live packets are parsed and validated through the existing pure wire layer, with quartet/metrics, header/raw words, clock diagnostics, and capture-date consistency checks. Batch summaries are checked against valid samples only. Unknown versions/model fields are rejected rather than guessed. This establishes internal consistency, not cryptographic authenticity or proof that a user-supplied capture actually occurred.

P1.7 reapplies the live wall/monotonic interval guard during replay. New live exports include the positive decimal-string `parameters.discontinuity_threshold_ns`; this is an optional additive schema-1 field. For legacy captures without it, the loader assumes the original documented 5,000,000 ns default, without inserting metadata or modifying the recording. A custom legacy threshold cannot be recovered. Older strict loaders may reject new exports containing the field; use the P1.7 loader. The original P1.3 evidence and packaged copy remain byte-identical.

`experiments/scenarios.py` loads the packaged `fixtures/scenarios/catalog.json` via `importlib.resources`. The ten entries cover four delay presets, five virtual-clock cases, and the archived genuine exchange. Synthetic definitions have fixed definition/creation metadata for reproducibility. Public capture metadata is never reused to label synthetic data. Package-data rules include both JSON resource directories in wheels; offline commands need neither checkout paths nor live modules.

## 9. Standalone CLI

P1.6 implements the existing console script `ntp-sync-lab` and equivalent `python -m ntp_sync_lab` through one `argparse` dispatcher. The commands below are now available. Root startup and help perform no measurements; live service imports/calls occur only for an explicit `measure` command.

```text
ntp-sync-lab measure --server pool.ntp.org --count 1 --timeout-seconds 3
ntp-sync-lab measure --server pool.ntp.org --count 3 --interval-seconds 64 --format json --output artifacts/live.json
ntp-sync-lab delay --preset symmetric-low
ntp-sync-lab delay --true-offset-ms 100 --forward-ms 60 --reverse-ms 20 --processing-ms 5 --format json
ntp-sync-lab delay --true-offset-ms 100 --round-trip-ms 80 --sweep-points 9 --format json
ntp-sync-lab sync --client-offset-ms 120 --forward-ms 20 --reverse-ms 20
ntp-sync-lab sync --client-offset-ms 120 --forward-ms 60 --reverse-ms 20 --format json
ntp-sync-lab scenarios list
ntp-sync-lab replay --file artifacts/live.json
ntp-sync-lab replay --scenario symmetric-low --format json
```

`--client-offset-ms` means b, client minus reference; `--true-offset-ms` means θ, server minus client. CLI help must spell out the difference. With no flags, `delay` uses `symmetric-low` and `sync` uses the stated defaults. An explicit preset and explicit numeric overrides are mutually exclusive. Fixed-round-trip sweep and individual-delay inputs are also mutually exclusive; require 2–200 points, include endpoints from all-reverse to all-forward, and return results in that order. Round each forward-delay point once to integer nanoseconds and set reverse delay to the requested total minus that point, preserving fixed total delay exactly. Scenario replay executes stored deterministic inputs and labels the result `replay` with original source `simulation`.

Every experiment supports `--format text|json` for stdout and optional `--output PATH` to additionally save a machine-readable JSON recording, independently of the stdout format. JSON is one complete versioned document, including batch attempts, suitable for replay. Status/progress goes to stderr; stdout remains parseable when JSON is selected. Saving refuses existing files unless `--overwrite` is explicitly supplied; without `--output`, no recording file is written. Exported recordings use the full envelope, not the illustrative fragment above. `scenarios list` identifies source and purpose.

Every experiment command produces objective, conditions/source, T1–T4/clock ownership, formula substitutions/units, results, assumptions/limitations, and conclusion. UTC labels accompany exact Unix nanoseconds, including fractional virtual time. Synchronization includes common-instant snapshots and correction/residual. Failed attempts mark unavailable observations instead of inventing values. Fixed-total and `--increments-ms` equal-increase sweeps show one worked point and a complete comparison table; every point quartet is preserved in JSON. Machine-readable output is separate. The live service/polling code and authoritative calculations remain unchanged.

Options follow their command. `scenarios list` supports text or JSON catalog output (a catalog is not a recording); all experiment/replay commands support `--format`, `--output`, and explicit `--overwrite`. Output destinations are checked before live execution. A temporary file plus atomic no-clobber link/replace preserves existing files on errors. If saving fails after execution, text still displays the completed result and JSON errors include `partial_result`; do not re-probe to repair an export. Status/progress goes to stderr. Initial argument/validation errors use the same stable error envelope when JSON is selected. Help is always human-readable.

Exit codes: 0 for a successful experiment/all requested live attempts valid; 2 for invalid usage/input; 3 for a live run containing an operational failure (with any successful attempts retained); 4 for invalid/unsupported recording or file I/O; 130 for interruption. Interrupting a batch retains completed attempts in its structured output and closes sockets. A timeout or malformed reply prints an actionable explanation without a traceback in normal operation.

## 10. FastAPI boundary (P3.1)

Phase 2 approval has been reported. P3.1 implements the following endpoints; FastAPI and Uvicorn remain optional `web` dependencies:

| Endpoint | Input | Output / behavior |
| --- | --- | --- |
| `GET /api/v1/health` | None | Local application status; never contacts NTP |
| `GET /api/v1/config` | None | Server identifiers, bounds, units, schema version, cooldown state |
| `GET /api/v1/scenarios` | None | Packaged scenarios with descriptions and provenance |
| `POST /api/v1/measurements` | `{server_id, timeout_seconds}` | One validated live exchange; one datagram maximum |
| `POST /api/v1/experiments/delay` | Explicit delays/true offset/processing, or preset ID; optional sweep specification | `DelayResult` envelope |
| `POST /api/v1/experiments/sync` | Initial client offset and modeled delays; required mode is `step` | `SyncResult` envelope |
| `GET /api/v1/recordings` | None | Packaged replay catalog, identifying synthetic and captured data |
| `POST /api/v1/replays` | `{recording_id}` or `{scenario_id}`, exactly one | Validated replay envelope; no UDP |

Duration inputs use explicitly named decimal millisecond strings, such as `forward_ms: "60"`. A live request accepts a configured `server_id`, not an arbitrary destination from the browser. File paths are never accepted through the API. User recording uploads can be deferred; packaged catalogs and CLI replay satisfy the required offline workflow.

The API validates input, invokes services, maps errors, and serializes results. Blocking UDP work runs in a bounded worker, with one live operation in flight and a shared destination cooldown. Use an ordinary request/response for one probe; no queue, job database, WebSocket, or streaming protocol is required. A disconnected browser never triggers retries. The backend still completes or times out the existing attempt and records its cooldown.

Proposed error mapping: invalid input 422; unknown configured ID 404; cooldown/busy 429 with retry metadata; UDP timeout 504; unusable upstream reply 502; DNS/network unavailability 503; recording corruption 503; unexpected internal failure 500 with safe diagnostics. Stable domain error codes remain unchanged across CLI and HTTP.

Run locally on loopback, with a Vite development proxy and a same-origin production build if packaging the final app. No permissive cross-origin configuration or publicly reachable UDP proxy is needed. Share the Python wire contract with TypeScript through OpenAPI-generated types or an explicitly checked schema export; do not maintain a second handwritten calculator in the frontend.

## 11. Three-tab UX architecture

The React app has one shell, one tab bar, and shared components for result provenance, metric values, timestamp tables, assumptions, errors, and playback. Tabs follow the learning sequence: “Real NTP Exchange,” “Network Delay & Accuracy,” and “Clock Synchronization.” There are no separate websites or independent applications.

Use a networking-lab visual system: two clock lanes, directed packet arrows, a compact formula panel, strong readable numbers, and a clear control → observation → conclusion flow. Prefer a wide projector-friendly central diagram over a wall of unrelated dashboard cards. Keep the primary controls and conclusion visible without scrolling at the classroom display size verified in Phase 3; provide a stacked responsive layout on small screens.

| Tab | Primary interaction | Main observation | Persistent conclusion/context |
| --- | --- | --- | --- |
| Real exchange | Measure once, inspect, play recorded exchange, explicitly load replay | Four timestamps and calculated offset/delay | Live true offset and one-way delays are unknown |
| Delay & accuracy | Adjust two delays or select comparison | True versus estimated offset; error changes with asymmetry | Symmetric delay cancels under the displayed model |
| Clock synchronization | Set virtual error, measure model, apply/reset correction | Before/after clock error and residual | Only a virtual clock changes; measurement bias can remain |

Source badges use text and distinct shapes/styles as well as color: “LIVE MEASUREMENT,” “SIMULATION,” or “REPLAY — captured [date]” / “REPLAY — synthetic scenario.” Keep provenance visible in screenshots and exports. A live timeout offers a separate “Load offline example” action; it never silently replaces the failed attempt.

Use explicit loading, empty, success, error, cooldown, and replay states. Disable duplicate live requests and show the next allowed measurement time. Keep a bounded in-memory session history (proposed 20 entries), with provenance on each row. Simulation controls are local to their tabs and never imply injected delay on a public NTP exchange. Users may carry a modeled delay scenario into synchronization by an explicit action; do not carry an unrelated live estimate into the virtual clock.

Packet playback controls support replay, pause, and speed. Animation duration is chosen for explanation, never presented as real transit time. Step correction is labeled as a step even if a highlight/transition helps the audience follow it. For moving clock faces, the browser may extrapolate equal-rate display time from a backend-provided anchor; before/after comparisons and all metrics come from backend snapshots. Such display interpolation is not a new synchronization calculation.

Use keyboard-accessible tabs and controls, visible focus, semantic tables, accessible chart descriptions, readable contrast, and reduced-motion support. Show signs and units alongside every number. Offer large comparison bars or a time-error plot instead of requiring the audience to read clock hands. [Recharts](https://recharts.github.io/en-US/) is a provisional Phase 3 option; plain React SVG is sufficient for the schematic exchange.

## 12. Reliability, testing, and demonstration integrity

Default automated tests use controlled timestamps and injected clocks/transports and need no Internet. Packet fixtures cover valid and invalid responses, era boundaries, and originate matching. A loopback UDP stub exercises sockets on an unprivileged test port, explicitly separate from the production port-123 configuration; it is not evidence of a public exchange. Manually evaluate real public-server interoperability during P1.3 as soon as the first UDP client works, with conservative polling. Record genuine successes, unsupported responses, or honest network failures. Public probes remain outside deterministic CI and never belong in P1.1.

Mathematical tests cover signs, zero and nonzero processing, symmetric-delay invariance, reversed asymmetry, half-nanosecond results, and virtual residuals. Serialization tests cover large epoch values, unknown truth, schema rejection, and preservation of replay provenance. Fake time tests cover timeout/backoff/cooldown without sleeping 64 seconds. CLI integration tests exercise all experiments and recordings without React or FastAPI. The implementation plan defines the full acceptance evidence.

A rehearsed 3–4 minute demonstration can use:

| Elapsed | Action | Teaching point |
| --- | --- | --- |
| 0:00–1:00 | One preflighted live request; inspect/play the exchange. If unavailable, visibly select replay. | Real UDP communication and four-timestamp estimate |
| 1:00–2:15 | Compare low/high symmetric delay, then asymmetric delay with known truth. | Round-trip delay and estimation error are different |
| 2:15–3:30 | Correct +120 ms virtual error under symmetric, then asymmetric delay. | Correction works within measurement quality; bias remains |
| 3:30–4:00 | State limitations and reset for questions. | Scientific honesty and reproducibility |

Preflight the actual classroom network and display. Prepare a genuine recording beforehand if available and deterministic synthetic alternatives regardless. Do not wait through a multi-request live batch on stage. If no genuine recording exists, say so and present the synthetic exchange as a model. A small host offset is a legitimate result, so the simulated experiments provide the visible correction rather than exaggerating live data.

## 13. Approval boundaries

G0, P1.1–P1.7, and the Phase 2 team review gate are complete by the owner-reported approval on 2026-11-23. P3.1 added the optional thin HTTP API over the existing engine. P3.2 added the React shell and Real NTP Exchange. P3.3 adds only the two modeled experiment interfaces using existing endpoints; P3.4 is now authorized and its automated checks pass; see [INTEGRATION_VALIDATION.md](INTEGRATION_VALIDATION.md). Phase 4 remains pending owner review. See [SIMULATIONS.md](SIMULATIONS.md) for controls and validation. See [FRONTEND.md](FRONTEND.md) for execution and verification. No new public probe or OS clock change is part of this task. See [API.md](API.md) for API setup, contracts, and test evidence.

After the standalone Python engine and CLI are implemented and validated in Phase 1, stop at Phase 2 for team review of actual functionality and protocol correctness. FastAPI, React, frontend scaffolding, and web dependencies require explicit approval after that review. Phase 4 integrates the approved application, prepares the four-slide presentation and portfolio materials, and verifies the fallback demo. No commits or pushes are authorized by this plan.
