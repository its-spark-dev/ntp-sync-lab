# NTP Sync Lab — Implementation Plan

Status: Phase 2 team approval and P3.1 API review are complete. P3.2 React shell and Real NTP Exchange are implemented, awaiting review. Authorization ends at P3.2; the other two experiment interfaces and P3.3/P3.4 have not begun.

The architecture, sign conventions, interfaces, proposed tree, CLI, and API contracts are defined in [ARCHITECTURE.md](ARCHITECTURE.md). Complete the phases in order. The standalone backend must work without FastAPI or React, and the team must review it before web work begins.

## 1. Delivery sequence and gates

| Phase | Deliverable | Exit gate |
| --- | --- | --- |
| 0 — Architecture and planning | The two planning documents; no application files or dependencies | G0 complete: architecture approved with refinements; P1.1 authorized |
| 1 — Python backend and CLI | All three experiments, actual UDP client, versioned results, offline scenarios, deterministic tests | Submit runnable backend evidence for Phase 2 |
| 2 — Team review | Hands-on review of CLI behavior, calculations, protocol, educational value, demo readiness | G2: explicit approval before any web development |
| 3 — API and React | Thin FastAPI adapter and one React app with three tabs | G3: verified integration and feature review |
| 4 — Demo and portfolio | Rehearsal, fallbacks, four slides, documentation/screenshots | G4: classroom and portfolio readiness review |

There is no implied approval from the existence of a roadmap or from successful tests. Architecture approval preserves the three experiments, shared Python calculations, CLI-first delivery, and mandatory team review before web development. The approved refinements require simple polling safeguards, early interoperability checks in P1.3, complete educational CLI explanations in P1.6, and step correction only in the required scope. Do not add unrelated production features. P1.1–P1.6 reviews are complete; current authorization covers P3.2 only, after owner-reported team approval and P3.1 review.

## 2. Phase 0 — completed planning deliverable

Tasks completed by this planning change:

- Inspect the repository and existing conventions.
- Define the layer boundaries, domain models, numerical conventions, and limited NTP profile.
- Plan three experiments, a standalone CLI, future HTTP contracts, and one three-tab UX.
- Identify risks, offline workflows, acceptance evidence, and explicit review gates.

Acceptance criteria:

- Only `docs/ARCHITECTURE.md` and `docs/IMPLEMENTATION_PLAN.md` are added.
- No source code, scaffolding, dependencies, slides, commits, or pushes are created.
- The team can review the meaning of offset, delay, truth, error, and virtual correction without guessing.
- The proposal distinguishes actual measurements, synthetic models, and recorded replays in every interface.
- Phase 1 and pre-web review gates are explicit.

**G0 — complete:** Architecture review initially authorized P1.1. P1.1–P1.7 and P3.1 have since passed review. Phase 2 approval and P3.1 review are complete; only P3.2 is authorized in this task.

## 3. Phase 1 — standalone Python backend and CLI

### P1.1 — Package boundary and mathematical core

After G0 approval, create the minimal Python package, `pyproject.toml`, Pytest configuration, and console/module entry points. Keep runtime dependencies in the standard library and add only the approved testing dependencies. Do not add an API directory implementation, FastAPI dependency, frontend directory, or JavaScript manifest.

Implement the immutable models, error codes, timestamp units, exact offset arithmetic, and pure `calculate_exchange` function. Establish the version-1 serialization envelope early so CLI, recordings, and eventual HTTP responses agree. Keep wall-clock access out of pure calculations.

Implement only the models needed for a timestamp quartet, exchange metrics, and an immutable result/serialization foundation. Future packet, configuration, batch, simulation, and replay models are added with their respective tasks. P1.1 does not implement timestamp wire encoding, UDP transport, experiment engines, recording loaders, or experiment commands. Minimal entry points may identify the foundation and show help, without performing an experiment.

Acceptance evidence:

- Controlled T1–T4 fixtures verify zero, positive, and negative server-minus-client offset.
- Increasing server processing changes total elapsed time but cancels from network round-trip delay.
- Symmetric-delay invariance and half-nanosecond offset results are exact at the decoded nanosecond level.
- Epoch timestamps larger than JavaScript's safe integer range round-trip as strings.
- Unknown live truth remains `null`; invalid inputs and nonfinite values are rejected.
- The package and pure tests run without web libraries or network access.

**P1.1 review stop — satisfied:** The user approved P1.1 and explicitly authorized P1.2 after the implementation/test report. The next stop is the P1.2 review below.

