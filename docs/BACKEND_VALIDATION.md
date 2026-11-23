# P1.7 backend validation

Follow-up (2026-11-23): the owner reports unanimous Phase 2 approval. P3.1 API
work is documented in [API.md](API.md). The results below remain the historical
P1.7 validation record, not a statement of the current approval boundary.

**PASS — ready for hands-on team review.** No unresolved high-severity defect
or CLI demonstration blocker was found after correction. This is a backend
validation verdict, not team approval or authorization for web work.

## Environment and results

Validated 2026-11-15 on macOS 26.6.2 arm64, CPython 3.11.14, Pytest 9.2.0,
pluggy 1.7.0, uv 0.9.27. Isolated builds were constrained to setuptools
**77.0.3**, the newly declared minimum. Runtime dependencies remain empty.

| Check | Outcome |
| --- | --- |
| Unmodified P1.6 baseline, `.venv/bin/python -m pytest -ra` | 554 passed, 2.55 s |
| Final project suite, same command | 563 passed, 2.70 s |
| Fresh wheel environment, full suite from `/tmp` | 563 passed, 2.86 s |
| Targeted polling/recordings/CLI suite after corrections | 123 passed, 2.64 s (included above) |
| Independent installed CLI acceptance | 50/50 expected outcomes, both entry points |
| Isolated wheel + sdist; rebuild wheel from sdist | Success; wheel contents identical; zero warnings |

There were **zero test failures, skips, or warnings** in the passing suites.
Both IPv4 and IPv6 loopback tests executed. The new nine cases comprise two
polling-contention outcomes, one invalid clock interval, one custom threshold
round trip, and five malformed thresholds. Before correction, the four positive
regression cases failed as expected; they exposed actual defects.

Fresh environment procedure (substitute a temporary directory for `$VALIDATION_DIR`):

```sh
printf 'setuptools==77.0.3\n' > "$VALIDATION_DIR/minimum-build.txt"
uv build --sdist --wheel --python .venv/bin/python --build-constraints "$VALIDATION_DIR/minimum-build.txt" --out-dir "$VALIDATION_DIR/dist"
uv build "$VALIDATION_DIR/dist/ntp_sync_lab-0.1.0.tar.gz" --wheel --python python3.11 --build-constraints "$VALIDATION_DIR/minimum-build.txt" --out-dir "$VALIDATION_DIR/from-sdist"
uv venv --python python3.11 "$VALIDATION_DIR/clean-venv"
uv pip install --python "$VALIDATION_DIR/clean-venv/bin/python" --no-deps "$VALIDATION_DIR/dist/ntp_sync_lab-0.1.0-py3-none-any.whl"
# Run CLI acceptance outside the checkout before adding test tools.
uv pip install --python "$VALIDATION_DIR/clean-venv/bin/python" 'pytest==9.2.0'
# From /tmp, use the installed interpreter and an absolute path to repository tests:
"$VALIDATION_DIR/clean-venv/bin/python" -m pytest /absolute/path/to/ntp-sync-lab/tests -ra
```

Only `ntp-sync-lab` was installed during initial CLI acceptance. Its import path
was inside the clean environment's `site-packages`, not an editable/source path.
The wheel/sdist contain the MIT license, scenario catalog, and unchanged public
recording. Their contents, entry-point metadata, Python requirement, and absence
of runtime dependencies were inspected directly.

## Independent mathematical and protocol findings

Let server-minus-client truth be θ, forward/reverse transit df/dr, and server
processing p. With client T1=0, the independently derived quartet is
`(0, df+θ, df+p+θ, df+p+dr)`. Thus the estimate is
`θ+(df−dr)/2` and network RTT is `df+dr`; p cancels. Only T4−T1 and T3−T2 are
chronological intervals within a clock. Cross-clock comparisons are unsuitable
for rejecting replies.

Hand-derived values were checked directly against `calculate_exchange`, without
using the delay engine to generate expectations:

| T1, T2, T3, T4 (ms) | Expected estimate ms | Expected RTT ms |
| --- | --- | --- |
| 0, 10, 12, 8 | +7 | 6 |
| 0, −4, −2, 8 | −7 | 6 |
| 0, 3, 5, 8 | 0 | 6 |
| 0, 12, 14, 8 | +9 (θ=7, bias +2) | 6 |
| 0, 8, 10, 8 | +5 (θ=7, bias −2) | 6 |
| 0, 12, 32, 26 | +9 (longer processing) | 6 |

For virtual client error b, θ=−b, correction=`−b+(df−dr)/2`, and residual
`b+correction=(df−dr)/2`. With df/dr=5/1 ms, b=+11/−11/0 ms produced corrections
−9/+13/+2 ms and residual +2 ms. A direct ns quartet `(0,1,2,2)` preserved an
exact 0.5 ns offset. Existing preset results and same-instant snapshots agree.

Unix zero independently encodes to `83aa7e8000000000`, Unix +0.5 s to
`83aa7e8080000000`. The 2036-02-07 06:28:16 UTC rollover is Unix
2,085,978,496 s and raw seconds zero. Codec checks at the boundary and ±1 ns,
negative dates, and a 2¹⁰⁰ ns epoch preserve whole ns with the correct era.
Raw zero is a codec value but an unavailable timestamp in packets. Conversion
uses integer nearest/ties-to-even rounding; raw words survive validation.

