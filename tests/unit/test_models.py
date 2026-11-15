from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction

import pytest

from ntp_sync_lab.errors import InvalidInputError
from ntp_sync_lab.models import (
    ExchangeMetrics,
    ExchangeResult,
    Experiment,
    ResultSource,
    TimestampQuad,
)


@pytest.fixture
def result():
    return ExchangeResult(
        timestamps=TimestampQuad(0, 1, 1, 2),
        experiment=Experiment.REAL_EXCHANGE,
        source=ResultSource.LIVE,
        result_id="controlled-fixture",
        created_at_utc=datetime(2026, 11, 15, tzinfo=timezone.utc),
        provenance="Controlled fixture, not an actual network capture",
        assumptions=("Stable clocks during one exchange",),
    )


@pytest.mark.parametrize("field", ["t1_unix_ns", "t2_unix_ns", "t3_unix_ns", "t4_unix_ns"])
@pytest.mark.parametrize("value", [True, 1.0, "1", Fraction(1), Decimal("1"), float("nan"), float("inf"), None])
def test_timestamps_reject_lossy_or_ambiguous_types(field, value):
    timestamps = dict(t1_unix_ns=0, t2_unix_ns=1, t3_unix_ns=1, t4_unix_ns=2)
    timestamps[field] = value
    with pytest.raises(InvalidInputError) as error:
        TimestampQuad(**timestamps)
    assert error.value.code == "INVALID_INPUT"


def test_domain_records_are_immutable(result):
    with pytest.raises(FrozenInstanceError):
        result.timestamps.t1_unix_ns = 5
    with pytest.raises(FrozenInstanceError):
        result.source = ResultSource.SIMULATION
    with pytest.raises(FrozenInstanceError):
        ExchangeMetrics(Fraction(0), 2, 2, 0).estimated_offset_ns = Fraction(1)


@pytest.mark.parametrize(
    "changes",
    [
        {"true_offset_ns": 0},
        {"true_offset_ns": 100},
        {"true_offset_ns": float("nan")},
        {"true_offset_ns": True},
        {"source": "live"},
        {"experiment": "real_exchange"},
        {"experiment": Experiment.NETWORK_DELAY},
        {"timestamps": (0, 1, 1, 2)},
        {"result_id": " "},
        {"provenance": ""},
        {"assumptions": ["mutable list"]},
        {"assumptions": ("",)},
        {"created_at_utc": datetime(2026, 11, 15)},
        {"created_at_utc": datetime(2026, 11, 15, tzinfo=timezone(timedelta(hours=-5)))},
    ],
)
def test_invalid_result_metadata_and_false_live_truth_are_rejected(result, changes):
    with pytest.raises(InvalidInputError):
        replace(result, **changes)


@pytest.mark.parametrize(
    "values",
    [
        (0.5, 1, 1, 0),
        (Fraction(1, 3), 1, 1, 0),
        (Fraction(0), -1, 0, 1),
        (Fraction(0), 1, 1.0, 0),
        (Fraction(0), 1, 1, True),
        (Fraction(0), 1, 5, 1),
    ],
)
def test_metrics_validate_exact_types_and_interval_consistency(values):
    with pytest.raises(InvalidInputError):
        ExchangeMetrics(*values)
