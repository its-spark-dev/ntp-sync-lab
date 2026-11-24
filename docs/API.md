# P3.1 — Local HTTP API

Phase 2 review and unanimous backend approval were reported by the project
owner on **2026-11-23**. P3.1 implemented the API only. Follow-up: the authorized P3.2 React shell and
Real NTP Exchange are now documented in [FRONTEND.md](FRONTEND.md); other
experiment interfaces remain pending. No commit or push is
part of this task.

## Install and run

From the activated repository environment, with Python 3.11+:

```sh
python -m pip install -e '.[web]'
python -m uvicorn ntp_sync_lab.api.app:app --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation or
`http://127.0.0.1:8000/openapi.json` for the actual schema. Startup, documentation,
health, catalogs, simulations, and replay never request public NTP time.
Only explicitly submitting a measurement does so.

Use **one process/worker**, bound to loopback. The app accepts localhost/127.0.0.1
Host headers and rejects cross-origin mutation requests. CORS is not enabled.
There is no authentication or public deployment support. P3.2 provides a local development proxy and optional same-origin static serving;
see [FRONTEND.md](FRONTEND.md). The proxy preserves foreign origins for rejection.

## Endpoints

| Method and path | Body / result |
| --- | --- |
| `GET /api/v1/health` | Local status, schema version |
| `GET /api/v1/config` | Server IDs, units/bounds, live busy status, observed cooldown |
| `GET /api/v1/scenarios` | Ten existing scenario definitions with original source labels |
| `GET /api/v1/recordings` | Packaged historical public capture catalog |
| `POST /api/v1/measurements` | `{"server_id":"pool","timeout_seconds":3}` → one native live result |
| `POST /api/v1/experiments/delay` | Preset/custom delays, optionally a sweep → native simulation result/series |
| `POST /api/v1/experiments/sync` | Initial virtual error and delays → native synchronization result |
| `POST /api/v1/replays` | Exactly one `recording_id` or `scenario_id` → preserved replay wrapper |

Server IDs map to operator-configured targets, default `pool` → `pool.ntp.org`.
The browser cannot submit arbitrary hosts, ports, file paths, or recording uploads.
`create_app(servers=..., live_service=...)` supports operator configuration and
injected test services, not browser-controlled destinations.

### Offline requests

With the server running, in another terminal:

```sh
curl http://127.0.0.1:8000/api/v1/health

curl -X POST http://127.0.0.1:8000/api/v1/experiments/delay \
  -H 'Content-Type: application/json' \
  -d '{"preset":"asymmetric-forward"}'

curl -X POST http://127.0.0.1:8000/api/v1/experiments/delay \
  -H 'Content-Type: application/json' \
  -d '{"round_trip_ms":"80","sweep_points":3}'

curl -X POST http://127.0.0.1:8000/api/v1/experiments/sync \
  -H 'Content-Type: application/json' \
  -d '{"client_offset_ms":"120","forward_ms":"60","reverse_ms":"20"}'

curl -X POST http://127.0.0.1:8000/api/v1/replays \
  -H 'Content-Type: application/json' \
  -d '{"recording_id":"captured-public-ntp"}'
```

Delay: estimated +120 ms versus true +100 ms, error +20 ms. Fixed-RTT sweep:
RTT 80 ms and errors −40/0/+40 ms. Sync: correction −100 ms, final virtual
client error +20 ms. Replay: original capture date unchanged, estimated
+81.0434325 ms and RTT 78.664213 ms; unknown live truth/error stays `null`.

Delay custom fields: `true_offset_ms`, `forward_ms`, `reverse_ms`,
`processing_ms`, `reference_unix_ns`. A preset excludes custom base fields.
`round_trip_ms` plus `sweep_points` (default 9) excludes preset/individual
one-way delays and `increments_ms`. Equal-increase sweeps use an increasing
`increments_ms` list with a custom base or preset. Engine limits are unchanged:
offset ±60000 ms, each delay 0–2000 ms, processing 0–500 ms, 2–200 sweep points,
fixed RTT at most 2000 ms. Sync supports only `mode: "step"`.

## Precision and contracts

Duration inputs are **decimal millisecond strings**, with at most six fractional
places. `reference_unix_ns` is an integer decimal string. Timeout alone is a
JSON number (0.1–10 seconds); point counts are JSON integers. HTTP numeric input
strings are limited to 128 characters. Unknown fields, numeric millisecond
values, booleans for timeout/point counts, nonfinite values, and invalid
combinations are rejected rather than silently coerced.