P1.1 implementation evidence: Python 3.11.14 with Pytest 9.2.0; `.venv/bin/python -m pytest -q` passed all 80 deterministic tests. The console and module entry-point help were smoke-tested. At that point the foundation had no runtime dependencies, wire codecs, networking, experiment engines, functioning experiment commands, replay loader, FastAPI, or React. The serializer is an exchange envelope foundation, not yet a complete recording/export format. Implementation stopped for review before P1.2 was approved.

Recommended starting task: agree on the `TimestampQuad`/`ExchangeMetrics` contract and implement the four-timestamp calculation with hand-derived fixtures. This anchors all later experiments before sockets add uncertainty.

### P1.2 — Timestamp codec and packet validation

Implement integer wire conversions, epoch translation, era unfolding, request encoding, base-header parsing, response checks, and typed control/error responses. Preserve exact request transmit bytes. All functions are pure; local clock resolution/capture and injected clock adapters belong to P1.3. The validation boundary accepts actual/expected numeric peers and captured T4 from that future adapter.

Acceptance evidence:

- Known raw timestamp words decode correctly and encode within the documented conversion tolerance.
- Tests cross the February 2036 era boundary using a controlled nearby reference date.
- A valid mode-4, version-4, 48-byte response is accepted.
- Short packets, unsupported trailers/versions/modes, mismatched originate values, unsynchronized status, and invalid within-clock timing produce the documented outcomes.
- A stratum-zero control response is recognized even when its normal time fields are unusable.
- No cross-clock timestamp comparison incorrectly rejects a legitimate large offset.
- Packet parsing performs no I/O, and source/originate validation is not represented as authentication.

P1.2 implementation decisions: use immutable raw `NtpTimestamp` words, integer nearest/ties-to-even conversions, and explicit nearest-era inference with an ambiguous-midpoint rejection. Packet zero timestamps are unspecified even at the era boundary; do not alter an all-zero outgoing T1 to manufacture a valid request. Check raw server timestamp ordering before nanosecond rounding. Stratum-zero replies retain their raw reference ID and stop the target after correlation checks, before normal timestamp/LI checks. Reject trailing data without asserting its unparsed contents. No P1.1 calculation or JSON contract change is needed.

P1.2 validation evidence: `.venv/bin/python -m pytest -q` passes all 218 tests (80 existing P1.1 tests and 138 new timestamp/packet tests) on Python 3.11.14 with Pytest 9.2.0. An isolated import/execution check outside the checkout confirms the installed protocol functions work without importing socket transport, CLI, or web frameworks. Real-server interoperability remains unverified until P1.3.

**P1.2 review stop — satisfied:** The user approved the protocol layer and explicitly authorized P1.3, including one initial public probe after deterministic tests. No UDP/DNS work was performed during P1.2.

### P1.3 — UDP exchange and safe repeated measurements

Implement the injected resolver/transport and `measure_once`. Use destination port 123, an ephemeral source port, application-boundary T1/T4 sampling, monotonic deadlines, socket cleanup, and a fixed deadline across ignored datagrams. Immediately after the first functioning UDP client is available, manually evaluate real NTP server interoperability. Record target, packet profile/length, validation outcome, and a genuine result or accurate failure. Do not defer all compatibility evaluation until P1.7 and do not introduce networking in P1.1.

Add live batches, bounded counts/timeouts, conservative in-process cooldowns, and timeout backoff. Start with the smallest reliable implementation. Evaluate independent CLI invocations in this task; add only a minimal last-send/next-allowed record if needed to prevent accidental excessive requests. A complex persistent polling-state subsystem is not required. Document protection boundaries, restart/concurrency limitations, and the operator's minimum interval between independent probes.

Implement fake clock, resolver, and transport adapters for deterministic tests. Add a loopback UDP test server on an unprivileged port behind a test-only transport configuration; never require public Internet for the default test suite.

Acceptance evidence:

- Fake transports verify exactly one sent request per attempt and no immediate retry on failure.
- Ignored wrong-peer/originate packets cannot extend the receive deadline.
- T4 is captured before response decoding; packet construction uses the recorded T1.
- A controlled wall-time jump is rejected, while monotonic time still bounds receive waiting.
- Timeout, DNS failure, socket failure, and malformed/control/unsupported replies have actionable, accurate diagnostics. An unparsed trailer is reported as unsupported, not asserted to be a valid extension or authentication field.
- Fake-time tests demonstrate 64 s minimum spacing, sequential attempts, 128/256 s timeout backoff, and target control stopping without real sleeps.
- The implementation documents which cooldowns survive process exit and whether concurrent invocations are coordinated. Any justified minimal persistence has targeted failure tests; no elaborate locking/state framework is required.
- Completed attempts survive partial failure/interruption, and summaries exclude failed samples.
- Local UDP tests exercise request/response bytes and source checks with no elevated privileges.

