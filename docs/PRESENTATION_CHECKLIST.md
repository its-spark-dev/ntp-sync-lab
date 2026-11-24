# Presentation quick checklist

Use with [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md). These boxes are **not yet verified
by a human rehearsal**. Phase 4 work currently covers documentation only; slides,
physical rehearsal, and new public probes are not performed by this change.

## Before leaving for class

- [ ] Dependencies installed and `frontend/dist` built on the actual demo machine.
- [ ] One-origin server starts from the repository at `http://127.0.0.1:8000`.
- [ ] Local archive loads with REPLAY · original LIVE and the original date.
- [ ] Both simulation tabs work after external Internet is disconnected.
- [ ] CLI fallback terminal and local static artifacts are ready.
- [ ] Spoken five-stage sequence rehearsed with a stopwatch; target 3:40.
- [ ] Any separately chosen live request follows server policy/cooldown; its
  genuine outcome is recorded. Skip this if using the offline baseline.

## At the projector

- [ ] API connected; readable from the back of the room.
- [ ] Zoom/viewport tested; offset, RTT, signs, and units are not clipped.
- [ ] Notifications silenced, screen awake, server terminal retained.
- [ ] Browser reloaded to **Real NTP Exchange → Awaiting an exchange**.
- [ ] Do not click Measure once unless explicitly choosing an eligible live request.

## Cue card (web baseline)

| Time | Action | Numbers / teaching point |
| --- | --- | --- |
| 0:00–0:55 | Load captured exchange | Replay of real capture; +81.0434325 ms offset, 78.664213 ms RTT; truth unknown |
| 0:55–1:35 | Delay: Increase both delays → Run | RTT 40→160 ms; true/estimated +100; error 0 |
| 1:35–2:10 | Single exchange → Asymmetric 60/20 → Run | Estimate +120 versus truth +100; error +20; RTT 80 |
| 2:10–3:20 | Sync: symmetric Measure → Apply; forward-heavy Measure → Apply | Initial +120; corrections −120/−100; residuals 0/+20 |
| 3:20–3:40 | State limits | Unknown live asymmetry, software timestamps, ideal step-only model, no OS clock change |

If live fails, explicitly load saved replay. If web fails, use the five CLI
commands in the runbook. If runtime fails, label screenshots/output as static.
Reset simulations with their Reset experiment buttons; reload for a clean entire
session. **Never reset/delete polling state to reset the screen.**

## Record actual rehearsal (leave incomplete fields blank)

| Field | Observed value |
| --- | --- |
| Presenter / reviewer | |
| Local date and time | |
| Machine / OS / browser | |
| Projector resolution / viewport / browser zoom | |
| Back-row readability / wrapping | |
| Offline run outcome | |
| Spoken demo elapsed time | |
| Optional real preflight date / source / outcome | |
| Problems and corrections | |
| Ready for the next authorized Phase 4 step? | |

Slides are not included. No G4 completion or timed/projected rehearsal is implied
by preparing these documents.
