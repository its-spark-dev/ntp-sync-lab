# P3.4 — Integrated acceptance

**PASS for automated local integration; ready for owner review.** All three
interfaces, shared API/CLI calculations, controlled failures, cooldown, reset,
and offline playback were exercised. The G3 evidence is complete; this report
does not approve or start Phase 4. The existing presentation design is unchanged.

## Results

| Check | Result |
| --- | --- |
| Complete Python suite | **649 passed**, 5.05 s (634 existing + 15 integration cases) |
| Frontend unit/component tests | **40 passed** (39 existing + 1 regression) |
| Chromium browser tests | **56 passed**, 31.2 s (46 existing + 10 integration cases) |
| TypeScript/Vite production build | Pass |
| API type drift check / Prettier / whitespace check | Pass |

No failures or skips remain. Python suites reported no warnings. Browser logs
retain the environment-only NO_COLOR/FORCE_COLOR warning; no application defect
is inferred from it. Environment: macOS, Python 3.11.14/Pytest 9.2.0, Node 26.5.0,
React 19.3.1, TypeScript 5.9.3, Vite 7.3.8, Playwright 1.65.1. npm dependencies
and lockfile were not changed.

Commands from the repository:

```sh
.venv/bin/python -m pytest -ra
npm --prefix frontend run test
npm --prefix frontend run types:check
npm --prefix frontend run format:check
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Browser checks start isolated local development and static-release servers as
documented in [FRONTEND.md](FRONTEND.md). Ports 8000/5173/8001 must be free.
The Python public-network audit guard remains enabled in API subprocesses.
No public NTP request was made. No host OS clock was changed.

## Acceptance evidence

- **Three-tab journey:** load historical replay, run fixed-RTT delay comparison,
  inspect point 3 (+40 ms error), measure forward-heavy virtual time, reveal
  +20 ms residual, reset synchronization, and return to unchanged delay and
  archived exchange states. Exactly three user-initiated experiment POSTs occur;
  navigation, Apply, and reset do not create additional operations.
- **In-flight isolation:** switch tabs while a controlled measurement is pending,
  reset another experiment, and return. The live action remains disabled until
  that request finishes. Only one measurement request occurs. The result and
  cooldown survive further navigation and another tab's reset.
- **Cooldown:** a controlled 429 response with Retry-After disables the live
  action. Virtual browser time expires the displayed wait without real sleeps;
  no automatic retry occurs and the failure stays visible. Existing cases cover
  cached control blocks and server policy errors.
- **API/CLI parity:** twelve additional cases use the same payload values as the
  simulation UI: all four delay conditions, both sweep modes, five clock cases,
  and half-nanosecond correction. Full native documents match after removing
  nondeterministic result IDs/creation dates, including timestamps, metrics,
  source, parameters, assumptions, and timelines. Existing parity tests also run.
- **Live adapter parity:** independent fake-clock/transport executions through
  actual API and CLI entry points produce the same normalized single result,
  including raw packets, exact timestamps, diagnostics, and unknown truth/error
  as null. The CLI wraps that result in its native batch; the API returns a single
  result. Each controlled execution sends exactly one fixture datagram.
- **Shared persisted policy:** an API measurement blocks the CLI against the same
  numeric destination and temporary guard state. Advancing fake time permits a
  CLI attempt, which then blocks the API. Exactly two fixture sends occur.
  No actual public polling state is reset or bypassed.
- **Offline provenance:** API and CLI replay preserve an identical original
  archived document and LIVE origin. A browser workflow prohibits all external
  destinations while replay and both simulations use the local API. No external
  request is observed. Browser offline mode itself is not enabled because that
  would also cut off the required localhost API.
- **Existing regressions:** browser cases continue to cover timeout/failure
  preservation and explicit fallback, exact values, exports, half-ns snapshots,
  reset/stale input protection, keyboard tabs, reduced motion, 390px layouts,
  projector-sized wrapping, and Axe accessibility states on both dev/release.
  Python tests retain IPv4/IPv6 loopback, packet validation, state locking,
  clock discontinuity, cancellation shielding, timeout/backoff, and corruption.

## Corrected defect

A connection failure after successful startup left the cached green
“API connected” indicator visible. A new component test reproduced this before
correction. The indicator now reflects API_UNAVAILABLE failures or setup errors;
its existing styling and layout are unchanged. A browser regression verifies
that the error and the historical replay both remain visible, with no retry or
silent result substitution. The indicator reports observed state, not a periodic
health monitor. No calculation, wire, API policy, or CSS design changes were made.

Changed implementation: `frontend/src/App.tsx` only. Added/updated checks:
`frontend/src/App.test.tsx`, `frontend/tests/integrated.spec.ts`, and
`tests/integration/test_integrated.py`. Review status and links were updated in
README, architecture, implementation plan, and this report.

## Remaining limits and stop

This verifies local development and built static release with Chromium. Native
Safari/WebKit, physical projector readability, spoken classroom timing, and
current campus/public UDP reachability are not certified here. The archived
P1.3 capture remains historical; loopback/injected exchanges are not renewed
public interoperability evidence. API imports, health, catalogs, replay, and
simulations do not require public NTP access.

Unauthenticated 48-byte NTPv4, software timestamp uncertainty, unknown live
one-way delays/ground truth, nearby-date era inference, POSIX/shared-state
polling assumptions, unbounded system DNS/filesystem waits, and ideal step-only
simulations remain documented limitations. See [API.md](API.md) and
[SIMULATIONS.md](SIMULATIONS.md).

No unresolved integration blocker remains in the exercised scope. Stop after
P3.4 and await owner review. Phase 4 rehearsal, slides, portfolio work, public
probes, commits, and pushes have not been started by this task.
