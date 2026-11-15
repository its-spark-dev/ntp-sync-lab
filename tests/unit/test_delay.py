"""Hand-derived model expectations; expected metrics never use the core helper.

With r0=0 ms, theta=100 ms and p=5 ms, the four required quartets are:
low:     (-100, 20, 25, -55) -> offset (120+80)/2=100; RTT 45-5=40
high:    (-100, 80, 85,  65) -> offset (180+20)/2=100; RTT 165-5=160
forward: (-100, 60, 65, -15) -> offset (160+80)/2=120; RTT 85-5=80
reverse: (-100, 20, 25, -15) -> offset (120+40)/2=80;  RTT 85-5=80
The engine adds its fixed reference epoch to every event. Truth is known from
the input, not inferred from a live exchange. All units below are nanoseconds.
"""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal, Inexact, ROUND_UP, localcontext
from fractions import Fraction
import json
import socket
import time

import pytest

import ntp_sync_lab.experiments.delay as delay_module
from ntp_sync_lab.core.calculations import calculate_exchange
from ntp_sync_lab.errors import InvalidInputError
from ntp_sync_lab.experiments.delay import (
    DEFAULT_REFERENCE_UNIX_NS, DELAY_PRESETS, DelayConfig, equal_increase_sweep,
    fixed_rtt_sweep, make_delay_config, run_delay,
)
from ntp_sync_lab.models import ExchangeMetrics, ResultSource, TimestampQuad
from ntp_sync_lab.serialization import delay_to_contract, delay_to_json

CREATED = datetime(2026, 11, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'name,relative_ms,estimate_ms,rtt_ms,error_ms',
    [
        ('symmetric-low', (-100, 20, 25, -55), 100, 40, 0),
        ('symmetric-high', (-100, 80, 85, 65), 100, 160, 0),
        ('asymmetric-forward', (-100, 60, 65, -15), 120, 80, 20),
        ('asymmetric-reverse', (-100, 20, 25, -15), 80, 80, -20),
    ],
)
def test_required_presets_against_independently_derived_values(
    name, relative_ms, estimate_ms, rtt_ms, error_ms,
):
    result = run_delay(make_delay_config(preset=name))
    assert isinstance(result.timestamps, TimestampQuad)
    assert isinstance(result.metrics, ExchangeMetrics)
    assert result.timestamps == TimestampQuad(*(
        DEFAULT_REFERENCE_UNIX_NS + value * 1_000_000 for value in relative_ms
    ))
    assert result.true_offset_ns == 100_000_000
    assert result.metrics.estimated_offset_ns == estimate_ms * 1_000_000
    assert result.metrics.round_trip_delay_ns == rtt_ms * 1_000_000
    assert result.metrics.server_processing_ns == 5_000_000
    assert result.estimation_error_ns == error_ms * 1_000_000
    assert result.source is ResultSource.SIMULATION
    assert result.config.preset_id == name


@pytest.mark.parametrize(
    'theta,expected',
    [
        (100_000_000, (-100_000_000, 20_000_000, 25_000_000, -55_000_000)),
        (0, (0, 20_000_000, 25_000_000, 45_000_000)),
        (-100_000_000, (100_000_000, 20_000_000, 25_000_000, 145_000_000)),
    ],
)
def test_offset_signs_and_timestamp_clock_ownership(theta, expected):
    result = run_delay(DelayConfig(true_offset_ns=theta, reference_unix_ns=0))
    assert result.timestamps == TimestampQuad(*expected)
    assert result.metrics.estimated_offset_ns == theta
    assert result.estimation_error_ns == 0


@pytest.mark.parametrize('offset', [-60_000_000_000, 0, 60_000_000_000])
def test_symmetric_delay_invariance_over_approved_bounds(offset):
    results = [run_delay(DelayConfig(
        true_offset_ns=offset, forward_delay_ns=value, reverse_delay_ns=value,
    )) for value in (0, 1, 20_000_000, 80_000_000, 2_000_000_000)]
    assert all(item.metrics.estimated_offset_ns == offset for item in results)
    assert all(item.estimation_error_ns == 0 for item in results)
    assert [item.metrics.round_trip_delay_ns for item in results] == [
        0, 2, 40_000_000, 160_000_000, 4_000_000_000,
    ]


