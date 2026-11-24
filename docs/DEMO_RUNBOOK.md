# Presentation demo runbook

Phase 4 documentation preparation is authorized following P3.4 approval.
This runbook covers the implemented three-tab app, explicit offline alternatives,
and startup/reset procedures. **No slides are created in this task.** Physical
projector checks, spoken timing, and classroom network preflight remain manual;
writing this document does not claim those rehearsals have occurred.

Use [PRESENTATION_CHECKLIST.md](PRESENTATION_CHECKLIST.md) immediately before the
talk. Technical validation is in [INTEGRATION_VALIDATION.md](INTEGRATION_VALIDATION.md).

## 1. Prepare before presentation day

Use the actual demonstration machine. Python 3.11+, Node.js 22.12+, and npm are
required for clean setup/build. Complete dependency installation while online;
do not depend on package downloads in the classroom. From the repository root:

```sh
# First setup only; skip environment creation if already prepared.
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[web]'
npm --prefix frontend ci
npm --prefix frontend run build
```

If the repository environment is already working, retain it. Do not delete it or
change polling-state locations just to repeat setup. The resulting
`frontend/dist/index.html` and assets must stay on the demo machine together
with the installed Python package and packaged recordings.

The preferred presentation build uses **one local server and one origin**:

```sh
# Run from the repository root; keep this terminal open.
NTP_LAB_WEB_DIST="$PWD/frontend/dist" .venv/bin/python -m uvicorn ntp_sync_lab.api.web:create_web_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000**. Leave the server terminal available for diagnosis.
No NTP request is sent at startup. Stop with Ctrl-C in that terminal after the
presentation. Only one server should own port 8000. If it is occupied, stop the
known development server normally before starting the presentation server;
do not indiscriminately terminate other processes.

The two-terminal development setup remains in [FRONTEND.md](FRONTEND.md).
The single-origin build above removes the need to run Vite during the talk.
There is no deployment, account login, or remote hosting requirement.

## 2. Rehearse and preflight without public NTP

1. Start the prepared build, open the local URL, and confirm **API connected**.
   A GET-only health check is also available:

   ```sh
   curl --fail http://127.0.0.1:8000/api/v1/health
   ```

2. In **Real NTP Exchange**, choose **Load captured exchange**. Confirm
   **REPLAY · original LIVE**, capture date **2026-11-15 09:30:25.203822 UTC**,
   offset **+81.0434325 ms**, RTT **78.664213 ms**, and accuracy **Unknown**.
3. Run both simulation tabs with the scenarios below. Check their **SIMULATION**
   labels, expected values, Apply behavior, and Reset experiment actions.
4. During rehearsal, disconnect external Internet access while keeping the local
   server running. Reload the local page and repeat capture/simulation actions.
   Localhost must remain reachable. Browser DevTools “Offline” can also block
   localhost, so it is not the intended simulation of unavailable public NTP.
5. Connect the actual projector. Start at browser zoom 100% because the UI already
   uses enlarged presentation typography. Inspect from the back of the room;
   enlarge further if needed and recheck wrapping. Scroll a long panel as needed.
   Dense exact-timestamp/comparison tables intentionally scroll within themselves.
6. Time a spoken rehearsal with the five stages below. The **3:40** budget is an
   estimate, not measured delivery. Explain results rather than reading every
   timestamp, assumption, or JSON field. Keep detailed tables for questions.
7. Restore the clean start described in section 5. Leave the browser on the first
   tab with no result selected; leave CLI fallback commands ready in a second
   terminal. Disable distracting notifications using the machine's normal controls.

Do not click **Measure once** as part of these offline checks. A separately chosen
public live preflight is optional and follows section 4.

## 3. Web demonstration — target 3 minutes 40 seconds

The baseline sequence is entirely local and uses a genuine historical exchange
plus deterministic simulations. It remains valid when public UDP is blocked.
The surrounding topic explanation (2–3 minutes) and Q&A (1–2 minutes) are separate.

### 0:00–0:55 — Real NTP Exchange, using the preserved capture

- Select **Load captured exchange**. Point to **REPLAY · original LIVE** and the
  original capture date before explaining numbers.
- Say: “This is a saved real exchange, not a new request. T1/T4 use the client
  clock; T2/T3 use the server clock.”
- Briefly play the illustration, then pause it. State that arrow positions and
  playback speed do not represent measured one-way delays.
- Point to **+81.0434325 ms** estimated server-minus-client offset and
  **78.664213 ms** network RTT. True offset/error remain unknown.
- Expand **Four timestamps** or **How the estimate works** only if needed to
  identify ownership/formula; close it before moving on. Diagram timestamps
  show milliseconds; the table retains exact nanoseconds.

### 0:55–1:35 — Symmetric delay comparison

- Open **Network Delay & Accuracy**.
- Keep **Symmetric · 20 / 20 ms** and choose Comparison **Increase both delays**.
  Select **Run delay simulation**.
- Use the comparison table: forward/reverse delays **20/20→80/80 ms**,
  RTT **40→160 ms**, estimated offset **+100 ms**, error **0** at both points.
  Select **Point 2** if you want its metrics/chart displayed.
- Say: “This is a model with known truth. Equal increases in delay raise RTT
  without adding offset bias under these assumptions.”

### 1:35–2:10 — Asymmetric delay

- Set Comparison to **Single exchange** and Delay preset to
  **Asymmetric · 60 / 20 ms**. Select **Run delay simulation**.
- Point to true offset **+100 ms**, estimate **+120 ms**, error **+20 ms**,
  and RTT **80 ms**.
- Say: “Half the difference between the one-way delays becomes offset error.
  RTT alone does not determine accuracy.” The controls model a path; they do not
  inject delay into the earlier public exchange.

### 2:10–3:20 — Virtual clock correction

- Open **Clock Synchronization**, with **Symmetric · zero residual** selected.
- Select **Measure virtual clock**, then **Apply correction**.
  Initial client error **+120 ms** → correction **−120 ms** → residual **0**.
- Choose **Forward-heavy · positive residual**. Select **Measure virtual clock**
  again, then **Apply correction**.
  Initial **+120 ms** → correction **−100 ms** → residual **+20 ms**.
- Say: “Client error is client minus reference, so its sign is opposite to NTP
  offset. We add the estimated offset to virtual time. Measurement bias can
  remain after correction. Both snapshots share one reference instant.”
- Apply reveals the after snapshot already calculated by Python; it does not
  change the host clock or perform a fresh network measurement.

### 3:20–3:40 — Close with the limits

“These are software timestamps without cryptographic authentication. A live
exchange does not reveal true one-way delays or true offset. The simulations
assume equal-rate clocks and apply one step; drift and gradual discipline are
outside this model. Only virtual time changes.”

For Q&A, optionally show **Fixed RTT asymmetry**, 80 ms/3 points: errors
**−40/0/+40 ms** at the same RTT. Or choose **Reverse-heavy · negative residual**
in synchronization: correction **−140 ms**, residual **−20 ms**. These are outside
the five-stage time budget.

## 4. Optional live request and explicit fallback ladder

A new live request is optional. Choose it only when explicitly intended and
permitted by the target's policy; do not make one merely to check that the web
page loads. No new public probe was made while preparing these documents.

If live behavior is part of the talk, preflight **one** target on the actual
network, using one chosen interface, for example:

```sh
.venv/bin/python -m ntp_sync_lab measure --server pool.ntp.org --count 1 --timeout-seconds 3 --output artifacts/classroom-preflight.json
```

An existing export is protected; choose an intentional new filename if needed.
If saving fails after a measurement, preserve the displayed result instead of
probing again. A permitted preflight can be replayed by CLI with
`replay --file artifacts/classroom-preflight.json`; browser replay accepts packaged
recordings only, so it cannot import this arbitrary file through the UI.

Before a further live attempt, wait for the **actual** destination cooldown:
at least 64 seconds, longer after timeouts (persisted backoff up to 1024 seconds).
CLI and API share the guard. A control response blocks that target for operator
policy review; do not reset state or rotate destinations to force success.
DNS/filesystem waits are outside the UDP timeout, so do not promise a hard
three-second total response. Never wait through a multi-request batch on stage.

If using a permitted live exchange, substitute it for the first archived step;
do not add repeated requests to the short demonstration. Actual offset/RTT may
be small or differ from the capture. Keep **LIVE MEASUREMENT** visible and leave
truth/error unknown. A previously successful preflight does not guarantee the
next request will succeed.

| Problem | Explicit next action | What to tell the audience |
| --- | --- | --- |
| Live timeout, unsupported reply, DNS/network failure | Leave the error visible; select **Load captured exchange** | “The live request failed; we are now replaying a saved real exchange.” |
| Cooldown or target blocked | Respect the wait/block; choose packaged replay | “Public polling is restricted. This example sends no new NTP request.” |
| Internet unavailable | Keep localhost running; use packaged replay and simulations | “The first result is historical; the other two are models.” |
| Local web/API startup failure or unreadable browser layout | Switch to prepared CLI commands below | “The CLI uses the same Python engine.” |
| Local runtime also unavailable | Show the saved screenshots/output files as static evidence | “These are saved results, not an interactive or live run.” |

### CLI fallback (same five stages)

From the repository, paste commands separately. They need no public networking:

```sh
.venv/bin/python -m ntp_sync_lab replay --scenario captured-public-ntp
.venv/bin/python -m ntp_sync_lab delay --preset symmetric-low --increments-ms 0 60
.venv/bin/python -m ntp_sync_lab delay --preset asymmetric-forward
.venv/bin/python -m ntp_sync_lab sync --client-offset-ms 120 --forward-ms 20 --reverse-ms 20
.venv/bin/python -m ntp_sync_lab sync --client-offset-ms 120 --forward-ms 60 --reverse-ms 20
```

Read the labeled result sections, not the entire terminal transcript. CLI sync
prints the complete modeled correction directly; it has no separate Apply click.
No invisible switch from live to replay occurs. The historical
[P1.7 CLI transcript](evidence/p1.7-cli-rehearsal.txt) is supporting evidence,
not a timed human classroom rehearsal.

Static fallback artifacts are local repository files:
[exchange output](examples/replay-public.txt), [delay output](examples/delay.txt),
[sync output](examples/sync.txt), [exchange screenshot](evidence/p3.2-exchange-desktop.png),
[delay screenshot](evidence/p3.3-delay-desktop.png), and
[sync screenshot](evidence/p3.3-sync-desktop.png). Open them before entering the
room if the fallback must survive a local runtime failure.

## 5. Reset and stop — preserve network safeguards

| Action | Effect | Does not do |
| --- | --- | --- |
| **Restart illustration** | Returns packet playback to its initial ready state; pauses it | Does not clear the exchange or send UDP |
| **Reset experiment** in Delay | Clears only that tab's results/errors; restores Single exchange, symmetric 20/20, truth +100, processing 5, default sweep settings | Does not clear other tabs or public cooldown |
| **Reset experiment** in Sync | Clears measurement/Apply state; restores client +120 and 20/20 delays, processing 5 | Does not alter the OS clock or another tab |
| Reload local browser page | Returns to the first tab; clears in-memory results, history, and simulation state | Does not clear persisted cooldown/backoff/control blocks |
| Switch a tab | Preserves that tab's state; pauses packet illustration when leaving it | Does not start a new measurement or reset another experiment |
| Ctrl-C in server terminal | Stops the local server when shutdown completes | Does not clear persisted polling state |

To prepare the clean opening: finish any pending action, pause the illustration,
then reload the browser. Verify the first tab says **Awaiting an exchange** and
that no measurement/replay begins automatically. There is no separate “clear
history” or real-tab Reset button; a page reload clears its session history.

If the browser is reloaded/closed during a live request, the backend may still
complete or time out that request and persist its guard state. Wait and inspect
state before another attempt. Reloading/restarting is not permission to bypass
a cooldown. Never delete `$XDG_CACHE_HOME/ntp-sync-lab/polling` or
`~/.cache/ntp-sync-lab/polling` to prepare a visually clean demonstration.

## 6. Rehearsal record

Use the checklist to record who rehearsed, when, projector/viewport/zoom, offline
behavior, and elapsed spoken time. Record any real preflight outcome separately
with its actual source and date. Leave unknowns blank rather than treating
existing automated test counts as a completed physical rehearsal. G4 is not
complete until the authorized final presentation requirements are actually met.

Documentation verification: all five CLI fallback cases were executed with
`socket.*` audit events prohibited and their JSON numbers checked against the
values above. This was an automated command check, not a spoken/timed rehearsal
or a fresh network measurement. Application code and design were unchanged.