Required P1.3 interoperability evaluation: probe an approved public server conservatively as soon as the client works, checking cooldown and network policy. Record actual compatibility evidence or the connectivity limitation. If a response is unsupported, preserve its diagnostic metadata and evaluate whether a small, tested scope adjustment is needed. A blocked public probe is not a reason to falsify a capture or make deterministic CI depend on Internet access. Document that DNS resolution is outside the UDP timeout.

P1.3 implemented scope and decisions:

- `core/clock.py`, `transport.py`, and `client.py` provide injected capture, one-address resolution, UDP send/receive, software T1/T4, unchanged packet validation/calculation, typed failures, and structured results. No alternate-address retries occur. A default 3 s monotonic deadline includes reservation/setup/send/receive after DNS/socket creation; ignored packets never reset it.
- `core/polling.py` uses the minimal per-destination JSON record plus brief POSIX `flock` transactions required for independent and concurrent invocations. State is atomic, shared by the default cache directory, and reserves before transmission. Normal spacing is at least 64 s from send completion; initial/crashed reservations retain 74 s. Timeout backoff is persisted at 128/256/512/1024 s. Stratum-zero control blocks survive restart without automatic expiry. This is local operational state, not a database or scheduling service.
- Guard limits: cooperating macOS/Linux processes sharing one cache directory are protected. Windows fails closed until a lock adapter exists. Cross-user/machine coordination is outside scope. Persistent wall-time deadlines assume a stable clock; backward steps fail closed, but large forward steps across new guard instances can shorten cooldowns. An existing instance also enforces monotonic time. State corruption/failure blocks live work; batch outcome-update failures stop with partial results. Do not bypass state or clear a control block without reviewing server policy.
- `experiments/measurement.py` provides 1–10 explicit sequential attempts and 64–3600 s configured spacing, valid-only summaries, separate success/failure records, and completed-result preservation on interruption. Initial cooldown/contention fails visibly; fatal DNS/control/state failures stop the batch. No NTP filter/discipline, simulation engine, or educational CLI is implemented.
- Serialization extends the version-1 exchange envelope with raw packets, peer/server/capture metadata and unknown truth as null. Fraction formatting additionally preserves quarter-nanosecond medians; original whole/half-nanosecond contracts remain unchanged. The full replay loader is deferred.
- `python -m ntp_sync_lab.diagnostics` is an internal, single-probe-only diagnostic respecting the same policy. Its output file is exclusively created before networking to avoid accidental overwrite/re-probe behavior. It is separate from the future CLI.

P1.3 validation: the full suite passes **285 tests** on Python 3.11.14/Pytest 9.2.0 (all 218 prior tests plus 67 new cases). New coverage includes both real IPv4 and IPv6 loopback UDP exchanges on unprivileged ports, cross-process reservation contention, fake-time polling/backoff, exact timestamps, software capture order, invalid replies, cleanup/error paths, interruption, partial batches, and serialization. The test suite installs a public-network audit guard; public DNS/UDP calls are blocked. No test waits 64 s or depends on Internet access.

After the first 281 deterministic/loopback tests passed, exactly one guarded public probe to `pool.ntp.org` succeeded with the supported 48-byte v4/mode-4 profile, stratum 2. No retries or further public probes were made. Additional offline edge-case checks brought the suite to 285. The [interoperability report](INTEROPERABILITY.md) separates the genuine capture from all fixtures and includes the raw evidence, observed metrics, and limits.

**P1.3 review stop — satisfied:** The user approved networking and its evidence, and explicitly authorized P1.4. The approved live behavior remains unchanged; no additional public probes belong to P1.4.

### P1.4 — Delay and asymmetry experiment

Implement `DelayConfig`, deterministic timestamp generation, the four required presets, and fixed-round-trip sweeps. Reuse the established calculation module. Use exact decimal input conversion and enforce the documented bounds. No real traffic or wall-time sleeps are involved.

Acceptance evidence:

- With true offset +100 ms, 20/20 ms delays give θ̂=+100 ms, δ=40 ms, e=0.
- Raising both delays to 80 ms gives θ̂=+100 ms, δ=160 ms, e=0.
- 60/20 ms delays give θ̂=+120 ms and e=+20 ms; reversing them gives θ̂=+80 ms and e=-20 ms.
- All fixed-80-ms-round-trip sweep points have δ=80 ms while error varies with asymmetry.
- Processing time cancels from δ and θ̂ under the model.
- Returned assumptions include equal clock rates, constant offset, deterministic one-way delays, known reference, and no loss/jitter.
- Negative delays, conflicting preset/custom inputs, excessive sweep sizes, and unsupported precision fail clearly.