Code and tests confirm exact originate bytes, actual response peer, v4/mode 4,
strata 1–15, unsynchronized LI/stratum, stratum-zero control handling before
normal timestamps, short/trailing packets, missing T2/T3, raw sub-ns server
ordering, and calculated negative-delay rejection. These checks correlate
traffic; they provide no cryptographic authentication. Capture occurs at the
application boundary, with monotonic deadlines and measured clock-read spans.

## CLI, JSON, replay, and reliability evidence

[Acceptance results](evidence/p1.7-cli-acceptance.json) record all 50 checks.
Both actual installed entry points ran help, catalog, replay, delay, sync, and
measure from outside the checkout. Successful experiment text contains all
seven educational sections, timestamp ownership/UTC, substitutions, units,
assumptions, and conclusions.

Offline subprocesses used an audit hook rejecting **every** `socket.*` event.
Measurement subprocesses used an injected numeric resolver and an actual local
UDP responder on an unprivileged port, with DNS/public destinations prohibited.
[Local measurement output](evidence/p1.7-loopback-measure.txt) is explicitly a
test fixture. Silent local responders exercised timeouts; injected DNS errors
avoided DNS calls. A second request to each successful local destination was
blocked by the persisted cooldown. No public NTP server was contacted in P1.7.

Acceptance also covered nanosecond/large-epoch boundaries, invalid inputs,
unsupported recordings, JSON stdout, file export equality, refusal to overwrite,
explicit overwrite, and original metadata after replay. Unit/integration tests
cover cleanup, ignored peer/originate packets with unchanged deadlines,
discontinuities, cooldown restart/concurrency/corruption, backoff, control blocks,
valid-only summaries, partial/interrupted batches, and stable diagnostic codes.

The archived P1.3 capture still yields +81.0434325 ms offset and 78.664213 ms
RTT; live truth/error remain `null`. Original and packaged capture SHA-256:
`42a57bc9023c5015e382e0b32d2c89557e5c95c6b1c94a6884aec7418d6d6cb0`.
Its original date is preserved; replay does not imply renewed interoperability.

## Corrections and packaging warning

- **Polling:** a brief competing state lock caused `finish()` to discard a
  timeout backoff or control block. Outcome writes now wait for the short state
  transaction. Reservations/reads remain nonblocking; no network wait holds a lock.
- **Replay:** a recording with a self-consistent but excessive wall/monotonic
  discrepancy was accepted. Replay now invokes the shared live interval guard.
  New exports store the actual positive `discontinuity_threshold_ns`; missing
  legacy values assume the documented 5 ms default without changing old bytes.
- **Packaging:** reproduced `SetuptoolsDeprecationWarning: project.license as a
  TOML table is deprecated` in a temporary copy using the former license table.
  Its source is setuptools `config/_apply_pyprojecttoml.py:82`. Replaced the table
  with `license = "MIT"` and `license-files = ["LICENSE"]`; raised only the build
  backend minimum to 77.0.3, following the [PyPA guidance](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license).
  New metadata is version 2.4 with `License-Expression: MIT` and
  `License-File: LICENSE`; license bytes/copyright are unchanged. Both new build
  logs contain no warnings or deprecations.

No calculation, packet, transport, experiment, or CLI feature was refactored.
Modified implementation files: `core/polling.py`, `experiments/replay.py`,
`serialization.py`, `pyproject.toml`; regression cases in `test_polling.py` and
`test_recordings.py`. Documentation changes: README, architecture, plan, demo
runbook, this report, team review, and the three accompanying P1.7 evidence files.

## Rehearsal, assumptions, and remaining limits

The [offline transcript](evidence/p1.7-cli-rehearsal.txt) contains six successful
commands (five recommended plus optional reverse asymmetry), 340 output lines,
351 lines including command separators, executing in approximately 0.28 s.
Reading this verbatim will exceed 3–4 minutes. The revised runbook uses a single
equal-increase delay comparison and highlights result lines; its 3:40 narration
budget is an estimate. A human timed talk and projector check remain pending.

Known limits: unauthenticated 48-byte NTPv4 only; era inference needs a nearby
date; software timestamps and unknown one-way transit cannot establish accuracy;
ideal equal-rate simulations, step correction only. System DNS and local
filesystem waits are outside a hard UDP response deadline. Outcome persistence
can wait behind another local state transaction. Polling is a small per-user
JSON/lock guard, not a distributed service: cooperating callers must share state;
cross-process forward clock jumps can shorten cooldowns. Windows live locking
fails closed. Other Python versions/platforms and current public connectivity
were not tested here. Persistent control blocks require operator policy review.

Legacy custom clock thresholds cannot be recovered; P1.7 assumes 5 ms when
missing. Older strict loaders can reject new threshold-bearing exports; the
current loader accepts both. Replay verifies consistency, not authenticity.

The backend is ready for team evaluation using [TEAM_REVIEW.md](TEAM_REVIEW.md).
P1.7 stops here. Phase 2 review, FastAPI/React, frontend scaffolding, slides,
OS clock modification, commits, and pushes have not been performed.
