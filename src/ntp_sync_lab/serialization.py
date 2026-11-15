"""Version-1 JSON foundation for exchange results; no recording loader or I/O."""

import json
import copy
from datetime import datetime
from fractions import Fraction
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ntp_sync_lab.core.client import MeasurementResult
    from ntp_sync_lab.experiments.measurement import MeasurementBatch
    from ntp_sync_lab.experiments.delay import DelayResult
    from ntp_sync_lab.experiments.synchronization import SyncResult

from ntp_sync_lab.core.calculations import calculate_exchange
from ntp_sync_lab.errors import InvalidInputError
from ntp_sync_lab.models import ExchangeResult, Experiment, ResultSource

SCHEMA_VERSION = "1"


def _offset_string(value: Fraction) -> str:
    """Render exact offsets, including quarter-nanosecond descriptive medians."""
    if value.denominator == 1:
        return str(value.numerator)
    if value.denominator not in (2, 4):
        raise InvalidInputError("offset serialization supports whole, half, or quarter nanoseconds")
    # A median of two half-nanosecond offsets can have denominator 4.
    sign = "-" if value < 0 else ""
    whole, remainder = divmod(abs(value.numerator), value.denominator)
    fraction = str(remainder * (100 // value.denominator)).zfill(2).rstrip("0")
    return f"{sign}{whole}.{fraction}"


def to_contract(result: ExchangeResult) -> dict[str, object]:
    """Return a fresh JSON-compatible envelope with exact decimal strings.

    This foundation deliberately omits packet/peer diagnostics and experiment
    parameters that do not exist until later tasks. Empty containers reserve
    the approved envelope fields. It does not claim to be a complete recording.
    """
    if not isinstance(result, ExchangeResult):
        raise InvalidInputError("result must be an ExchangeResult")
    metrics = calculate_exchange(result.timestamps)
    true_offset = result.true_offset_ns
    estimation_error = (
        None if true_offset is None else metrics.estimated_offset_ns - true_offset
    )
    timestamps = result.timestamps
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": result.experiment.value,
        "source": result.source.value,
        "result_id": result.result_id,
        "created_at_utc": result.created_at_utc.isoformat().replace("+00:00", "Z"),
        "provenance": {"description": result.provenance},
        "parameters": {},
        "warnings": [],
        "assumptions": list(result.assumptions),
        "data": {
            "timestamps": {
                "t1_unix_ns": str(timestamps.t1_unix_ns),
                "t2_unix_ns": str(timestamps.t2_unix_ns),
                "t3_unix_ns": str(timestamps.t3_unix_ns),
                "t4_unix_ns": str(timestamps.t4_unix_ns),
            },
            "estimated_offset_ns": _offset_string(metrics.estimated_offset_ns),
            "round_trip_delay_ns": str(metrics.round_trip_delay_ns),
            "client_elapsed_ns": str(metrics.client_elapsed_ns),
            "server_processing_ns": str(metrics.server_processing_ns),
            "true_offset_ns": None if true_offset is None else str(true_offset),
            "estimation_error_ns": (
                None if estimation_error is None else _offset_string(estimation_error)
            ),
        },
    }


def to_json(result: ExchangeResult) -> str:
    """Serialize deterministically without lossy timestamp/offset coercion."""
    return json.dumps(to_contract(result), indent=2, sort_keys=True, allow_nan=False)


def measurement_to_contract(result: "MeasurementResult") -> dict[str, object]:
    """Extend the existing exchange envelope with actual capture diagnostics."""
    from dataclasses import asdict

    payload = to_contract(result.exchange)
    packet = result.response.packet
    payload["parameters"] = {
        "server": result.config.server, "timeout_seconds": result.config.timeout_seconds,
        "discontinuity_threshold_ns": str(result.config.discontinuity_threshold_ns),
    }
    payload["provenance"].update(
        server=result.config.server, peer=asdict(result.target.peer),
        local_peer=asdict(result.local_peer), capture_time_utc=payload["created_at_utc"],
    )
    payload["data"].update(
        request_packet_hex=result.request.packet.hex(), response_packet_hex=packet.raw.hex(),
        server_header={
            "version": packet.version, "mode": packet.mode, "stratum": packet.stratum,
            "leap_indicator": packet.leap_indicator, "packet_length": len(packet.raw),
            "poll_exponent": packet.poll_exponent, "precision_exponent": packet.precision_exponent,
            "root_delay_raw": packet.root_delay_raw, "root_dispersion_raw": packet.root_dispersion_raw,
            "reference_id_hex": packet.reference_id.hex(),
        },
        raw_timestamps={
            name: asdict(getattr(packet, f"{name}_timestamp"))
            for name in ("reference", "originate", "receive", "transmit")
        },
        clock_capture={
            "t1_wall_ns": str(result.sent.wall_ns),
            "t1_monotonic_ns": str(result.sent.monotonic_ns),
            "t4_wall_ns": str(result.received.wall_ns),
            "t4_monotonic_ns": str(result.received.monotonic_ns),
            "t1_read_span_ns": str(result.sent.read_span_ns),
            "t4_read_span_ns": str(result.received.read_span_ns),
            "wall_monotonic_discrepancy_ns": str(result.wall_monotonic_discrepancy_ns),
            "clock_info": asdict(result.clock_info),
        },
        ignored_count=result.ignored_count,
        ignored_datagrams=[asdict(item) for item in result.ignored_datagrams],
    )
    return payload


def batch_to_contract(batch: "MeasurementBatch") -> dict[str, object]:
    summary = batch.summary
    return {
        "schema_version": SCHEMA_VERSION, "experiment": "real_exchange", "source": "live",
        "server": batch.server, "requested_count": batch.requested_count,
        "interrupted": batch.interrupted, "stop_reason": batch.stop_reason,
        "attempts": [
            {
                "number": attempt.number,
                "result": None if attempt.result is None else measurement_to_contract(attempt.result),
                "error": None if attempt.error is None else {
                    "code": attempt.error.code, "message": attempt.error.message,
                    "details": {
                        key: str(value) if key.endswith("_ns") and type(value) is int else value
                        for key, value in attempt.error.details.items()
                    },
                },
            } for attempt in batch.attempts
        ],
        "summary": None if summary is None else {
            "valid_count": summary.valid_count,
            "median_offset_ns": _offset_string(summary.median_offset_ns),
            "minimum_round_trip_delay_ns": str(summary.minimum_round_trip_delay_ns),
            "offset_range_ns": _offset_string(summary.offset_range_ns),
            "interpretation": "Descriptive variation only; true synchronization accuracy is unknown",
        },
    }


def batch_to_json(batch: "MeasurementBatch") -> str:
    return json.dumps(batch_to_contract(batch), indent=2, sort_keys=True, allow_nan=False)


def delay_to_contract(
    result: "DelayResult", *, result_id: str, created_at_utc: datetime,
) -> dict[str, object]:
    """Serialize known model truth with explicit caller-supplied metadata.

    No clock/UUID is read or invented: identical results plus identical metadata
    serialize identically. created_at_utc describes result creation supplied by
    the caller, separately from the fixed modeled reference timestamp.
    """
    from ntp_sync_lab.experiments.delay import DelayResult, MODEL_VERSION

    if not isinstance(result, DelayResult):
        raise InvalidInputError("result must be a DelayResult")
    payload = to_contract(ExchangeResult(
        timestamps=result.timestamps, experiment=Experiment.NETWORK_DELAY,
        source=ResultSource.SIMULATION, result_id=result_id, created_at_utc=created_at_utc,
        provenance="Deterministic synthetic delay model; no network measurement",
        assumptions=result.assumptions, true_offset_ns=result.true_offset_ns,
    ))
    payload["provenance"].update(
        model="constant-offset-equal-rate", model_version=MODEL_VERSION,
        preset_id=result.config.preset_id,
    )
    payload["parameters"] = {
        name: str(getattr(result.config, name))
        for name in ("true_offset_ns", "forward_delay_ns", "reverse_delay_ns",
                     "server_processing_ns", "reference_unix_ns")
    }
    payload["parameters"]["preset_id"] = result.config.preset_id
    payload["data"].update(
        forward_delay_ns=str(result.config.forward_delay_ns),
        reverse_delay_ns=str(result.config.reverse_delay_ns),
        conclusion=result.conclusion,
    )
    return payload


def delay_to_json(result: "DelayResult", *, result_id: str, created_at_utc: datetime) -> str:
    return json.dumps(
        delay_to_contract(result, result_id=result_id, created_at_utc=created_at_utc),
        indent=2, sort_keys=True, allow_nan=False,
    )


def series_contract(results, parameters, *, result_id, created_at_utc):
    """Schema-1 delay series, containing complete independently replayable points."""
    first = delay_to_contract(results[0], result_id=result_id, created_at_utc=created_at_utc)
    first['parameters'] = copy.deepcopy(parameters)
    first['provenance']['description'] = 'Deterministic synthetic delay parameter sweep; no network measurement'
    first['provenance']['preset_id'] = None
    first['data'] = {'points': [delay_to_contract(
        result, result_id=f'{result_id}:{index}', created_at_utc=created_at_utc,
    ) for index, result in enumerate(results)]}
    return first


def sync_to_contract(
    result: "SyncResult", *, result_id: str, created_at_utc: datetime,
) -> dict[str, object]:
    """Schema-1 simulation envelope, with exact backend-generated step data."""
    from ntp_sync_lab.experiments.synchronization import MODEL_VERSION, SyncResult

    if not isinstance(result, SyncResult):
        raise InvalidInputError("result must be a SyncResult")
    payload = to_contract(ExchangeResult(
        timestamps=result.measurement.timestamps, experiment=Experiment.CLOCK_SYNC,
        source=ResultSource.SIMULATION, result_id=result_id, created_at_utc=created_at_utc,
        provenance="Deterministic virtual clock step model; no OS synchronization or network measurement",
        assumptions=result.assumptions, true_offset_ns=result.true_offset_ns,
    ))
    payload["provenance"].update(model="virtual-clock-step", model_version=MODEL_VERSION)
    payload["parameters"] = {
        name: str(getattr(result.config, name))
        for name in ("initial_client_error_ns", "forward_delay_ns", "reverse_delay_ns",
                     "server_processing_ns", "reference_unix_ns")
    }
    payload["parameters"]["mode"] = result.config.mode

    def snapshot_data(snapshot):
        return {
            "reference_unix_ns": str(snapshot.reference_unix_ns),
            "virtual_client_unix_ns": _offset_string(snapshot.virtual_client_unix_ns),
            "client_error_ns": _offset_string(snapshot.client_error_ns),
        }

    event = result.correction_event
    payload["data"].update(
        initial_client_error_ns=str(result.initial_client_error_ns),
        applied_correction_ns=_offset_string(result.applied_correction_ns),
        final_client_error_ns=_offset_string(result.final_client_error_ns),
        measurement=delay_to_contract(
            result.measurement, result_id=f"{result_id}:measurement", created_at_utc=created_at_utc,
        ),
        before=snapshot_data(event.before), after=snapshot_data(event.after),
        correction_event={
            "mode": event.mode, "reference_unix_ns": str(event.reference_unix_ns),
            "applied_correction_ns": _offset_string(event.applied_correction_ns),
            "before_sequence": 1, "after_sequence": 2,
        },
        timeline=[{
            "sequence": point.sequence, "stage": point.stage,
            **snapshot_data(point.snapshot),
            "applied_correction_ns": _offset_string(point.applied_correction_ns),
        } for point in result.timeline],
        explanation=list(result.explanation), conclusion=result.conclusion,
    )
    return payload


def sync_to_json(result: "SyncResult", *, result_id: str, created_at_utc: datetime) -> str:
    return json.dumps(
        sync_to_contract(result, result_id=result_id, created_at_utc=created_at_utc),
        indent=2, sort_keys=True, allow_nan=False,
    )