@pytest.mark.parametrize('forward,reverse,error', [(1, 0, Fraction(1, 2)), (0, 1, Fraction(-1, 2))])
def test_half_nanosecond_bias_is_exact(forward, reverse, error):
    result = run_delay(DelayConfig(
        true_offset_ns=-7, forward_delay_ns=forward, reverse_delay_ns=reverse,
        server_processing_ns=0, reference_unix_ns=2**100,
    ))
    assert result.metrics.estimated_offset_ns == -7 + error
    assert result.estimation_error_ns == error
    assert isinstance(result.estimation_error_ns, Fraction)
    assert result.metrics.round_trip_delay_ns == 1


def test_processing_cancels_from_metrics_but_not_elapsed_time():
    results = [run_delay(DelayConfig(
        forward_delay_ns=60_000_000, reverse_delay_ns=20_000_000, server_processing_ns=p,
    )) for p in (0, 5_000_000, 500_000_000)]
    assert [item.metrics.client_elapsed_ns for item in results] == [80_000_000, 85_000_000, 580_000_000]
    assert all(item.metrics.estimated_offset_ns == 120_000_000 for item in results)
    assert all(item.metrics.round_trip_delay_ns == 80_000_000 for item in results)


def test_engine_delegates_to_existing_authoritative_calculator(monkeypatch):
    calls = []
    def spy(timestamps):
        calls.append(timestamps)
        return calculate_exchange(timestamps)
    monkeypatch.setattr(delay_module, 'calculate_exchange', spy)
    result = run_delay(DelayConfig())
    assert calls == [result.timestamps]


def test_fixed_80_ms_sweep_orders_points_and_changes_error_at_constant_rtt():
    points = fixed_rtt_sweep(round_trip_ms=80, points=9)
    assert isinstance(points, tuple) and len(points) == 9
    assert [p.config.forward_delay_ns for p in points] == [i * 10_000_000 for i in range(9)]
    assert [p.config.reverse_delay_ns for p in points] == [i * 10_000_000 for i in range(8, -1, -1)]
    assert [p.metrics.estimated_offset_ns for p in points] == [i * 10_000_000 for i in range(6, 15)]
    assert [p.estimation_error_ns for p in points] == [i * 10_000_000 for i in range(-4, 5)]
    assert all(p.metrics.round_trip_delay_ns == 80_000_000 for p in points)


@pytest.mark.parametrize('total_ms,expected_forward_ns', [
    ('0.000001', [0, 0, 1]), ('0.000003', [0, 2, 3]), ('0', [0, 0, 0]),
])
def test_fixed_sweep_rounds_forward_once_ties_to_even_and_preserves_total(total_ms, expected_forward_ns):
    points = fixed_rtt_sweep(round_trip_ms=total_ms, points=3)
    assert [p.config.forward_delay_ns for p in points] == expected_forward_ns
    total = expected_forward_ns[-1]
    assert all(p.config.forward_delay_ns + p.config.reverse_delay_ns == total for p in points)
    assert all(p.metrics.round_trip_delay_ns == total for p in points)


@pytest.mark.parametrize('count', [2, 200])
def test_sweep_size_boundaries_and_duplicate_tiny_delay_points(count):
    points = fixed_rtt_sweep(round_trip_ms='0.000001', points=count)
    assert len(points) == count
    assert points[0].config.forward_delay_ns == 0 and points[-1].config.forward_delay_ns == 1
    assert all(p.metrics.round_trip_delay_ns == 1 for p in points)


@pytest.mark.parametrize('preset,expected_error,expected_rtts', [
    ('symmetric-low', 0, [40_000_000, 80_000_000, 160_000_000]),
    ('asymmetric-forward', 20_000_000, [80_000_000, 120_000_000, 200_000_000]),
])
def test_equal_increase_comparison_preserves_asymmetry_bias(preset, expected_error, expected_rtts):
    points = equal_increase_sweep(DELAY_PRESETS[preset], increments_ms=[0, 20, 60])
    assert [p.metrics.round_trip_delay_ns for p in points] == expected_rtts
    assert all(p.estimation_error_ns == expected_error for p in points)
    assert all(p.config.preset_id is None for p in points)  # generated grid, not claimed preset selection


