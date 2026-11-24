# P3.2 — React shell and Real NTP Exchange

Implemented on 2026-11-23 after explicit P3.2 authorization. One React application
has three horizontal, Safari-inspired tabs. Only **Real NTP Exchange** is
functional. Network Delay & Accuracy and Clock Synchronization display honest
“coming later” panels; no simulation controls or requests were added for them.

## Run locally

Requirements: Python 3.11+ with the package's optional web dependencies and
Node.js 22.12+ with npm. Tested with Node 26.5.0/npm 11.17.0 on macOS.

From the repository, start the Python API in terminal 1:

```sh
source .venv/bin/activate
python -m pip install -e '.[web]'
python -m uvicorn ntp_sync_lab.api.app:app --host 127.0.0.1 --port 8000 --workers 1
```

In terminal 2:

```sh
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. No measurement or replay runs automatically.
Select **Load captured exchange** for the historical public capture, or explicitly
select **Measure once** to send one live request. Public-server cooldowns and
control blocks still apply. A live timeout does not load replay automatically.

The capture should show REPLAY · original LIVE, original date
2026-11-15 09:30:25.203822 UTC, offset +81.0434325 ms, RTT 78.664213 ms, and
unknown accuracy. The source badge and capture date remain visible. Expand
**Four timestamps**, **How the estimate works**, or **Provenance & limitations**
for exact values, formula substitution, assumptions, and JSON export.

## Build and serve on one origin

From the repository:

```sh
npm --prefix frontend run build
NTP_LAB_WEB_DIST="$PWD/frontend/dist" .venv/bin/python -m uvicorn ntp_sync_lab.api.web:create_web_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Stop the development API first if it owns port 8000. Open
**http://127.0.0.1:8000**. The optional factory adds static files after the existing
API routes. A missing build fails with an actionable startup error. The React
build remains separate from the Python wheel; no Node dependency is needed by
the calculation engine or CLI.

Development uses a fixed loopback Vite proxy. It rewrites a matching local
browser Origin together with Host so the API's same-origin check works, but
preserves foreign origins for rejection. Vite CORS is disabled; FastAPI's CORS
policy is unchanged. The release uses relative `/api/v1` requests directly on
the same origin. `npm run preview` is also local and proxies to port 8000; it is
not a deployment service. Keep one Python worker and loopback binding.

## Interaction and scientific accuracy

- Explicit user actions alone create measurement/replay POSTs. A synchronous
  submission lock prevents double clicks, including React StrictMode behavior.
  Tabs preserve the ongoing operation and session result; switching tabs pauses
  illustrative playback without sending a new request.
- Backend cooldown/busy/control states disable measurements. Available waits
  count down locally using monotonic `performance.now()`. Configuration refresh
  after a live attempt is GET-only; an externally busy API has an explicit
  Refresh availability action. Unknown cooldown is labeled and still checked
  by Python. No periodic NTP requests, retry loop, or state bypass exists.
- Failures stay visible until an explicit next attempt. If a previous successful
  result remains, the UI labels it as separate from the failure. Network loss
  has an actionable API message. GET configuration calls have a 10-second client
  limit; an in-progress live request is not automatically repeated or abandoned
  merely because the UDP timeout does not bound DNS.
- The browser displays backend metrics. No four-timestamp estimator or protocol
  validation was duplicated in JavaScript. Exact decimal-string nanoseconds are
  retained. Integer/BigInt formatting converts units/calendar display without
  floating-point subtraction of epoch timestamps. Large dates outside browser
  calendar range retain their exact ns values in the timestamp table.
- Playback supports play/pause, restart, speed, and reduced-motion step-through.
  Arrow lengths, event positions, and playback durations are **illustrative**,
  not live traces, synchronized axes, or known one-way delays.
- Up to 20 successful observations are retained in memory, each with source and
  original date. Reloading the page clears history. JSON export preserves the
  native live document or complete replay wrapper; it never reconstructs a new
  capture from displayed values.

## Design and accessibility

The design follows Safari’s top horizontal tab structure and uses a system-font
stack, a lightly translucent navigation bar, solid content surfaces, generous
spacing, and a restrained blue primary action. It is a **web interpretation** of Apple
materials, not native SwiftUI/AppKit Liquid Glass or an Apple product. There are
no external fonts, image services, or runtime asset requests.

Roving tab focus supports Left/Right/Home/End, with proper tab/panel relationships.
Buttons and form controls have visible focus and names; tables expose event and
clock ownership. Information source is distinguished by text/icons as well as
color. Reduced motion disables timed animation; reduced transparency and
unsupported backdrop filters use opaque surfaces. Narrow screens stack the
controls and results, with a horizontally scrollable exact timestamp table.
SVG event labels remain visible on mobile; precise timestamps are inspected in
the full table rather than squeezed into tiny diagram labels.

