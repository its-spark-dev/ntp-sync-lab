# P3.3 — Delay and virtual clock interfaces

The existing React app now implements **Network Delay & Accuracy** and
**Clock Synchronization** alongside Real NTP Exchange. P3.2 and its presentation
design were approved before this task. This work stops at P3.3: **P3.4 integrated
acceptance and its G3 gate have not started or been claimed**.

## Start

Follow [FRONTEND.md](FRONTEND.md) for the existing Python API + Vite development
setup or same-origin release build. No new dependency or backend endpoint was
needed. Tabs use the same navigation, white content surfaces, blue actions,
48px desktop headings, approximately 32–40px primary metrics, focus treatment,
and responsive layout established in the first tab.

Opening a tab does not run an experiment. Run buttons submit a single request
to the existing Python API. Decimal inputs stay strings; Python validates units,
limits, generates timestamps, and performs every authoritative calculation.
No simulation modifies a public network or the operating-system clock.

## Network Delay & Accuracy

1. Open the tab and keep **Single exchange** as the comparison.
2. Choose a **Delay preset**, then select **Run delay simulation**.
3. Compare true offset, estimated offset, estimation error, and network RTT.
4. Expand **Modeled timestamps & calculations** to inspect T1–T4 ownership,
   exact Unix ns, UTC, and formula substitutions.

Expected results (all ms, truth +100, processing 5):

| Preset | Forward / reverse | Estimate | Error | RTT |
| --- | --- | --- | --- | --- |
| Symmetric low | 20 / 20 | +100 | 0 | 40 |
| Symmetric high | 80 / 80 | +100 | 0 | 160 |
| Asymmetric forward | 60 / 20 | +120 | +20 | 80 |
| Asymmetric reverse | 20 / 60 | +80 | −20 | 80 |

Custom true offset, forward/reverse delay, and processing fields are available.
Editing a field selects Custom; choosing a preset restores its baseline values.
The Run action appears after preset selection, so the usual classroom comparisons
can be launched without scrolling through every custom input.

**Increase both delays** submits the base scenario plus an equal-increase sweep
with increments `["0","60"]`. Starting at 20/20, the comparison rows are 20/20
and 80/80 ms: RTT rises 40→160 ms while offset error stays zero. This intentionally
small two-point comparison is for the short demonstration; the CLI supports
more custom increment grids.

**Fixed RTT asymmetry** submits a total RTT and 3/5/9 points to the existing sweep.
Default 80 ms/3 points gives forward/reverse 0/80, 40/40, 80/0 ms; estimates
+60/+100/+140 ms and errors −40/0/+40 ms. Every row retains RTT 80 ms. Select a
point to inspect its metrics, diagram bars, and timestamps. All table values and
points come from Python; JavaScript does not construct new timing quartets.

The comparison chart plots known truth, the NTP estimate, and signed error on a
shared zero-centered scale. Exact string values are printed alongside the bars.
Floating-point conversion is used only for illustrative bar positions. The table
retains every point. JSON export includes the **complete native series**, even
when a single point is selected for inspection, and is compatible with CLI replay.

## Clock Synchronization

1. Choose a **Clock scenario**, or enter a signed initial client error and delays.
2. Select **Measure virtual clock**. This calls `/api/v1/experiments/sync`, not the
   live measurement endpoint. It shows the initial error and estimated correction.
3. Select **Apply correction** to reveal the Python-provided after snapshot and
   residual error. The browser changes presentation stage only; it performs no
   correction arithmetic and sends no second request.
4. Expand **Virtual clock snapshots & timeline** for the common reference instant,
   exact virtual clock readings, and backend event sequence.
5. **Reset experiment** clears the result/applied state and restores default inputs
   locally. It sends no request and does not affect other tabs.

| Scenario | Initial client error | Correction | Residual client error |
| --- | --- | --- | --- |
| Symmetric 20/20 | +120 | −120 | 0 |
| Forward-heavy 60/20 | +120 | −100 | +20 |
| Reverse-heavy 20/60 | +120 | −140 | −20 |
| Client behind, 20/20 | −120 | +120 | 0 |
| Initially aligned, 60/20 | 0 | +20 | +20 |

Client error means **client minus reference**; NTP offset/correction means
**reference minus client**. Before/after readings refer to the same instant.
A negative correction is a backward step. Timelines and raw readings preserve
half-nanoseconds; residuals are not rounded to zero for display.

