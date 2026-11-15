import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ntp_sync_lab.errors import InvalidTimingError
from ntp_sync_lab.models import ExchangeResult, Experiment, ResultSource, TimestampQuad
from ntp_sync_lab.serialization import SCHEMA_VERSION, to_contract, to_json


@pytest.fixture
def result():
    return ExchangeResult(
        # Fixture is a software-created example, not a real network capture.
        timestamps=TimestampQuad(
            1_794_693_600_000_000_001,
            1_794_693_600_000_000_002,
            1_794_693_600_000_000_002,
            1_794_693_600_000_000_002,
        ),
        experiment=Experiment.REAL_EXCHANGE,
        source=ResultSource.LIVE,
        result_id="serialization-fixture",
        created_at_utc=datetime(2026, 11, 15, 12, 0, 0, 123456, tzinfo=timezone.utc),
        provenance="Test-only live-shaped fixture; no network request was made",
        assumptions=("Application-level timestamps", "True offset is not observable"),
    )


def test_versioned_live_json_preserves_unknown_truth_and_large_timestamps(result):
    payload = json.loads(to_json(result))
    assert payload["schema_version"] == SCHEMA_VERSION == "1"
    assert payload["source"] == "live"
    assert payload["experiment"] == "real_exchange"
    assert payload["created_at_utc"] == "2026-11-15T12:00:00.123456Z"
    data = payload["data"]
    assert data["timestamps"]["t1_unix_ns"] == "1794693600000000001"
    assert int(data["timestamps"]["t1_unix_ns"]) == result.timestamps.t1_unix_ns
    assert data["estimated_offset_ns"] == "0.5"
    assert data["round_trip_delay_ns"] == "1"
    assert data["client_elapsed_ns"] == "1"
    assert data["server_processing_ns"] == "0"
    assert data["true_offset_ns"] is None
    assert data["estimation_error_ns"] is None
    assert payload["provenance"] == {"description": result.provenance}
    assert payload["assumptions"] == list(result.assumptions)
    assert payload["parameters"] == {}
    assert payload["warnings"] == []


@pytest.mark.parametrize(
    "timestamps, truth, expected_offset, expected_error",
    [
        ((-100_000_000, 60_000_000, 65_000_000, -15_000_000), 100_000_000, "120000000", "20000000"),
        ((-100_000_000, 20_000_000, 25_000_000, -15_000_000), 100_000_000, "80000000", "-20000000"),
        ((100_000_000, 20_000_000, 25_000_000, 145_000_000), -100_000_000, "-100000000", "0"),
        ((0, 0, 0, 1), 0, "-0.5", "-0.5"),
        ((0, 1, 1, 1), 1, "0.5", "-0.5"),
    ],
)
def test_known_simulated_truth_and_exact_estimation_error(
    result, timestamps, truth, expected_offset, expected_error
):
    modeled = replace(
        result,
        timestamps=TimestampQuad(*timestamps),
        source=ResultSource.SIMULATION,
        experiment=Experiment.NETWORK_DELAY,
        true_offset_ns=truth,
    )
    data = json.loads(to_json(modeled))["data"]
    assert data["estimated_offset_ns"] == expected_offset
    assert data["true_offset_ns"] == str(truth)
    assert data["estimation_error_ns"] == expected_error


def test_serialization_is_deterministic_and_returns_independent_containers(result):
    first = to_json(result)
    contract = to_contract(result)
    contract["data"]["timestamps"]["t1_unix_ns"] = "0"
    contract["assumptions"].append("changed by consumer")
    assert to_json(result) == first


def test_serialization_does_not_publish_invalid_timing_as_success(result):
    invalid = replace(result, timestamps=TimestampQuad(0, 10, 30, 10))
    with pytest.raises(InvalidTimingError):
        to_json(invalid)