The API invokes existing services and serializers; no NTP calculations were
reimplemented. Native schema-1 envelopes, exact string timestamps/offsets,
source labels, and `null` truth values are preserved. Simulation IDs and creation
dates naturally differ across executions. Measurement returns a **single result**,
whereas CLI measurement wraps attempts in its existing batch envelope.

OpenAPI explicitly types the quartet, exact offsets, nullable truth/error, series
points, and synchronization snapshots/timeline. Additional live diagnostic fields
and original replay recordings remain JSON-compatible structures so the original
contracts are not filtered or rewritten. Types for those diagnostic structures
can be refined with frontend requirements later. No TypeScript files are created
in P3.1; use the actual OpenAPI schema as the source for later generated types:

```sh
curl http://127.0.0.1:8000/openapi.json -o /tmp/ntp-sync-lab-openapi.json
```

## Concurrency, cooldown, and failures

One live operation is admitted per app instance. It runs in a bounded thread
worker, keeping the event loop available; competing requests return 429 without
queueing another measurement. The worker owns the slot through completion and
state persistence, including request cancellation. There is no retry, automatic
polling, or new attempt after browser disconnection. The existing one-datagram
client and shared POSIX polling guard enforce destination spacing/backoff/control
blocks across CLI/API calls. Offline routes do not acquire the live slot.

`config` never resolves DNS. Before the app has observed a numeric target, its
cooldown state is **unknown**, including after restart; it is not a claim that
persisted CLI cooldown has expired. After resolution it reads the shared guard
for that observed destination. DNS changes can select a different destination
on a later request; measurement always revalidates its actual destination.

Errors use `{"schema_version":"1","error":{"code":...,"message":...,"details":...}}`:

| Status | Meaning |
| --- | --- |
| 422 | Invalid input/body |
| 404 | Unknown configured/catalog ID or route |
| 429 | Busy/cooldown; `Retry-After` and retry metadata |
| 504 | UDP deadline expired |
| 502 | Unsupported/malformed/unusable upstream reply, control response, timing failure |
| 503 | DNS/network/polling-state unavailable or corrupt packaged recording |
| 500 | Unexpected failure, sanitized message |

Cross-origin mutation requests return 403; the Host middleware rejects invalid
hosts with its standard 400 response. These checks are local usage safeguards,
not authentication. No permissive CORS or arbitrary destination proxy exists.

Existing limitations remain: software timing uncertainty, no authentication,
48-byte NTPv4 profile only, and unknown live ground truth. DNS and filesystem
waits are outside the UDP timeout. Never bypass polling-state safeguards to
repeat a probe. On control responses, stop and review server policy.

## Validation

```sh
python -m pip install -e '.[test,web,web-test]'
python -m pytest tests/integration/test_api.py -q
python -m pytest -ra
```

Validated on Python 3.11.14/macOS: **69 API tests passed; 632 total tests passed**
(563 existing + 69 API), no failures, skips, or warnings; final full run 4.11 s.
CLI-only environments can omit web extras: API tests skip as a module, while
core and CLI imports continue without optional dependencies.

Evidence includes exact normalized CLI parity for delay, both sweep modes, sync,
half-ns and large timestamps; live serializer parity and null truth; archived
replay preservation; strict inputs; error/status mapping; persisted cooldown,
timeout/control state; concurrent requests, responsive health, and cancellation
without duplicate sends. Offline routes run with DNS/socket creation forbidden.
An actual local UDP responder exercises the API measurement path. The existing
suite continues to forbid public networking.

A wheel built successfully with the new optional extras and API modules. Its
non-editable installation in a temporary target, outside the checkout, started
Uvicorn on an inherited ephemeral loopback socket and served health, OpenAPI,
catalogs, and replay over real HTTP. The environment supplied the optional
libraries; this was not a fresh dependency-free environment. Tested versions:
FastAPI 0.165.0, Starlette 1.10.0, Pydantic 2.14.4, AnyIO 4.16.0, Uvicorn 0.54.0,
HTTPX 0.28.1. HTTPX ASGI transport avoids the current Starlette TestClient HTTPX
deprecation. Other compatible dependency/platform combinations are not certified.

Concurrency cancellation is tested with an AnyIO cancellation scope; browser
UI and navigation behavior will be checked during frontend integration.
No new public NTP probe or OS clock modification occurred. P3.1 was reviewed before P3.2 began; the historical validation counts here
remain those of the API-only task. Current frontend evidence is in FRONTEND.md.

Implementation references: [FastAPI concurrency](https://fastapi.tiangolo.com/async/)
and [response models](https://fastapi.tiangolo.com/tutorial/response-model/).
