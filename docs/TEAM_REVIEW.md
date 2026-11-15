# Backend team review

P1.7 verdict: **PASS — ready for hands-on backend review**. Team approval has
not occurred. No API, React, slides, or operating-system clock changes are part
of this delivery. Start here; supporting evidence is in
[BACKEND_VALIDATION.md](BACKEND_VALIDATION.md).

## Install and start

From the repository, with Python 3.11+:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -ra
source .venv/bin/activate
ntp-sync-lab --help
python -m ntp_sync_lab scenarios list
```

Expected: 563 passing tests; ten scenarios. The runtime uses only the standard
library. Both entry points run the same CLI. Fresh non-editable wheel execution
was also validated outside the repository. Live polling requires POSIX locking;
the tested platform is macOS with Python 3.11.14.

Allow 10–15 minutes to inspect the following outputs and ask questions. The
separate [classroom runbook](DEMO_RUNBOOK.md) targets a focused 3–4 minute talk.

## 1. Real four-timestamp exchange, preserved offline

```sh
ntp-sync-lab replay --scenario captured-public-ntp
```

This replays the genuine P1.3 public capture from **2026-11-15 09:30:25.203822 UTC**.
It sends no request. Expect **REPLAY (original LIVE; no request sent)**,
offset **+81.0434325 ms**, RTT **78.664213 ms**, and unknown truth/error.
The raw response is 48-byte NTPv4, mode 4, stratum 2.

T1/T4 belong to the client; T2/T3 belong to the server. Offset means server
minus client: positive means the client is behind. Verify
`((T2−T1)+(T3−T4))/2` and `RTT=(T4−T1)−(T3−T2)` in the worked output.
This proves a real exchange was captured and can be recalculated; it does not
prove its absolute UTC accuracy or authenticate the server.

## 2. Delay and offset accuracy

```sh
ntp-sync-lab delay --preset symmetric-low --increments-ms 0 60
ntp-sync-lab delay --preset asymmetric-forward
ntp-sync-lab delay --round-trip-ms 80 --sweep-points 3
```

All are **SIMULATION** with known server-minus-client truth +100 ms.

| Forward / reverse ms | RTT ms | Estimate ms | Estimate minus truth ms |
| --- | --- | --- | --- |
| 20 / 20 | 40 | +100 | 0 |
| 80 / 80 | 160 | +100 | 0 |
| 60 / 20 | 80 | +120 | +20 |
| 0 / 80 (sweep) | 80 | +60 | −40 |
| 40 / 40 (sweep) | 80 | +100 | 0 |
| 80 / 0 (sweep) | 80 | +140 | +40 |

Higher symmetric delay increases RTT without bias in this ideal model.
At fixed RTT, changing asymmetry changes accuracy: `error=(df−dr)/2`.
Processing time cancels from the network RTT and offset estimate.

## 3. Virtual clock synchronization

```sh
ntp-sync-lab sync
python -m ntp_sync_lab sync --forward-ms 60 --reverse-ms 20
ntp-sync-lab sync --forward-ms 20 --reverse-ms 60
```

The virtual client starts **+120 ms ahead** of the reference, so the true NTP
offset is **−120 ms**. Expected corrections/residual client errors:

| Forward / reverse ms | Add to virtual clock ms | Residual client minus reference ms |
| --- | --- | --- |
| 20 / 20 | −120 | 0 |
| 60 / 20 | −100 | +20 |
| 20 / 60 | −140 | −20 |

Before/after snapshots refer to the same reference instant. A negative step can
move virtual time backward. This demonstrates measurement bias surviving a
correction; it neither changes the OS clock nor implements drift/slew discipline.

## JSON, export, failures, and source labels

```sh
ntp-sync-lab delay --preset asymmetric-forward --format json --output artifacts/review-delay.json
ntp-sync-lab replay --file artifacts/review-delay.json --format json
ntp-sync-lab sync --client-offset-ms 0.0000001 --format json
```

The last command deliberately exits 2: sub-nanosecond input is rejected. Reusing
an export path exits 4; use `--overwrite` only for an intentional replacement.
JSON stdout is separate from stderr status. Schema 1 uses exact decimal strings
for ns values; unknown live truth/error stays `null`. Replay preserves the
entire original document and capture date inside its wrapper.

**LIVE** means an actual UDP exchange (including a labeled local test fixture),
**SIMULATION** means deterministic modeled conditions, and **REPLAY** means saved
data with the original source shown. Replay validates consistency, not authenticity.
Help, scenarios, delay, sync, and replay require no DNS or sockets.

The real command is `ntp-sync-lab measure --server pool.ntp.org --count 1
--timeout-seconds 3` on one line. It is optional for review and was **not** run
in P1.7. Retain the shared 64-second destination cooldown, timeout backoff, and
control-response stop; never reset state to force another request.

## Limits and approval questions

Software timestamp precision does not establish accuracy; unknown live
asymmetry remains unknown. Only the 48-byte NTPv4 profile is supported, without
extensions, NTS, or authentication. Era inference needs a date within about
68 years. DNS and local filesystem operations have no hard UDP-timeout bound.
Polling coordination assumes cooperating processes sharing one local state
directory; another process's forward wall-clock jump can shorten a cooldown.
Windows live locking and other Python/platform combinations are unverified.
New exports include the clock-discontinuity threshold; old recordings assume
the 5 ms default, and older strict loaders may reject the added field.

- [ ] Can a teammate explain the two offset signs and own each T1–T4 correctly?
- [ ] Do equal RTT and different asymmetry give the expected errors?
- [ ] Does virtual correction show both zero and signed nonzero residuals?
- [ ] Are LIVE/SIMULATION/REPLAY and unknown live truth unmistakable?
- [ ] Do export/replay and deliberate failure messages work without source reading?
- [ ] Are the documented protocol, polling, timing, and model limits acceptable?
- [ ] Does a human rehearsal fit 3–4 minutes with readable projected output?
- [ ] Approve the backend explicitly before authorizing FastAPI/React work.

Record reviewer names, concerns, and a decision during the later team gate.
Passing tests and preparing this bundle do not constitute that approval.