Apple references: [materials](https://developer.apple.com/design/human-interface-guidelines/materials)
and [Adopting Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass).
Actual classroom projector readability and native Safari/WebKit behavior still
need manual verification; Chromium screenshots do not certify those settings.

## Types and validation

```sh
# In frontend, with the Python web environment installed
npm run types:check
npm run test
npm run build
npm run test:e2e
npm run format:check
```

`types:generate` imports the actual local FastAPI OpenAPI schema and produces
`src/generated/api.d.ts` using openapi-typescript. It requires neither an HTTP
server nor NTP access. `types:check` compares a fresh generation byte-for-byte;
set `NTP_LAB_PYTHON` to an absolute Python path if not using `../.venv/bin/python`.
Legacy replay batches and the API's generic config/catalog payloads additionally
receive narrow runtime boundary checks before display.

Playwright starts its own API/Vite/static-release servers on ports 8000, 5173,
and 8001; stop other servers on those ports before testing. On a new machine,
install the browser once with `npx playwright install chromium`. API subprocesses
load the existing loopback-only network audit guard. Browser measurement requests
are intercepted fixtures. No public NTP request is used in the browser tests.

Final results: **634 Python tests passed** (632 existing + 2 static-release
boundary tests), **19 frontend unit/component tests passed**, and **16 Chromium
browser tests passed** (8 workflows × development proxy and release). TypeScript
production build, API type drift check, and Prettier check passed. The exercised
Axe states reported zero violations after contrast and accessible-label fixes.
No checks were skipped in these installed environments. npm reported no known
vulnerabilities at installation; browser logs contained an environment-only
NO_COLOR/FORCE_COLOR warning. These checks do not certify every browser or a
physical projector.

Runtime build: React 19.3.1, TypeScript 5.9.3, Vite 7.3.8; Vitest 4.1.12,
Playwright 1.65.1 and axe-core integration 4.14.0. `package-lock.json` records the
complete npm dependency resolution. The production JS bundle is approximately
256 kB / 80 kB gzip, CSS 17 kB / 4 kB gzip, with no remote fonts/assets.

Tests cover:
exact positive/negative/half-ns formatting; no startup POSTs in StrictMode;
explicit replay, precise timestamps, unknown truth; duplicate-submit rejection;
backend blocked state; failure preservation; 20-entry history; keyboard tabs;
reduced motion; 390px mobile overflow; original JSON download; real API replay
through development and release serving; and rejection of foreign origins.
Axe checks cover mobile replay plus desktop empty and placeholder panels.

Remaining scope: the other two experiment interfaces, their charts/controls, and
full three-tab integration belong to P3.3/P3.4. No commit, push, new public probe,
or host clock modification is part of P3.2.

## Reviewed screenshots

These show the genuine archived capture, labeled as replay; they are not new
live measurements. Screenshots were captured from Chromium at desktop and
390px mobile widths and visually inspected. Exact timestamps are available in
the expandable table.

- [Desktop](evidence/p3.2-exchange-desktop.png)
- [Mobile, reduced motion](evidence/p3.2-exchange-mobile.png)

## Presentation design revision

The owner requested a less decorative, more legible classroom interface.
References consulted: [Apple Safari](https://www.apple.com/safari/),
[Apple HIG typography](https://developer.apple.com/design/human-interface-guidelines/typography.md),
and [Adopting Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass.md).
The applied design decisions are our interpretation, not an official Apple design.

Removed the imitation address bar, colored ambient glows, nested glass treatment,
gradient icon/buttons, and promotional slogans. Retained horizontal tabs, limited
translucency to navigation, and made numerical results the first content in the
result surface. Typography increases are generally around 120% or more: heading
40→48px, tabs 13→16px, primary actions 12→15px, key desktop values roughly
32→34–40px, and small explanatory copy 9–10→12–14px. Font sizes adapt by viewport;
this is a layout revision rather than a CSS/browser zoom transform.

Added browser assertions at 1280×720, 1024×768, and 1440×900: primary values are
above the fold, at least 32px, and controls/numbers have no horizontal clipping.
Mobile remains 390px with no document overflow. Numerical values never break
inside a number; exact ns timestamps remain in a scrollable table. Diagram labels
now show milliseconds (truncated for display) for readability, with explicit
notice that exact nanoseconds are in the table; calculations/results are unchanged.
Updated build, 19 component/unit tests, all 16 browser tests, Axe states, and
format checks passed. Python implementation was unchanged by this design pass.
Physical projector viewing and Safari remain manual checks.

[1280px projector layout](evidence/p3.2-projector-1280.png)