P1.4 implementation: `experiments/delay.py` owns immutable input/result models, the four presets, exact Decimal-to-nanosecond conversion, quartet generation, and fixed-total/equal-increase sweeps. Only the established `calculate_exchange` computes NTP offset/RTT. Serialization adds simulation-only envelope helpers with explicit caller-provided ID/creation time, normalized parameters, truth/error, assumptions, and conclusion. Original domain/calculation, packet, and live-network behavior is preserved. Complete-endpoint fixed-total sweeps accept at most 2000 ms because either endpoint puts the total on one path; independent pairs may still total 4000 ms. Tiny totals can generate duplicate rounded points while retaining exact total delay. Equal-increase inputs must be strictly increasing and stay within bounds.

P1.4 validation: the complete suite passes **369 tests** (285 preserved cases plus 84 new delay cases). Tests independently verify the four preset quartets/results, offset signs, symmetric invariance, asymmetry, processing cancellation, half-nanosecond precision, rounding, bounds/conflicts, immutable presets, Decimal context independence, repeatable serialization, and simulation provenance. A 9-point 80 ms sweep holds RTT exactly constant while forward delay runs 0,10,...,80 ms and estimation error runs -40,-30,...,+40 ms. Cold import/execution outside the checkout also verified no socket, live client, polling, CLI, or web dependency; network, clock, and sleep operations are forbidden in the delay execution test.

**P1.4 review stop — satisfied:** The user approved the delay model and its validation, and explicitly authorized P1.5. The validated delay and live-network behavior remains unchanged.

### P1.5 — Virtual clock synchronization

Implement a virtual clock represented by a reference anchor and client error, generate its corresponding modeled exchange, and apply a single correction step. Return an explicit measurement plus before/after snapshots and a backend-generated trajectory. Do not accept an unrelated host measurement as the virtual clock's estimate.

Acceptance evidence:

- Initial client error +120 ms yields true NTP offset -120 ms.
- A symmetric 20/20 ms exchange applies -120 ms and leaves zero residual.
- An asymmetric 60/20 ms exchange applies -100 ms and leaves +20 ms residual.
- A client starting behind the reference receives a positive correction.
- Zero initial error can acquire residual error under asymmetric delay; the result does not hide this case.
- For representative parameter combinations, `b_after = b_before + θ̂ = (df-dr)/2` holds exactly.
- Compared clocks are sampled at common reference instants; elapsed playback time cannot masquerade as correction.
- The implementation only changes virtual model state and contains no path to changing the OS clock.
- Required behavior is a single step correction; progressive correction and full NTP clock discipline are excluded from required scope.

Do not implement progressive correction, oscillator drift estimation, or full clock discipline as part of the required tasks. Any future extension requires separate scope approval.

P1.5 implementation: `experiments/synchronization.py` owns immutable virtual clock/config/result/snapshot/event models. `SyncResult` derives its measurement via the existing `run_delay` once, with true offset equal to negative initial client error. Correction is the measured estimate; final error is initial error plus correction. The same-instant comparison occurs at modeled response reception (`T4 - initial_client_error`), and a three-point logical timeline represents measurement start, before step, and after step. Models reject mismatched event instants/correction values or inconsistent phase ordering. Integer-nanosecond input bounds and decimal conversion are reused; half-nanosecond corrections, residuals, and absolute virtual times remain exact. There are no independent measurement/true-offset/correction inputs that could conflict with the virtual clock.

Serialization adds only the planned `clock_sync` identifier and schema-1 simulation helpers, preserving prior contracts. It includes the nested modeled measurement, original quartet/shared metrics, before/after snapshots, explicit step event, derived timeline, explanations, and assumptions. IDs/creation metadata are caller-supplied; the engine reads no clock and generates no random identity. No live-network changes, progressive correction, drift model, educational CLI, or web dependencies are introduced.

P1.5 validation: **454 tests pass** (369 preserved cases plus 85 new cases) on Python 3.11.14/Pytest 9.2.0. Independently derived required scenarios yield corrections -120/-100/-140 ms and residuals 0/+20/-20 ms. A representative grid verifies both residual invariants across positive/negative/zero initial error, both asymmetry signs, processing limits, and half-nanosecond values. Other checks cover source/sign correctness, measured-correction delegation, same-instant snapshots, zero-duration exchanges, immutable results, conversion/bounds/conflicts, timeline/event validation, deterministic JSON, and explicit simulation provenance. Network, host-clock read/write, process, and sleep operations are forbidden in execution tests. Cold import/run/serialization outside the checkout confirms no socket/live-client/host-clock-adapter/polling/CLI/web dependency.