def test_nanosecond_inputs_and_conversion_are_independent_of_decimal_context():
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        config = make_delay_config(
            true_offset_ms=Decimal('-123.456789'), forward_ms='0.000001',
            reverse_ms=Decimal('1999.999999'), processing_ms='499.999999', reference_unix_ns=-2**100,
        )
    assert config.true_offset_ns == -123_456_789
    assert config.forward_delay_ns == 1
    assert config.reverse_delay_ns == 1_999_999_999
    assert config.server_processing_ns == 499_999_999
    assert config.reference_unix_ns == -2**100


def test_inclusive_numeric_bounds_and_scientific_notation():
    config = make_delay_config(true_offset_ms='-60000', forward_ms='2e3', reverse_ms=2000, processing_ms=500)
    assert config.true_offset_ns == -60_000_000_000
    assert config.forward_delay_ns == config.reverse_delay_ns == 2_000_000_000
    assert config.server_processing_ns == 500_000_000
    assert make_delay_config(true_offset_ms='6e4').true_offset_ns == 60_000_000_000
    assert make_delay_config(forward_ms='1e-6').forward_delay_ns == 1


@pytest.mark.parametrize('kwargs', [
    {'forward_ms': '-0.000001'}, {'reverse_ms': -1}, {'processing_ms': -1},
    {'true_offset_ms': '60000.000001'}, {'true_offset_ms': '-60000.000001'},
    {'forward_ms': '2000.000001'}, {'reverse_ms': 2001}, {'processing_ms': '500.000001'},
    {'forward_ms': '0.0000001'}, {'reverse_ms': '1.0000000'},
    {'true_offset_ms': Decimal('NaN')}, {'forward_ms': 'Infinity'}, {'processing_ms': 'sNaN'},
    {'forward_ms': 1.0}, {'reverse_ms': True}, {'true_offset_ms': Fraction(1, 2)},
    {'forward_ms': float('nan')}, {'forward_ms': 'not a number'}, {'reference_unix_ns': 1.0},
    {'preset': 'missing'}, {'preset': []}, {'preset': 'symmetric-low', 'forward_ms': 20},
    {'preset': 'symmetric-low', 'reference_unix_ns': DEFAULT_REFERENCE_UNIX_NS},
])
def test_invalid_user_inputs_raise_domain_error(kwargs):
    with pytest.raises(InvalidInputError) as error:
        make_delay_config(**kwargs)
    assert error.value.code == 'INVALID_INPUT'


@pytest.mark.parametrize('kwargs', [
    {'true_offset_ns': 60_000_000_001}, {'forward_delay_ns': -1}, {'reverse_delay_ns': 2_000_000_001},
    {'server_processing_ns': 500_000_001}, {'forward_delay_ns': 1.0}, {'true_offset_ns': True},
    {'reference_unix_ns': None}, {'preset_id': 'symmetric-high'},
])
def test_native_nanosecond_config_cannot_bypass_bounds_or_preset_identity(kwargs):
    with pytest.raises(InvalidInputError):
        DelayConfig(**kwargs)


@pytest.mark.parametrize('points', [0, 1, 201, True, 3.0, None, float('inf')])
def test_invalid_fixed_sweep_sizes(points):
    with pytest.raises(InvalidInputError):
        fixed_rtt_sweep(round_trip_ms=80, points=points)


@pytest.mark.parametrize('total', [-1, 2001, '2000.000001', '0.0000001', float('nan')])
def test_fixed_sweep_total_must_support_both_endpoints_within_one_way_bounds(total):
    with pytest.raises(InvalidInputError):
        fixed_rtt_sweep(round_trip_ms=total)


@pytest.mark.parametrize('increments', [[], [0], [0]*201, [20, 0], [0, 0], [-1, 0], [0, 2000],
                                         [0, '0.0000001'], [0, float('inf')], '0,20', None])
def test_invalid_equal_increase_sweep_is_rejected(increments):
    with pytest.raises(InvalidInputError):
        equal_increase_sweep(DelayConfig(), increments_ms=increments)


