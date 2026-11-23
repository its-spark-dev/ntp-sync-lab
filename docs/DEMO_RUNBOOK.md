# CLI demonstration runbook

Status update (2026-11-23): Phase 2 team approval reported complete; P3.1 API only is authorized. The rehearsal evidence below remains the historical P1.7 CLI run. Commands below were
executed from a clean installed wheel with networking forbidden. No new public
probe, slides, API, or frontend was created. Use [TEAM_REVIEW.md](TEAM_REVIEW.md)
for the 10–15 minute hands-on review and
[BACKEND_VALIDATION.md](BACKEND_VALIDATION.md) for test/build evidence.

## Setup and presentation strategy

Use Python 3.11+ and the README installation steps, then:

```sh
source .venv/bin/activate
ntp-sync-lab --help
ntp-sync-lab scenarios list
```

`python -m ntp_sync_lab` is equivalent. Packaged scenarios and the real P1.3
recording work outside the checkout. Use a wide terminal, readable font, and
pre-entered command history. Leave calculation details available for questions;
point to the result lines instead of reading every section aloud.

The six-command offline rehearsal, including optional reverse asymmetry,
produced 340 output lines and took about 0.28 seconds of command execution.
That is not a human presentation time. Full output is too verbose to read
within four minutes. The five-command plan below has an estimated **3:40**
focused narration budget. Human spoken timing and projector readability still
need verification; a classroom rehearsal is not claimed.

## Five-command classroom sequence

### 0:00–0:55 — Archived real exchange

```sh
ntp-sync-lab replay --scenario captured-public-ntp
```

Say: “This is **REPLAY of an original LIVE exchange**, captured on November 15,
2026 at 09:30:25.203822 UTC. No request is being sent now. T1 and T4 belong to
the client; T2 and T3 to the server. The estimate is server minus client:
**+81.0434325 ms**, with **78.664213 ms** network RTT. True offset and error
are unknown.” Point out the offset formula once. Do not infer chronological
order by comparing timestamps from different clocks.

### 0:55–1:30 — Symmetric delay comparison in one command

```sh
ntp-sync-lab delay --preset symmetric-low --increments-ms 0 60
```

Use the compact comparison at the end. One-way delays rise **20/20→80/80 ms**;
RTT rises **40→160 ms**, while truth/estimate remain **+100 ms**, error **0**.
Say: “This is a simulation with known truth. Equal delays can get much larger
without adding bias in this ideal model.”

### 1:30–2:10 — Asymmetric delay

```sh
ntp-sync-lab delay --preset asymmetric-forward
```

Point to inputs and results: **60/20 ms**, true offset **+100 ms**, estimate
**+120 ms**, error **+20 ms**, RTT **80 ms**. Say: “Half the one-way difference
becomes estimation error. RTT alone does not determine accuracy.”

### 2:10–3:20 — Apply correction to the virtual clock

```sh
ntp-sync-lab sync
ntp-sync-lab sync --forward-ms 60 --reverse-ms 20
```

Focus on the before/after error and correction lines. Initial virtual client
error is **+120 ms** (client minus reference), so true NTP offset is **−120 ms**.
Symmetric correction **−120 ms** leaves **0**; asymmetric correction **−100 ms**
leaves **+20 ms**. Say: “We add the estimated offset to virtual time. Both
snapshots refer to the same reference instant. Bias in the measurement remains
after correction. This changes only the virtual clock.”

### 3:20–3:40 — State limits

“These are unauthenticated software timestamps. Live one-way delay and true
clock offset are unknown. Our simulation assumes equal clock rates and applies
one step, without drift or gradual discipline.” Reserve remaining time for
questions. Verify readable projection and spoken timing before the final talk.

## Optional review/Q&A comparisons

```sh
ntp-sync-lab sync --forward-ms 20 --reverse-ms 60
ntp-sync-lab delay --round-trip-ms 80 --sweep-points 3
```

Reverse synchronization applies **−140 ms**, leaving **−20 ms**. The sweep
holds RTT at 80 ms for 0/80, 40/40, 80/0 ms paths, giving errors −40/0/+40 ms.
These strengthen the explanation but are outside the five-command time budget.
Full reviewed output is saved in the
[offline rehearsal transcript](evidence/p1.7-cli-rehearsal.txt).

## Optional real request and explicit fallback

The archived sequence needs no DNS or sockets. An actual classroom request
needs a separately requested preflight and server-policy review. P1.7 made none.

```sh
ntp-sync-lab measure --server pool.ntp.org --count 1 --timeout-seconds 3 --output artifacts/preflight.json
```

Keep the shared minimum 64-second destination interval and persisted timeout
backoff. A control response stops that target for operator review. Do not reset
polling state, rotate targets to force success, or wait through a batch on stage.
DNS and local filesystem operations have no hard UDP-timeout bound. Matching
peer/originate values is not authentication; a small host offset is legitimate.

If a permitted request times out or is unsupported, leave its failure visible
and explicitly select `replay --scenario captured-public-ntp`. Do not call the
saved result a new live request. Local P1.7 UDP fixtures validate socket behavior,
not present public-server reachability.

## JSON and file review

```sh
ntp-sync-lab delay --preset asymmetric-forward --format json --output artifacts/delay.json
ntp-sync-lab replay --file artifacts/delay.json --format json
```

`--output` writes JSON regardless of stdout format. Existing paths are protected;
`--overwrite` explicitly replaces them. Diagnostics go to stderr. If export fails
after execution, text still shows the result or JSON retains `partial_result`;
do not repeat a public request to recreate a failed export. Invalid recordings
exit 4 without a traceback. Files are limited to 1 MiB and nesting depth 12.

Replay wraps the unchanged original document, retaining its capture date and
source. New replay time is separate. The packaged public recording is the exact
P1.3 evidence; synthetic scenarios carry model-definition metadata. Recorded
failures remain failures. Validation proves consistency, not authenticity.

For individual examples see [recorded exchange](examples/replay-public.txt),
[delay](examples/delay.txt), [synchronization](examples/sync.txt), and
[replayable JSON](examples/delay-asymmetric.json). P1.7 resolved the prior
license-table warning. Team approval is now recorded in [TEAM_REVIEW.md](TEAM_REVIEW.md).
Spoken/projected timing has not been independently measured here; React work
remains pending. The P3.1 API is documented in [API.md](API.md).