**P1.5 review stop — satisfied:** The user approved the three backend capabilities and authorized P1.6 CLI/offline integration. Phase 2 team review is still mandatory before web development.

### P1.6 — CLI, scenarios, recordings, and backend documentation

Expose all required commands from the architecture document through `argparse`. Every experiment command must give a structured human-readable explanation of its objective, inputs, T1–T4 timestamps and clock ownership, calculations with substitutions/units, results, assumptions/limitations, and conclusion. Synchronization also explains the correction and before/after errors. Failed exchanges clearly mark unavailable observations instead of inventing them. Keep machine-readable JSON as a separate output mode. Implement explicit units/signs, error mapping, file output rules, scenario catalog, and replay. Package deterministic resources. Include a genuine public capture only if one has actually been obtained and validated.

Acceptance evidence:

- From a clean approved Python environment, documented install/run instructions produce a working console script and `python -m ntp_sync_lab`.
- `measure`, `delay`, `sync`, `scenarios list`, and both replay paths work without React/FastAPI.
- Help and text output explain both offset signs and distinguish clock error from estimation error.
- All three experiment commands include the objective, inputs, timestamps, calculations, results, assumptions, and conclusion; explanations are verified independently of JSON output.
- JSON is one valid document with no progress text mixed into stdout; file exports are valid replay inputs.
- Failed/partial live batches retain ordered attempt results and documented nonzero exit codes.
- Replay checks schema, units, source, and stored calculation consistency; unsupported/corrupt recordings fail clearly.
- Replay preserves original capture dates and source, labels replay time separately, and opens no sockets.
- Synthetic scenarios can be reproduced exactly without Internet; installed package resources work outside the checkout.
- File output refuses accidental overwrite; interruption closes sockets and retains completed attempt results.
- README/backend usage and a preliminary demo runbook describe limitations, safe polling, actual versus synthetic data, and offline operation.

P1.6 implementation: existing console/module entry points now share one argparse CLI. Commands dispatch to unchanged measurement, delay/sweep, and synchronization services. Educational formatting includes objective, inputs/provenance, correctly owned timestamps with UTC/exact values, formula substitutions, results, assumptions, and conclusion. Sweep output has one worked point plus a comparison table. JSON stays separate from stderr status/progress; file exports retain full native envelopes and use atomic no-clobber/explicit overwrite. Completed results survive export failure in text or JSON `partial_result`. Existing polling/cooldown/backoff semantics remain enforced by the live service; startup/help/offline commands never call it.

Packaged resources include ten catalog entries: four synthetic delay cases, five synthetic virtual-clock cases, and the genuine P1.3 public capture. The capture was verified through pure packet/calculation validation and copied byte-for-byte with no missing metadata invented. Replay validates supported native schema-1 result/series/batch/wrapper shapes, units, exact model outputs, live raw packets/clock diagnostics, and valid-only summaries. The original document is preserved unchanged in a source-labeled replay wrapper with a separate replay time. Duplicate keys, nonfinite values, unsupported fields/versions, files over 1 MiB, and excessive nesting are rejected. Consistency is not a claim of capture authenticity. Model input definitions and raw capture resources are found via importlib.resources outside the checkout.

P1.6 validation: **554 tests pass** (454 existing + 100 new CLI/recording cases) with Python 3.11.14/Pytest 9.2.0. Coverage includes all command families, conflicts/bounds/help, educational sections, JSON/export/overwrite/races/symlinks, injected live failures and partial/interrupted batches, catalog/replay provenance, malformed/corrupt recordings, and installed entry points. Offline subprocesses forbid socket operations. A non-editable wheel resource smoke check outside the checkout also exercised catalog, genuine saved replay, delay, and sync with networking forbidden and JSON/capture dates verified. No new public probe or runtime dependency was introduced. Representative outputs and a replayable JSON export are saved under `docs/examples/`.

At the P1.6 checkpoint, the preliminary demo runbook included the recommended sequence, expected values, preflight/polling precautions, explicit fallback, file inventory, limits, and review checklist. Its wheel build succeeded with the existing setuptools license-table deprecation warning. That warning and the backend review bundle were subsequently addressed in P1.7 below; these were not claimed by the P1.6 feature tests. Human classroom rehearsal and Phase 2 approval remain outstanding.

**P1.6 review stop — satisfied:** Feature integration was approved and P1.7 validation was explicitly authorized. No commits or pushes are authorized.