The API computes both snapshots during measurement; the UI deliberately reveals
the after state only on Apply. Exported native simulation JSON therefore contains
both snapshots even before Apply. No animation claims to infer drift or gradual
clock discipline.

## State, errors, and boundaries

- Each tab owns its inputs, result, and reset state. Tab navigation preserves them.
  Nothing transfers a live offset into the virtual clock; scenario transfer
  between simulations was optional and is not implemented in this slice.
- Editing inputs marks the old result explicitly. Sync Apply is disabled until
  a successful measurement matches the edited inputs. A new success clears the
  applied stage. Failed requests keep the old result with a clear failure label;
  no automatic fallback, retry, or simulation POST on tab activation exists.
- Submission locks prevent duplicate requests; inputs/reset are disabled in flight.
  Native input patterns reject missing/non-decimal values; the Python API enforces
  actual numeric ranges and reports domain errors such as a 2001 ms one-way delay.
- Fields accept decimal strings with up to six fractional ms places. Known truth
  is shown only with SIMULATION provenance. Simulations assume equal-rate ideal
  clocks, constant offset, fixed delays, and a single step correction.
- Reduced-motion behavior from P3.2 remains in effect. New charts and correction
  snapshots are static. Values, signs, table alternatives, and source labels do
  not depend on color. Dense comparison/timestamp tables scroll within their
  containers instead of overflowing the page.

## Implementation and validation

New modules: `DelayLab.tsx`, `SyncLab.tsx`, `SimulationShared.tsx`,
`simulationApi.ts`, component/contract tests, and targeted browser cases.
The existing fetch/error adapter is reused. Types are taken from the existing
OpenAPI-generated declarations, with narrow response boundary checks. Python
models, formulas, API implementation, and protocol behavior are unchanged.

Test fixtures are labeled schema-1 simulations with fixed result metadata and
are generated by `frontend/scripts/export_test_fixtures.py`. Regenerate using
`.venv/bin/python frontend/scripts/export_test_fixtures.py` from the repository;
it requires the optional web environment because series fixtures exercise the
existing API adapter. Expected preset/correction values in tests are literal,
independently stated observations, not calculated by a second JS implementation.

Run the existing frontend commands (`test`, `types:check`, `build`, `test:e2e`,
`format:check`) and the Python regression suite. Browser API processes use the
existing public-network audit guard; simulation cases use the real local Python
API. Any attempted browser measurement is rejected by the test fixture.
P3.2 browser cases run as regressions, not as a declaration of P3.4 completion.

Final results: **634 Python tests passed** (existing suite, 4.25 s),
**39 frontend unit/component tests passed** (19 existing + 20 new), and
**46 Chromium browser tests passed** (16 existing regressions + 30 targeted
simulation cases across development/release, 26.3 s). No failures or skips
remain. Production TypeScript/Vite build, generated API type drift check, and
Prettier check pass. Generated fixtures reproduce byte-for-byte. Browser cases
include all four delay presets, both sweeps, five synchronization cases, dirty
inputs/API errors, half-ns readings, reset, and complete series JSON export.

Axe checks pass for the exercised empty/result states. A hovered primary button
contrast failure found during validation was corrected with a slightly darker
shared hover blue; button size and the design system are unchanged. Projection
sizes 1280/1024px and mobile 390px were checked for wrapping/overflow; new
primary values retain at least 32px at the tested desktop sizes. Native browser
select menus may shorten long option labels on narrow screens; full chosen
parameters are retained in the input fields and results. The shared menu options
and field values are keyboard accessible. Node emitted the existing environment
NO_COLOR/FORCE_COLOR warning; it is not an app failure.

No package dependencies, Python API routes, or calculation algorithms were
changed. New JS/CSS build sizes are approximately 279 kB / 85 kB gzip and 24 kB /
6 kB gzip. Frontend-only changes were validated against the actual Python API;
this does not claim the separate P3.4 integrated-acceptance gate.

Reviewed screenshots (SIMULATION, not public measurements):

- [Delay desktop](evidence/p3.3-delay-desktop.png) · [Delay mobile](evidence/p3.3-delay-mobile.png)
- [Synchronization desktop](evidence/p3.3-sync-desktop.png) · [Synchronization mobile](evidence/p3.3-sync-mobile.png)

Remaining manual checks: native Safari, the physical projector, and classroom
spoken timing. P3.4's full integrated acceptance remains a separate authorized
phase. No public NTP request, OS clock change, commit, or push was performed.