def test_unsupported_configuration_combinations_are_not_silently_ignored():
    with pytest.raises(TypeError):
        fixed_rtt_sweep(round_trip_ms=80, forward_ms=20)
    with pytest.raises(TypeError):
        fixed_rtt_sweep(round_trip_ms=80, preset='symmetric-low')
    with pytest.raises(InvalidInputError):
        run_delay({'forward_ms': 20})
    with pytest.raises(InvalidInputError):
        equal_increase_sweep(None, increments_ms=[0, 20])


def test_models_and_preset_registry_are_immutable():
    with pytest.raises(TypeError):
        DELAY_PRESETS['symmetric-low'] = DelayConfig()
    with pytest.raises(FrozenInstanceError):
        DELAY_PRESETS['symmetric-low'].forward_delay_ns = 1
    with pytest.raises(FrozenInstanceError):
        run_delay(DelayConfig()).metrics = None


def test_serialization_preserves_schema_simulation_provenance_and_known_truth():
    result = run_delay(make_delay_config(preset='asymmetric-forward'))
    payload = json.loads(delay_to_json(result, result_id='delay-fixture', created_at_utc=CREATED))
    assert payload['schema_version'] == '1'
    assert payload['source'] == 'simulation' and payload['experiment'] == 'network_delay'
    assert payload['created_at_utc'] == '2026-11-15T00:00:00Z'
    assert payload['parameters']['reference_unix_ns'] == str(DEFAULT_REFERENCE_UNIX_NS)
    assert payload['parameters']['preset_id'] == 'asymmetric-forward'
    assert payload['parameters']['forward_delay_ns'] == '60000000'
    assert payload['data']['true_offset_ns'] == '100000000'
    assert payload['data']['estimated_offset_ns'] == '120000000'
    assert payload['data']['estimation_error_ns'] == '20000000'
    assert payload['data']['round_trip_delay_ns'] == '80000000'
    assert payload['provenance']['model_version'] == '1'
    assert 'synthetic' in payload['provenance']['description']
    assert 'capture_time_utc' not in payload['provenance']
    assert 'response_packet_hex' not in payload['data']
    assert any('No packet loss, jitter, oscillator drift' in text for text in payload['assumptions'])
    assert any('Actual public NTP' in text for text in payload['assumptions'])
    assert 'positive' in payload['data']['conclusion']


def test_reproducibility_includes_large_reference_and_half_nanosecond_json():
    config = DelayConfig(true_offset_ns=0, forward_delay_ns=0, reverse_delay_ns=1,
                         server_processing_ns=0, reference_unix_ns=2**100)
    result = run_delay(config)
    assert result == run_delay(config)
    first = delay_to_json(result, result_id='repeatable', created_at_utc=CREATED)
    assert first == delay_to_json(run_delay(config), result_id='repeatable', created_at_utc=CREATED)
    payload = json.loads(first)
    assert payload['data']['estimated_offset_ns'] == payload['data']['estimation_error_ns'] == '-0.5'
    assert int(payload['data']['timestamps']['t1_unix_ns']) == 2**100
    payload['parameters']['forward_delay_ns'] = 'changed'
    assert delay_to_json(result, result_id='repeatable', created_at_utc=CREATED) == first


def test_invalid_serialization_metadata_reuses_existing_domain_validation():
    result = run_delay(DelayConfig())
    with pytest.raises(InvalidInputError):
        delay_to_contract(result, result_id='', created_at_utc=CREATED)
    with pytest.raises(InvalidInputError):
        delay_to_contract(result, result_id='test', created_at_utc=datetime(2026, 11, 15))
    with pytest.raises(InvalidInputError):
        delay_to_contract(None, result_id='test', created_at_utc=CREATED)


def test_execution_and_serialization_need_no_network_clocks_or_sleep(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No networking, live clock reads, or sleeps in a delay simulation')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    for name in ('time_ns', 'monotonic_ns', 'sleep'):
        monkeypatch.setattr(time, name, forbidden)
    for config in DELAY_PRESETS.values():
        delay_to_json(run_delay(config), result_id='offline-fixture', created_at_utc=CREATED)
    assert len(fixed_rtt_sweep(round_trip_ms=80)) == 9
    assert len(equal_increase_sweep(DelayConfig(), increments_ms=[0, 60])) == 2
