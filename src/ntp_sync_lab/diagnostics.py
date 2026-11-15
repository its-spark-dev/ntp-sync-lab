"""Internal one-probe interoperability diagnostic, not the P1.6 educational CLI."""

import argparse
from pathlib import Path

from ntp_sync_lab.core.client import MeasurementConfig
from ntp_sync_lab.experiments.measurement import run_measurements
from ntp_sync_lab.serialization import batch_to_json


def main() -> int:
    parser = argparse.ArgumentParser(description="One guarded public NTP compatibility probe; no retry")
    parser.add_argument("--server", required=True)
    parser.add_argument("--output", type=Path, help="Save evidence; refuses an existing path")
    args = parser.parse_args()
    # Open the evidence destination before any probe: an existing file is never
    # a reason to make a second measurement just to recreate its output.
    handle = args.output.open("x") if args.output is not None else None
    try:
        batch = run_measurements(MeasurementConfig(args.server))
        text = batch_to_json(batch)
        if handle is not None:
            handle.write(text + "\n")
        print(text)
        return 130 if batch.interrupted else (3 if batch.failures else 0)
    finally:
        if handle is not None:
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