### P1.7 — Backend validation and review bundle

Run the deterministic suite and CLI smoke scenarios; do not repeatedly query public servers as a verification shortcut. Prepare a compact review bundle containing:

- Test results and the exact environment/commands used.
- Human-readable output and JSON for all three experiments.
- A local UDP integration result plus an actual public result or a clearly reported connectivity failure.
- A symmetric/asymmetric comparison and its hand-calculated expected values.
- A virtual correction example with both zero and nonzero residual.
- An offline replay demonstration and provenance inspection.
- Known limitations, unresolved defects, and any changed architecture decisions.

No code-quality percentage alone establishes protocol correctness. Reviewers need observable results and independently derived expected values.

P1.7 outcome: **PASS for backend/team-review readiness**, with 563 tests passing both in the project environment and against a clean installed wheel, plus 50 independent installed CLI checks. Hand-derived examples confirm formulas/signs, processing cancellation, asymmetry, virtual residuals, epoch conversion, and rollover. No new public probe was needed: the genuine P1.3 capture remains unchanged. Targeted regressions corrected loss of polling outcomes under brief contention and missing replay clock-discontinuity enforcement; new exports record the configured threshold while old captures retain their original bytes. SPDX MIT metadata replaces the deprecated license table; isolated wheel/sdist builds are warning-free. See [BACKEND_VALIDATION.md](BACKEND_VALIDATION.md) for evidence and compatibility limits.

The [TEAM_REVIEW.md](TEAM_REVIEW.md) bundle and revised [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) are ready. The five-command classroom sequence was executed offline and its output inspected; 3–4 minutes is an estimated focused narration budget, not a measured human talk. Projector readability and spoken timing still require a human rehearsal. **Stop after P1.7; await explicit review.** Neither Phase 2 approval nor web work is implied.

## 4. Test matrix for backend acceptance

| Area | Technique | Required evidence |
| --- | --- | --- |
| Offset and delay | Hand-derived timestamp fixtures | Correct signs, processing subtraction, zero/asymmetric cases |
| Precision | Integer/fraction fixtures | Half-nanosecond result preserved; no float epoch subtraction |
| Wire timestamps | Known raw words and era fixtures | Epoch conversion and adjacent-era behavior |
| Validation | Raw packet mutations | Peer, originate, length, version/mode, server status, timing rejection |
| Capture/clock behavior | Injected wall/monotonic clocks | T1/T4 order, discontinuity diagnostic, no claimed hardware precision |
| Availability | Fake resolver/socket | Distinct DNS/timeout/network errors, bounded UDP wait |
| Polling | Fake elapsed time; temp files only if minimal persistence is justified | Cooldown, backoff, control-response stop, and explicit restart/concurrency limits |
| Live socket path | Loopback UDP responder | Actual socket send/receive on unprivileged test port |
| Delay model | Presets and bounded parameter grid | Symmetric invariance; `e=(df-dr)/2`; fixed-RTT sweep |
| Virtual correction | Before/after invariants | Correct direction and asymmetry residual; no OS clock mutation |
| Contracts/replay | Round-trip and invalid documents | Source/era/precision preserved, false live truth rejected |
| CLI | Subprocess invocation with offline fixtures | Every command, parseable JSON, exit codes, help/errors |
| Public interoperability | Manual evaluation early in P1.3 | Genuine capture, unsupported-response diagnostics, or honest network failure; outside deterministic CI |

Use temporary directories for output and any justified minimal cooldown state in tests. Test collection must not resolve public hostnames or open external sockets. Timing-sensitive tests use fake time rather than real sleeps. Unit tests verify behavior and mathematical invariants, not private implementation details.

## 5. Phase 2 — mandatory team review gate

**G2 — satisfied (2026-11-23):** The project owner reports that teammates completed the review and unanimously approved the backend. No reviewer names, meeting minutes, or separately measured classroom timing are invented here. P3.1 was subsequently implemented and reviewed; current authorization is P3.2 only.

The team runs the CLI and reviews the bundle; reading source alone is insufficient. Review questions:

1. Is a real UDP request sent to port 123, and are the four timestamps interpreted from the correct clocks and fields?
2. Do formulas, signs, era handling, and response validation match the documented scope?
3. Can symmetric delay and asymmetry be distinguished with independently checked examples?
4. Does virtual correction use an appropriate modeled measurement, preserve bias where expected, and leave the OS clock untouched?
5. Are live measurements, modeled truth, unknown truth, and replay provenance visible and accurate?
6. Do failures, safe polling, and offline scenarios work on the intended demonstration machine?
7. Can the backend support a useful 3–4 minute demonstration of the assigned networking topic?

