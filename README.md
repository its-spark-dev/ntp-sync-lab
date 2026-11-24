# NTP Sync Lab

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![MIT License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![CLI available](https://img.shields.io/badge/Interface-CLI%20%2B%20Web-475569)](#quick-start)
[![Offline examples](https://img.shields.io/badge/Examples-Offline-0f766e)](#quick-review-commands)

**Explore how NTP estimates time, why network asymmetry affects accuracy, and what remains after a clock correction.**

NTP Sync Lab is an educational Python application with three experiments:

| Experiment | What you explore |
| --- | --- |
| Real NTP exchange | Inspect four timestamps from a genuine recorded exchange, or make an optional live request. |
| Network delay | Compare symmetric and asymmetric paths with a known clock offset. |
| Virtual clock correction | Apply the estimated offset and inspect the remaining clock error. |

The standalone CLI, optional HTTP API, and React **Real NTP Exchange** interface
are available now. The other two web experiment tabs are coming later. All five quick review commands below work **offline** and
leave your operating-system clock unchanged.

## Quick Start

You need **Python 3.11 or later** and Git. The commands below use macOS/Linux
shell syntax. If your Python executable is named `python3`, check that
`python3 --version` reports 3.11+ and use it instead of `python3.11`.

```sh
git clone https://github.com/its-spark-dev/ntp-sync-lab.git
cd ntp-sync-lab

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

ntp-sync-lab --help
```

The runtime uses only Python's standard library. Run the following examples
from this activated environment. In a new terminal, return to the repository
and run `source .venv/bin/activate` again.

If `ntp-sync-lab` is not found, use `python -m ntp_sync_lab` with the same
arguments. For example:

```sh
python -m ntp_sync_lab replay --scenario captured-public-ntp
```

Live measurements require POSIX file locking; Windows live support is not yet
implemented. The documented setup and validation environment is macOS.

## Quick Review Commands

Run these commands one at a time. Start with **Inputs & Conditions**, then
**Results** and **Conclusion**. The timestamps and worked calculations explain
how each result was obtained.

```sh
# 1. Previously captured real NTP exchange
ntp-sync-lab replay --scenario captured-public-ntp

# 2. Symmetric delay
ntp-sync-lab delay --preset symmetric-low

# 3. Asymmetric delay
ntp-sync-lab delay --preset asymmetric-forward

# 4. Clock correction without residual error
ntp-sync-lab sync --client-offset-ms 120 \
  --forward-ms 20 --reverse-ms 20

# 5. Clock correction with residual error
ntp-sync-lab sync --client-offset-ms 120 \
  --forward-ms 60 --reverse-ms 20
```

### What to look for

| Command | Expected result | What it demonstrates |
| --- | --- | --- |
| **1 · Recorded exchange** | Estimated offset **+81.0434325 ms**; network RTT **78.664213 ms**; true offset and error **unknown**. | Four timestamps give an estimate; a live exchange does not reveal the true one-way delays or clock error. |
| **2 · Symmetric delay** | True offset **+100 ms**; estimate **+100 ms**; error **0 ms**; RTT **40 ms**. | Equal forward/reverse delays produce an unbiased estimate in the ideal model. |
| **3 · Asymmetric delay** | True offset **+100 ms**; estimate **+120 ms**; error **+20 ms**; RTT **80 ms**. | A 60/20 ms path biases the estimate by half the difference: **+20 ms**. |
| **4 · Symmetric correction** | Initial client error **+120 ms**; correction **−120 ms**; residual **0 ms**. | The virtual clock aligns with the reference after correction. |
| **5 · Asymmetric correction** | Initial client error **+120 ms**; correction **−100 ms**; residual **+20 ms**. | Measurement bias remains after correction; the virtual client is still ahead. |

Command 1 shows **REPLAY (original LIVE; no request sent)**. It preserves a
public NTP exchange captured on **2026-11-15 at 09:30:25.203822 UTC**; it does
not contact a server now. Commands 2–5 show **SIMULATION**, using known inputs
rather than public-server observations.

Each experiment prints seven sections: objective, inputs/conditions, T1–T4,
calculations, results, assumptions/limitations, and conclusion. To preview full
output, see the [recorded exchange](docs/examples/replay-public.txt),
[delay example](docs/examples/delay.txt), and
[clock correction example](docs/examples/sync.txt).

## Reading the Timestamps and Signs

| Timestamp | Event | Clock |
| --- | --- | --- |
| T1 | Client sends the request | Client |
| T2 | Server receives the request | Server |
| T3 | Server sends the response | Server |
| T4 | Client receives the response | Client |

```text
Estimated NTP offset = ((T2 − T1) + (T3 − T4)) / 2
Network RTT          = (T4 − T1) − (T3 − T2)
```

**NTP offset means server minus client.** A positive estimate says the client
is behind; adding that estimate advances the client clock.

**Client error means client minus reference.** In commands 4–5, the virtual
client starts **+120 ms ahead**, so its true NTP offset is **−120 ms**. Adding
the estimated correction leaves either zero error or an asymmetric-path bias.
The before/after virtual snapshots refer to the same reference instant.

The model assumes clocks run at equal rates with fixed delays. Server processing
time cancels from both equations. Estimated offset error is
`(forward delay − reverse delay) / 2`; RTT alone does not determine accuracy.

## Try More Comparisons

```sh
# Higher symmetric delay: RTT grows to 160 ms, offset error stays zero
ntp-sync-lab delay --preset symmetric-high

# Same 80 ms RTT, different asymmetry: errors −40, 0, +40 ms
ntp-sync-lab delay --round-trip-ms 80 --sweep-points 3

# Reverse the asymmetric path: correction −140 ms, residual −20 ms
ntp-sync-lab sync --client-offset-ms 120 --forward-ms 20 --reverse-ms 60

# Discover saved scenarios and command options
ntp-sync-lab scenarios list
ntp-sync-lab delay --help
ntp-sync-lab sync --help
```

Sweeps show one worked example followed by a comparison table. JSON output
retains every point and its timestamps.

## Save Results and Replay Them

```sh
ntp-sync-lab delay --preset asymmetric-forward --format json --output artifacts/delay.json
ntp-sync-lab replay --file artifacts/delay.json
```

`--format json` produces machine-readable stdout. `--output` always saves JSON,
even with text stdout; its parent directory is created when needed. An existing
file is protected unless you explicitly add `--overwrite`. Status messages go
to stderr, keeping JSON stdout parseable.

Schema-1 recordings store nanosecond timestamps and durations as decimal strings,
preserving exact values. Unknown live truth/error is `null`. Replay validates
the recording and retains the original source and capture date; it establishes
internal consistency, not authenticity.

## Optional: Make a Live NTP Request

The quick review above needs no network access. To measure a real server:

```sh
ntp-sync-lab measure --server pool.ntp.org --count 1 --timeout-seconds 3
```

Look for **LIVE**, the responding server, T1–T4, estimated offset, and network
RTT. The actual numbers depend on your machine and network; the saved example
is not an expected live result. True offset and estimation error remain unknown.
If UDP is blocked, resolution fails, or a response is unsupported, the CLI
reports that outcome. Choose replay explicitly to continue offline.

Public requests have a **minimum 64-second destination cooldown**, persisted
across cooperating local CLI invocations. Timeouts increase backoff; a server
control response blocks that target for policy review. Do not delete polling
state or change its location to force another request. DNS and local filesystem
operations are outside the UDP response timeout. See the
[interoperability report](docs/INTEROPERABILITY.md) for the original capture.

## Web Interface (P3.2)

The React app has Safari-inspired horizontal tabs and translucent glass surfaces.
Only **Real NTP Exchange** is implemented; the other two tabs show preparation
notices. No measurement or replay starts automatically.

Start the API in one terminal:

```sh
python -m pip install -e '.[web]'
python -m uvicorn ntp_sync_lab.api.app:app --host 127.0.0.1 --port 8000 --workers 1
```

With Node.js 22.12+ installed, start the frontend in another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173** and select **Load captured exchange** for the
offline example. Inspect the source badge, offset, RTT, timestamp table, and
formula details. **Measure once** explicitly makes a real NTP request and retains
the existing cooldown policy. Playback is illustrative, not a packet trace.

See the [frontend guide](docs/FRONTEND.md) for production build/same-origin
serving, keyboard controls, API type generation, screenshots, and tests.

## Optional HTTP API (P3.1)

```sh
python -m pip install -e '.[web]'
python -m uvicorn ntp_sync_lab.api.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000/docs` to inspect and try the API. Opening the page
or calling health/scenario/replay endpoints sends no NTP request. An explicit
`POST /api/v1/measurements` does, using a configured server ID and the existing
cooldown policy. Use one worker and loopback binding for this local lab.

For setup, offline request examples, OpenAPI export, error handling, and tests,
see the [API guide](docs/API.md). There is no React application yet.

## Development and Validation

```sh
# From the activated repository environment
python -m pip install -e '.[test]'
python -m pytest -ra
```

P1.7 validation recorded **563 passing tests** in both the project environment
and a clean wheel installation, plus **50 installed CLI acceptance checks**.
Tests use deterministic fixtures and local UDP responders; they do not need
public NTP servers. See the [validation report](docs/BACKEND_VALIDATION.md)
for the tested environment, corrections, packaging checks, and evidence.

The mathematical core uses integer Unix nanoseconds and exact `Fraction`
arithmetic. CLI, networking, and presentation remain outside the pure
calculation layer. Only virtual time changes during synchronization experiments.

### Current Limits

- Supports the **48-byte NTPv4 client/server profile**; extensions and other
  versions/modes are reported as unsupported. No NTS or cryptographic authentication.
- Software timestamp precision does not establish measurement accuracy.
  Matching peer/originate fields correlates a reply with its request.
- Timestamp era inference requires a reference date within about 68 years.
- Polling coordination is local, requires shared state and POSIX locks, and
  assumes stable wall time across processes; it is not a distributed limiter.
- Simulations use ideal equal-rate clocks and step correction. Drift, gradual
  slewing, full NTP discipline, and host clock control are outside scope.

## Documentation

| Document | Use it for |
| --- | --- |
| [Team review](docs/TEAM_REVIEW.md) | A hands-on checklist and expected results for all three experiments. |
| [Demo runbook](docs/DEMO_RUNBOOK.md) | A focused five-command presentation with an estimated 3–4 minute narration budget. |
| [Backend validation](docs/BACKEND_VALIDATION.md) | Test results, independent calculations, packaging, and remaining risks. |
| [Architecture](docs/ARCHITECTURE.md) | Layer boundaries, protocol decisions, and data contracts. |
| [Implementation plan](docs/IMPLEMENTATION_PLAN.md) | Development phases and review gates. |

Backend validation and team approval are complete. P3.1 adds the optional API;
The P3.2 React shell and Real NTP Exchange tab are complete; the other two
experiment interfaces remain a separate next step. Human presentation timing and projector readability
still need rehearsal.

## License

[MIT](LICENSE) · Copyright © 2026 Sang Park
