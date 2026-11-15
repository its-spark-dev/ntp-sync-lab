"""Independent expected values for the step model; no expected metrics helper.

At r0=0 ms, client error b=+120 ms makes true NTP offset theta=-120 ms.
- 20/20 ms, p=5: T=(120,20,25,165). Offset=(-100-140)/2=-120;
  RTT=(165-120)-(25-20)=40. Add -120 to b -> residual 0.
- 60/20 ms, p=5: T=(120,60,65,205). Offset=(-60-140)/2=-100;
  RTT=85-5=80. Add -100 -> residual +20.
- 20/60 ms, p=5: T=(120,20,25,205). Offset=(-100-180)/2=-140;
  RTT=85-5=80. Add -140 -> residual -20.
Before/after clocks are compared at reference 45/85/85 ms respectively;
their virtual times are (165,45), (205,105), (205,65) ms at those instants.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal, Inexact, localcontext
from fractions import Fraction
import json
import os
import socket
import subprocess
import time

import pytest

import ntp_sync_lab.experiments.synchronization as sync_module
from ntp_sync_lab.errors import InvalidInputError
from ntp_sync_lab.experiments.delay import DelayConfig, run_delay
from ntp_sync_lab.experiments.synchronization import (
    ClockSnapshot, CorrectionEvent, SyncConfig, SyncResult, SyncTimelinePoint,
    VirtualClock, make_sync_config, run_sync,
)
from ntp_sync_lab.models import ExchangeResult, Experiment, ResultSource, TimestampQuad
from ntp_sync_lab.serialization import sync_to_contract, sync_to_json

CREATED = datetime(2026, 11, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize('forward,reverse,quartet,estimate,event_ms,after_ms,residual', [
    (20, 20, (120, 20, 25, 165), -120, 45, 45, 0),
    (60, 20, (120, 60, 65, 205), -100, 85, 105, 20),
    (20, 60, (120, 20, 25, 205), -140, 85, 65, -20),
])
def test_required_scenarios_against_independently_derived_values(
    forward, reverse, quartet, estimate, event_ms, after_ms, residual,
):
    result = run_sync(make_sync_config(forward_ms=forward, reverse_ms=reverse, reference_unix_ns=0))
    assert result.initial_client_error_ns == 120_000_000
    assert result.true_offset_ns == -120_000_000
    assert result.measurement.timestamps == TimestampQuad(*(v * 1_000_000 for v in quartet))
    assert result.measurement.metrics.estimated_offset_ns == estimate * 1_000_000
    assert result.applied_correction_ns == estimate * 1_000_000
    assert result.final_client_error_ns == residual * 1_000_000
    assert result.measurement.metrics.round_trip_delay_ns == (forward + reverse) * 1_000_000
    assert result.before.reference_unix_ns == result.after.reference_unix_ns == event_ms * 1_000_000
    assert result.before.virtual_client_unix_ns == quartet[-1] * 1_000_000
    assert result.after.virtual_client_unix_ns == after_ms * 1_000_000
    assert result.source is result.measurement.source is ResultSource.SIMULATION
    assert result.correction_event.mode == 'step'


@pytest.mark.parametrize('initial_ms,forward,reverse,correction_ms,residual_ms', [
    (-120, 20, 20, 120, 0), (-120, 60, 20, 140, 20), (-120, 20, 60, 100, -20),
    (0, 20, 20, 0, 0), (0, 60, 20, 20, 20), (0, 20, 60, -20, -20),
])
def test_client_behind_and_zero_initial_error(initial_ms, forward, reverse, correction_ms, residual_ms):
    result = run_sync(make_sync_config(client_offset_ms=initial_ms, forward_ms=forward, reverse_ms=reverse))
    assert result.true_offset_ns == -initial_ms * 1_000_000
    assert result.applied_correction_ns == correction_ms * 1_000_000
    assert result.final_client_error_ns == residual_ms * 1_000_000
    assert result.after.client_error_ns == residual_ms * 1_000_000
    if initial_ms == 0:
        assert 'aligned' in result.explanation[0]
    else:
        assert 'behind' in result.explanation[0]


@pytest.mark.parametrize('client_offset_ms,expected_ns', [('0.125', 125_000), ('-0.125', -125_000)])
def test_fractional_millisecond_initial_errors_preserve_exact_signs(client_offset_ms, expected_ns):
    result = run_sync(make_sync_config(client_offset_ms=client_offset_ms))
    assert result.initial_client_error_ns == expected_ns
    assert result.applied_correction_ns == -expected_ns
    assert result.final_client_error_ns == 0


@pytest.mark.parametrize('forward,reverse,residual', [(1, 0, Fraction(1, 2)), (0, 1, Fraction(-1, 2))])
def test_half_nanosecond_correction_residual_and_large_virtual_timestamp(forward, reverse, residual):
    epoch = 2**100
    result = run_sync(SyncConfig(
        initial_client_error_ns=3, forward_delay_ns=forward, reverse_delay_ns=reverse,
        server_processing_ns=0, reference_unix_ns=epoch,
    ))
    assert result.applied_correction_ns == -3 + residual
    assert result.final_client_error_ns == residual
    assert isinstance(result.applied_correction_ns, Fraction)
    assert result.before.reference_unix_ns == result.after.reference_unix_ns == epoch + 1
    assert result.after.virtual_client_unix_ns == epoch + 1 + residual
    encoded = json.loads(sync_to_json(result, result_id='fractional', created_at_utc=CREATED))
    assert Fraction(encoded['data']['after']['virtual_client_unix_ns']) == epoch + 1 + residual
    assert encoded['data']['final_client_error_ns'] == ('0.5' if forward else '-0.5')


@pytest.mark.parametrize('initial_ns', [-60_000_000_000, -1, 0, 1, 60_000_000_000])
@pytest.mark.parametrize('forward_ns,reverse_ns', [(0, 0), (1, 0), (0, 1), (60_000_000, 20_000_000), (0, 2_000_000_000)])
def test_both_residual_invariants_across_representative_configurations(initial_ns, forward_ns, reverse_ns):
    result = run_sync(SyncConfig(
        initial_client_error_ns=initial_ns, forward_delay_ns=forward_ns,
        reverse_delay_ns=reverse_ns, server_processing_ns=500_000_000,
    ))
    independently_expected = Fraction(forward_ns - reverse_ns, 2)
    assert result.final_client_error_ns == initial_ns + result.measurement.metrics.estimated_offset_ns
    assert result.final_client_error_ns == independently_expected
    assert result.estimation_error_ns == independently_expected
    assert result.after.client_error_ns == independently_expected


def test_processing_time_cancels_and_moves_only_the_event_reference_time():
    results = [run_sync(SyncConfig(
        forward_delay_ns=60_000_000, reverse_delay_ns=20_000_000,
        server_processing_ns=processing, reference_unix_ns=0,
    )) for processing in (0, 5_000_000, 500_000_000)]
    assert [r.correction_reference_unix_ns for r in results] == [80_000_000, 85_000_000, 580_000_000]
    assert all(r.applied_correction_ns == -100_000_000 for r in results)
    assert all(r.final_client_error_ns == 20_000_000 for r in results)
    assert all(r.measurement.metrics.round_trip_delay_ns == 80_000_000 for r in results)


def test_existing_delay_engine_supplies_the_correction_not_the_visible_initial_label(monkeypatch):
    calls = []
    def spy(config):
        calls.append(config)
        return run_delay(config)
    monkeypatch.setattr(sync_module, 'run_delay', spy)
    config = make_sync_config(forward_ms=60, reverse_ms=20)
    result = run_sync(config)
    assert calls == [config.to_delay_config()]
    assert calls[0].true_offset_ns == -120_000_000
    assert result.applied_correction_ns == result.measurement.metrics.estimated_offset_ns == -100_000_000
    assert result.applied_correction_ns != -result.initial_client_error_ns


def test_step_timeline_uses_logical_sequence_and_same_instant_for_before_after():
    result = run_sync(SyncConfig(reference_unix_ns=0))
    timeline = result.timeline
    assert [p.sequence for p in timeline] == [0, 1, 2]
    assert [p.stage for p in timeline] == ['measurement_start', 'before_correction', 'after_correction']
    assert [p.snapshot.reference_unix_ns for p in timeline] == [0, 45_000_000, 45_000_000]
    assert [p.applied_correction_ns for p in timeline] == [0, 0, -120_000_000]
    assert [p.snapshot.virtual_client_unix_ns for p in timeline] == [120_000_000, 165_000_000, 45_000_000]
    assert timeline[0].snapshot.virtual_client_unix_ns == result.measurement.timestamps.t1_unix_ns
    assert timeline[1].snapshot.virtual_client_unix_ns == result.measurement.timestamps.t4_unix_ns
    assert timeline[1].snapshot == result.before and timeline[2].snapshot == result.after


def test_zero_duration_exchange_has_a_well_defined_instantaneous_step():
    result = run_sync(SyncConfig(forward_delay_ns=0, reverse_delay_ns=0, server_processing_ns=0))
    assert len(result.timeline) == 3
    assert len({p.snapshot.reference_unix_ns for p in result.timeline}) == 1
    assert result.applied_correction_ns == -120_000_000
    assert result.final_client_error_ns == 0


def test_virtual_step_is_immutable_and_neither_rounds_nor_requires_forward_time():
    before = VirtualClock(1)
    after = before.step(Fraction(-3, 2))
    assert before.client_error_ns == 1 and after.client_error_ns == Fraction(-1, 2)
    assert after.read_at(0).virtual_client_unix_ns == Fraction(-1, 2)
    with pytest.raises(FrozenInstanceError):
        after.client_error_ns = 0
    with pytest.raises(FrozenInstanceError):
        after.read_at(0).reference_unix_ns = 5


def test_config_conversion_reuses_precision_rules_without_decimal_context_rounding():
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        config = make_sync_config(client_offset_ms=Decimal('-123.456789'), forward_ms='0.000001',
                                  reverse_ms='1999.999999', processing_ms='499.999999')
    assert config.initial_client_error_ns == -123_456_789
    assert config.forward_delay_ns == 1
    assert config.reverse_delay_ns == 1_999_999_999
    assert config.server_processing_ns == 499_999_999
    assert config.to_delay_config().true_offset_ns == 123_456_789


@pytest.mark.parametrize('kwargs', [
    {'client_offset_ms': '60000.000001'}, {'client_offset_ms': '-60000.000001'},
    {'client_offset_ms': '0.0000001'}, {'client_offset_ms': '1.0000000'},
    {'client_offset_ms': float('nan')}, {'client_offset_ms': Decimal('Infinity')},
    {'client_offset_ms': 1.0}, {'client_offset_ms': True}, {'client_offset_ms': Fraction(1, 2)},
    {'client_offset_ms': 'not a number'}, {'forward_ms': -1}, {'reverse_ms': '2000.000001'},
    {'processing_ms': -1}, {'processing_ms': '500.000001'}, {'forward_ms': 'NaN'},
    {'reverse_ms': float('inf')}, {'reference_unix_ns': 1.5}, {'reference_unix_ns': True},
    {'mode': 'slew'}, {'mode': None},
])
def test_invalid_boundary_parameters_are_rejected_without_clamping(kwargs):
    with pytest.raises(InvalidInputError) as error:
        make_sync_config(**kwargs)
    assert error.value.code == 'INVALID_INPUT'


@pytest.mark.parametrize('kwargs', [
    {'initial_client_error_ns': True}, {'initial_client_error_ns': Fraction(1, 2)},
    {'initial_client_error_ns': 60_000_000_001}, {'initial_client_error_ns': -60_000_000_001},
    {'forward_delay_ns': -1}, {'reverse_delay_ns': 2_000_000_001},
    {'server_processing_ns': 500_000_001}, {'reference_unix_ns': None}, {'mode': 'progressive'},
])
def test_native_config_cannot_bypass_validation(kwargs):
    with pytest.raises(InvalidInputError):
        SyncConfig(**kwargs)


def test_independent_offsets_measurements_or_corrections_cannot_be_injected():
    with pytest.raises(TypeError):
        make_sync_config(client_offset_ms=120, true_offset_ms=100)
    with pytest.raises(TypeError):
        SyncConfig(initial_client_error_ns=120, correction_ns=-120)
    with pytest.raises(TypeError):
        SyncResult(SyncConfig(), measurement=run_delay(DelayConfig()))
    with pytest.raises(InvalidInputError):
        run_sync(run_delay(DelayConfig()))
    with pytest.raises(InvalidInputError):
        SyncResult(None)


@pytest.mark.parametrize('value', [True, 1.0, '1', Fraction(1, 4), float('nan')])
def test_virtual_time_and_corrections_accept_only_supported_exact_values(value):
    with pytest.raises(InvalidInputError):
        VirtualClock(value)
    with pytest.raises(InvalidInputError):
        VirtualClock(0).step(value)
    with pytest.raises(InvalidInputError):
        ClockSnapshot(0, value)


def test_invalid_event_comparisons_and_timeline_inputs_are_rejected():
    before = ClockSnapshot(10, 20)
    with pytest.raises(InvalidInputError, match='same reference instant'):
        CorrectionEvent(before, ClockSnapshot(11, 21), Fraction(1))
    with pytest.raises(InvalidInputError, match='disagree'):
        CorrectionEvent(before, ClockSnapshot(10, 21), Fraction(2))
    with pytest.raises(InvalidInputError):
        CorrectionEvent(before, None, Fraction(1))
    with pytest.raises(InvalidInputError):
        SyncTimelinePoint(True, 'before_correction', before, Fraction(0))
    with pytest.raises(InvalidInputError):
        SyncTimelinePoint(0, 'after_correction', before, Fraction(0))
    with pytest.raises(InvalidInputError):
        SyncTimelinePoint(1, 'before_correction', before, Fraction(1))
    with pytest.raises(InvalidInputError):
        VirtualClock(0).read_at(1.5)


def test_structured_json_has_simulation_provenance_measurement_snapshots_and_step():
    result = run_sync(make_sync_config(forward_ms=20, reverse_ms=60, reference_unix_ns=0))
    payload = json.loads(sync_to_json(result, result_id='sync-fixture', created_at_utc=CREATED))
    assert payload['schema_version'] == '1'
    assert payload['experiment'] == 'clock_sync' and payload['source'] == 'simulation'
    assert payload['provenance']['model'] == 'virtual-clock-step'
    assert payload['parameters']['mode'] == 'step'
    assert payload['parameters']['initial_client_error_ns'] == '120000000'
    data = payload['data']
    assert data['true_offset_ns'] == '-120000000'
    assert data['estimated_offset_ns'] == data['applied_correction_ns'] == '-140000000'
    assert data['final_client_error_ns'] == '-20000000'
    assert data['estimation_error_ns'] == '-20000000'
    assert data['round_trip_delay_ns'] == '80000000'
    assert data['measurement']['experiment'] == 'network_delay'
    assert data['measurement']['source'] == 'simulation'
    assert data['measurement']['data']['timestamps'] == data['timestamps']
    assert data['before']['reference_unix_ns'] == data['after']['reference_unix_ns'] == '85000000'
    assert data['before']['virtual_client_unix_ns'] == '205000000'
    assert data['after']['virtual_client_unix_ns'] == '65000000'
    assert data['correction_event'] == {
        'mode': 'step', 'reference_unix_ns': '85000000', 'applied_correction_ns': '-140000000',
        'before_sequence': 1, 'after_sequence': 2,
    }
    assert data['timeline'][1]['reference_unix_ns'] == data['timeline'][2]['reference_unix_ns']
    assert 'OS synchronization' in payload['provenance']['description']
    assert any('host OS clock is unchanged' in text for text in data['explanation'])
    assert any('drift is a rate difference' in text for text in payload['assumptions'])
    assert 'capture_time_utc' not in payload['provenance']
    assert 'response_packet_hex' not in data


def test_explanation_distinguishes_error_offset_drift_and_os_time():
    result = run_sync(SyncConfig())
    assert 'ahead' in result.explanation[0]
    assert any('different definitions' in text for text in result.explanation)
    assert any('full NTP clock discipline' in text for text in result.assumptions)
    assert 'ideal reference' in result.conclusion


def test_reproducibility_and_fresh_json_containers():
    config = make_sync_config(client_offset_ms='-0.000001', forward_ms='0.000001', reverse_ms=0)
    first = run_sync(config)
    second = run_sync(config)
    assert first == second and first.timeline == second.timeline
    encoded = sync_to_json(first, result_id='repeatable', created_at_utc=CREATED)
    assert encoded == sync_to_json(second, result_id='repeatable', created_at_utc=CREATED)
    payload = sync_to_contract(first, result_id='repeatable', created_at_utc=CREATED)
    payload['data']['timeline'][1]['virtual_client_unix_ns'] = 'changed'
    assert sync_to_json(first, result_id='repeatable', created_at_utc=CREATED) == encoded
    with pytest.raises(FrozenInstanceError):
        first.measurement = None


def test_bad_serialization_inputs_and_false_live_sync_are_rejected():
    with pytest.raises(InvalidInputError):
        sync_to_contract(None, result_id='fixture', created_at_utc=CREATED)
    result = run_sync(SyncConfig())
    with pytest.raises(InvalidInputError):
        sync_to_json(result, result_id='', created_at_utc=CREATED)
    with pytest.raises(InvalidInputError):
        sync_to_json(result, result_id='fixture', created_at_utc=datetime(2026, 11, 15))
    with pytest.raises(InvalidInputError):
        ExchangeResult(timestamps=result.measurement.timestamps, experiment=Experiment.CLOCK_SYNC,
                       source=ResultSource.LIVE, result_id='fixture', created_at_utc=CREATED, provenance='invalid')


def test_sync_and_serialization_never_access_network_or_host_clock(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No network, OS clock read/write, process, or sleep in virtual synchronization')
    for target, names in [
        (socket, ('socket', 'getaddrinfo')), (time, ('time_ns', 'monotonic_ns', 'sleep')),
        (os, ('system',)), (subprocess, ('run', 'Popen')),
    ]:
        for name in names:
            monkeypatch.setattr(target, name, forbidden)
    for name in ('clock_settime', 'clock_settime_ns'):
        if hasattr(time, name):
            monkeypatch.setattr(time, name, forbidden)
    for forward, reverse in [(20, 20), (60, 20), (20, 60)]:
        result = run_sync(make_sync_config(forward_ms=forward, reverse_ms=reverse))
        sync_to_json(result, result_id='offline', created_at_utc=CREATED)