Acceptance requires all required CLI capabilities, passing deterministic tests, an exercised socket path, reproducible scenarios, and explicit resolution of material correctness defects. If campus UDP is blocked, record the limitation and approve a labeled recording/model fallback; do not describe offline data as a successful public exchange.

**G2 approval recorded:** The prerequisite team review is complete. P3.1 is complete and P3.2 has now been explicitly authorized; stop after the React shell and Real NTP Exchange without starting P3.3.

## 6. Phase 3 — FastAPI and one React application

### P3.1 — Thin API

After G2 approval, add the optional web dependencies and the specified `/api/v1` endpoints. Map existing dataclasses/contracts to boundary schemas, put blocking UDP work behind a bounded worker, and reuse the live cooldown service. Restrict live targets to configured IDs. No database, task queue, or background polling is required.

Acceptance criteria:

- API tests use injected services and compare normalized result payloads with the equivalent CLI/domain outputs.
- Input bounds, rate limits, error/status mapping, and replay provenance are preserved.
- One measurement request produces at most one sent datagram, regardless of UI rerenders or browser disconnection.
- Health/scenario/replay requests perform no public networking.
- Loopback binding, development proxy, and same-origin release setup work without permissive CORS.
- TypeScript types come from or are checked against the actual API schema, including string timestamps and null truth.

P3.1 implementation complete: optional `web`/`web-test` extras, eight `/api/v1`
endpoints, strict boundary inputs and OpenAPI result models, one in-flight live
worker with cancellation shielding, shared polling guard, configured server IDs,
same-origin/local Host checks, and domain error mapping. Existing calculations,
transport, serializers, and CLI remain unchanged. Validation: **69 API tests and
632 total tests pass**, plus installed-wheel Uvicorn loopback HTTP smoke checks.
No public probe was made. See [API.md](API.md) for exact setup/contracts, limits,
and evidence. At that P3.1 checkpoint, React/Vite proxy and frontend release validation were
pending. P3.1 review was subsequently completed; P3.2 below adds those paths.

### P3.2 — Shared shell and Real NTP Exchange tab

Create React + TypeScript + Vite only now. Build one shell with accessible tabs, shared source labels and metrics, and a central packet diagram. Implement real measurement, loading/error/cooldown states, timestamp inspection, formula substitution, bounded history, and explicitly labeled playback/replay.

Acceptance criteria:

- All four recorded timestamps are visible with units and clock ownership.
- Playback says its timing is illustrative and does not claim a live packet trace or known one-way delays.
- Small actual host offsets are displayed honestly; no fabricated dramatic error.
- A live failure remains visible until the user explicitly selects an offline alternative.
- Keyboard operation and reduced motion work; primary values are readable on the target projector.

P3.2 implementation: Safari-inspired horizontal tabs, system typography and
translucent controls, Real NTP Exchange setup/live/error/cooldown/replay states,
illustrative play/pause/speed/restart, exact timestamp inspection, backend metric
and formula display, preserved JSON export, and 20-entry session history. The
other two tabs have preparation notices only. TypeScript contracts are generated
from the actual API schema and checked for drift. Local Vite proxy and optional
same-origin static release preserve the API's origin policy. See
[FRONTEND.md](FRONTEND.md) for startup, test evidence, and limits. Stop for P3.2
review; P3.3 and the other experiment screens are not authorized.

### P3.3 — Delay and Clock Synchronization tabs

Wire controls to backend simulations. Add the required delay comparisons, true/estimated/error chart, virtual clock snapshots, correction step, and explicit reset. An explicit scenario transfer may connect Tabs 2 and 3. Browser code handles presentation and display interpolation only.

Acceptance criteria:

- The UI reproduces all preset outcomes from Phase 1 with correct labels and signs.
- Increasing equal delays raises RTT while leaving model estimation error zero.
- Fixed-RTT asymmetry visibly changes estimation error.
- Virtual correction shows zero residual under symmetric assumptions and the predicted residual under asymmetry.
- No authoritative NTP calculation is duplicated in TypeScript; charts render backend-returned points.
- Controls and assumptions remain local to their experiment; no apparent injection of delay into a live public exchange.
- Layout works on the target classroom screen and a narrow responsive viewport; text, units, focus, and chart alternatives are legible.

### P3.4 — Integrated acceptance

Run API/CLI parity checks, frontend type/build checks, and focused end-to-end workflows for the three tabs, timeout, cooldown, reset, and offline replay. Use controlled API fixtures for deterministic end-to-end assertions. Recheck the actual live path manually only as needed within polling policy.

