# P1.3 — NTP networking validation

## Genuine public interoperability check

This section reports one actual UDP exchange, separate from every automated test
fixture. After the initial 281 tests passed, the internal diagnostic ran once:

```sh
.venv/bin/python -m ntp_sync_lab.diagnostics --server pool.ntp.org --output docs/evidence/p1.3-public-ntp.json
```

The configured hostname was `pool.ntp.org`; the resolver selected
`23.143.196.203:123` for this exchange. This address is capture metadata, not a
recommendation to hard-code a volunteer server. The OS assigned local port 54027.
Capture completed at **2026-11-15 09:30:25.203822 UTC**. Exactly one request was
sent through the normal cooldown guard, with a 3 s timeout and no retries.

The [saved JSON evidence](evidence/p1.3-public-ntp.json) contains the actual
request/response bytes, raw timestamp words, decoded timestamps, capture spans,
monotonic readings, peer/server metadata, and calculated results. It was also
revalidated offline against the pure codec/validator/calculator after capture.

| Check | Observed result |
| --- | --- |
| Response length | 48 bytes; accepted base-header profile |
| Version / mode | NTPv4 / server mode 4 |
| Stratum / leap indicator | 2 / 0 |
| Originate timestamp | Exact match to request transmit bytes |
| Response source | Expected resolved IPv4 address and UDP port 123 |
| Ignored datagrams | 0 |
| Estimated server-minus-client offset | +81.0434325 ms |
| Network round-trip delay | 78.664213 ms |
| Client elapsed / server processing | 78.691 ms / 0.026787 ms |
| Wall-minus-monotonic elapsed discrepancy | +0.0015 ms; below the configured guard |
| Known true offset / estimation error | Unknown / unknown (`null`) |

The four timestamps are integer Unix nanoseconds, captured/reported by the
respective clocks:

| Event | Clock | Unix nanoseconds |
| --- | --- | --- |
| T1 — request transmission | Client software clock | 1794735025125131000 |
| T2 — request reception | Server-reported clock | 1794735025245506539 |
| T3 — response transmission | Server-reported clock | 1794735025245533326 |
| T4 — response reception | Client software clock | 1794735025203822000 |

Independent substitutions in nanoseconds:

```text
T2 - T1 = 120375539
T3 - T4 =  41711326
offset  = (120375539 + 41711326) / 2 = 81043432.5

T4 - T1 = 78691000
T3 - T2 =    26787
delay   = 78691000 - 26787 = 78664213
```

The nonnegative approximately 79 ms network delay and finite approximately
+81 ms estimated offset are plausible for an Internet exchange. This is not an
independent accuracy measurement: path asymmetry, server error, host scheduling,
and unauthenticated UDP still matter. T3 being greater than T4 numerically is
valid because the timestamps belong to different clocks. There is no known live
one-way delay or true offset, and no OS clock correction was attempted.

The selected server supports the current limited profile. No compatibility
expansion was needed. This one IPv4 success does not establish interoperability
with all servers, IPv6 public paths, extended/authenticated replies, or another
network. Replies with trailing data or unsupported version/mode still fail
explicitly; they are not silently accepted. No further public probe was made.
The chosen conservative usage follows the [NTP Pool guidance](https://www.ntppool.org/en/use.html).

## Automated and local evidence

The complete suite passes **285 tests** (218 preserved P1.1/P1.2 tests plus 67
P1.3 cases) with Python 3.11.14 and Pytest 9.2.0:

```sh
.venv/bin/python -m pytest -q
```

`tests/integration/test_local_udp.py` exercises actual sockets against **explicit
loopback test fixtures**, one each on `127.0.0.1` and `::1`, using OS-selected
unprivileged destination ports. Both passed with no skips in this environment.
These are not public NTP measurements. Assertions cover the actual request and
originate bytes, expected peer, software timestamps/metrics, nonprivileged source
port, fixture provenance, and closed client sockets.

Other tests use fake clocks/resolvers/transports or socket fixtures. They verify
fixed deadlines, bounded ignored-datagram diagnostics, distinct operational and
protocol errors, malformed/unsupported replies, wall steps, cleanup, persisted
cooldown/backoff/control blocks, concurrent processes, partial/interrupted
batches, exact summaries, and preservation of null ground truth. A Python audit
hook rejects public DNS and UDP inside the suite. Backoff tests advance fake
time; there are no real 64-second waits.

## Implementation boundaries and limitations

- DNS resolution is outside the monotonic UDP timeout and can block longer.
- Software timestamping includes packing, system calls, scheduling, and small
  wrapper overhead. Read-span and clock-jump diagnostics cannot prove accuracy.
- The UDP socket is unconnected; peer checks are explicit. Its local binding can
  be a wildcard address, not an independently identified outbound interface.
- Cooldown state uses small local files and POSIX locks. macOS/Linux are
  supported; platforms without that lock adapter fail closed. Cooperation uses
  the same cache directory. There is no cross-machine/user coordination.
- Across fresh processes, persisted deadlines rely on wall time. Backward steps
  block requests; large forward steps can shorten protection. One guard instance
  additionally enforces monotonic cooldowns. Corrupt/unavailable state blocks
  live work; outcome-persistence errors stop batches and need operator review.
- Control blocks are persistent and do not expire automatically. Review the
  server's policy before deliberately repairing/resetting its destination state.
- Schema version 1 remains in use, with additive networking/capture fields.
  Median offset can have a quarter-nanosecond mathematical value; this is exact
  arithmetic, not increased measurement accuracy. Full replay loading is later.
- No simulation/correction engines, educational CLI commands, full NTP
  filter/discipline, FastAPI, React, new dependencies, commits, or pushes are part
  of P1.3. The implementation stops here for review before P1.4.

## P1.3 file inventory

| Area | Created or modified |
| --- | --- |
| New core adapters/client | `src/ntp_sync_lab/core/clock.py`, `transport.py`, `polling.py`, `client.py` |
| New orchestration | `src/ntp_sync_lab/experiments/__init__.py`, `experiments/measurement.py` |
| New internal diagnostic | `src/ntp_sync_lab/diagnostics.py` |
| Existing code updated | `src/ntp_sync_lab/errors.py`, `serialization.py`, `core/__init__.py` |
| New test infrastructure | `tests/__init__.py`, `conftest.py`, `helpers.py` |
| New test modules | `tests/unit/test_clock.py`, `test_client.py`, `test_polling.py`, `test_transport.py`, `test_measurement.py`; `tests/integration/test_local_udp.py` |
| Documentation updated | `README.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md` |
| New report/evidence | `docs/INTEROPERABILITY.md`, `docs/evidence/p1.3-public-ntp.json` |

The P1.1 domain models/calculator, P1.2 wire codec/packet validator, educational CLI
scaffold, package metadata/dependencies, and existing tests were preserved.