G3 acceptance: one app, three functioning tabs, same validated engine, no silent source substitution, and no unresolved correctness or demonstration-blocking defects.

## 7. Phase 4 — integration, presentation, and portfolio

Tasks:

- Rehearse the architecture's approximately 3:30 demonstration on the actual machine and network. Rehearse the offline path with networking disabled as well.
- Verify a genuine recording's metadata if available; ensure synthetic fallbacks remain visibly synthetic.
- Finalize `docs/DEMO_RUNBOOK.md` with startup, preflight, cooldown, fallback, reset, and expected values.
- Create the required four-slide presentation only in this phase: motivation, exchange/formulas, delay/asymmetry, and virtual correction/results. Keep 2–3 minutes for topic explanation and 3–4 minutes for the demonstration, plus approximately 1–2 minutes of Q&A.
- Prepare Q&A on asymmetry, unknown live truth, offset versus drift, software timestamp limits, and simplified versus full NTP.
- Finish setup instructions, architecture links, screenshots with source labels, limitations, dependency records, and license notices appropriate for a public portfolio.
- Exercise the documented clean setup and final test/build commands once; avoid broad repeated testing after checks pass without a new reason.

G4 acceptance:

- The full demonstration meets the allotted time without waiting for live batches or depending on public UDP availability.
- Each experiment has a visible interaction, observable result, and defensible conclusion.
- Live, synthetic, and replayed material is distinguishable on screen and in the presentation.
- Four slides and final documentation accurately describe the delivered behavior.
- No operating-system clock change, privileged action, invented live capture, or misleading accuracy claim is present.
- Portfolio artifacts are ready for review. Commit, push, deployment, and publication still require the user's instructions; this roadmap does not authorize them.

## 8. Technical risk register

| Risk | Effect | Mitigation / acceptance evidence |
| --- | --- | --- |
| UDP 123 blocked or public server unavailable | Live demonstration cannot complete | Preflight one target, timeout visibly, retain genuine replay if available, always ship deterministic scenarios |
| Excessive requests or server control reply | Load on public infrastructure, blocked target | Single-request demo, 64 s minimum, simple cooldowns, bounded batches, backoff, stop on control reply; document independent-invocation limits |
| DNS blocks longer than socket timeout | A nominal 3 s probe takes longer | State timeout scope; preflight/use an approved numeric address; do not promise a hard DNS deadline |
| Reversed offset sign | Wrong explanations and correction direction | Define θ and b separately; hand-derived positive/negative fixtures and residual invariants |
| Asymmetry presented as known live truth | Incorrect accuracy claim | Live truth/error are null; one-way delays exist only in the model; schematic playback |
| Precision lost through floats/JSON | Incorrect small differences or era behavior | Integer codecs, exact offset halves, string epoch timestamps, boundary tests |
| Era/leap/smear interpretation | Incorrect calendar time or UTC claim | Nearby-date era assumption, 2036 fixtures, metadata, exclude leap/smear accuracy claims from model |
| OS clock step/slew and local scheduling | Distorted T1/T4 and uncertain measurement | Wall/monotonic diagnostics, reject detected jumps, report software timing limitations |
| Narrow packet profile rejects real server | Reduced interoperability | Evaluate real servers immediately after the P1.3 client works; explicit unsupported diagnostics, tested scope changes only |
| Unauthenticated UDP | False time response could pass basic checks | Restrict targets, match peer/originate, report no authentication; do not use results for system time control |
| Replay mislabeled or fabricated | Scientific integrity failure | Versioned provenance, actual capture timestamps, synthetic resource separation, no silent fallback |
| Virtual correction hides residual or claims drift discipline | Misleading experiment | Same modeled measurement, invariant tests, equal-rate assumptions; required scope is step correction only |
| Web logic diverges from CLI | Conflicting educational results | Shared Python services/serializer, schema-checked types, API/CLI parity tests |
| Independent CLI invocations bypass in-memory cooldowns | Accidental excessive requests | Document protection limits and minimum wait; add a small persistent record only if justified during P1.3 |
| Scope and dependency growth | Backend review and demo delayed | Strict gates, no database/cloud/queue, optional features deferred, no frontend work before G2 |

## 9. Completion policy for this turn

Complete P3.2 React shell and Real NTP Exchange only. Keep the other two tabs as
preparation notices. Validate types/build, frontend interactions, offline replay,
API regression suite, accessibility, and local same-origin operation. Stop for
review; do not begin P3.3/P3.4, make public probes, change the OS clock, commit,
or push.
