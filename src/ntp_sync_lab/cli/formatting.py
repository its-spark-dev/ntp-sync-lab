"""Educational terminal presentation of validated contracts; no authoritative calculator."""

from datetime import datetime, timezone
from fractions import Fraction
import textwrap

from ntp_sync_lab.experiments.replay import original_recording

OBJECTIVES = {
    'real_exchange': 'Observe an NTP UDP exchange and estimate relative clock offset from four timestamps.',
    'network_delay': 'Distinguish true offset, estimated offset, estimation error, and network RTT.',
    'clock_sync': 'Use a modeled NTP estimate to step a virtual clock and inspect the residual error.',
}


def exact_decimal(value):
    value = Fraction(value)
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    if denominator != 1:
        return str(value)
    sign = '-' if value < 0 else ''
    whole, remainder = divmod(abs(value.numerator), value.denominator)
    digits = ''
    while remainder:
        digit, remainder = divmod(remainder * 10, value.denominator)
        digits += str(digit)
    return f'{sign}{whole}' + ('.' + digits if digits else '')


def ms(value):
    return exact_decimal(Fraction(value) / 1_000_000) + ' ms'


def timestamp(value):
    number = Fraction(value)
    seconds = number // 1_000_000_000
    ns = number - seconds * 1_000_000_000
    try:
        readable = datetime.fromtimestamp(seconds, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        whole, _, fraction = exact_decimal(ns).partition('.')
        digits = f'{int(whole):09d}' + fraction
        return f'{readable}.{digits} UTC\n      Unix ns: {value}'
    except (ValueError, OverflowError, OSError):
        return f'Unix ns {value} (outside calendar display range)'


def error_text(error):
    details = error.get('details', {})
    retry = details.get('retry_after_ns')
    advice = {
        'NTP_TIMEOUT': 'UDP 123 may be blocked or the server unavailable. Use an explicit offline replay.',
        'DNS_FAILURE': 'Check the hostname/network, or use an offline scenario.',
        'RATE_LIMITED': 'Wait for the destination cooldown; do not change the cache to bypass it.',
        'SERVER_CONTROL': 'Stop this target and review its server policy before any later probe.',
        'LIVE_STATE_UNAVAILABLE': 'Review the local polling-state problem before further live requests.',
    }.get(error['code'], 'Review the supplied inputs or diagnostic details; no automatic retry was made.')
    if retry is not None:
        advice += f' Retry after at least {exact_decimal(Fraction(retry) / 1_000_000_000)} seconds.'
    return f"{error['code']}: {error['message']}\n{advice}"


def _single(document, label):
    data, params = document['data'], document['parameters']
    experiment = document['experiment']
    lines = [f'{label} | {experiment}', 'Experiment Objective', OBJECTIVES[experiment],
             '', 'Inputs & Conditions', f"Original result date: {document['created_at_utc']}",
             f"Source: {document['provenance']['description']}"]
    for key, value in params.items():
        if value is not None:
            label = key.removesuffix('_ns').replace('_', ' ')
            display = timestamp(value) if key == 'reference_unix_ns' else ms(value) if key.endswith('_ns') else value
            lines.append(f'  {label}: {display}')
    if experiment == 'real_exchange':
        header = data['server_header']
        peer = document['provenance']['peer']
        lines.append(f"Server: {peer['address']}:{peer['port']} | v{header['version']} mode {header['mode']} | stratum {header['stratum']} | {header['packet_length']} bytes")
    lines.extend(['', 'Four NTP Timestamps'])
    values = []
    for index, owner in ((1, 'Client transmission'), (2, 'Server reception'),
                         (3, 'Server transmission'), (4, 'Client reception')):
        value = data['timestamps'][f't{index}_unix_ns']
        values.append(int(value))
        lines.append(f'  T{index} {owner}: {timestamp(value)}')
    t1, t2, t3, t4 = values
    lines.extend(['', 'Calculations',
        '  Estimated offset = ((T2 - T1) + (T3 - T4)) / 2; server minus client',
        f"    = ({ms(t2-t1)} + {ms(t3-t4)}) / 2 = {ms(data['estimated_offset_ns'])}",
        '  Network RTT = (T4 - T1) - (T3 - T2)',
        f"    = {ms(data['client_elapsed_ns'])} - {ms(data['server_processing_ns'])} = {ms(data['round_trip_delay_ns'])}",
        '', 'Results', f"  Estimated NTP offset: {ms(data['estimated_offset_ns'])}",
        f"  Network RTT: {ms(data['round_trip_delay_ns'])}"])
    if data['true_offset_ns'] is None:
        lines.extend(['  True offset: unknown', '  Estimation error: unknown',
                      '  Actual one-way delays are unknown; asymmetry can bias this estimate.'])
    else:
        lines.extend([f"  Known model true offset: {ms(data['true_offset_ns'])}",
                      f"  Estimation error = estimate - truth: {ms(data['estimation_error_ns'])}"])
    if experiment == 'clock_sync':
        lines.extend([f"  Initial client-minus-reference error: {ms(data['initial_client_error_ns'])}",
                      f"  Applied virtual step = estimated offset: {ms(data['applied_correction_ns'])}",
                      f"  Final residual client error: {ms(data['final_client_error_ns'])}",
                      f"  Common reference instant: {timestamp(data['before']['reference_unix_ns'])}",
                      f"  Virtual time before: {timestamp(data['before']['virtual_client_unix_ns'])}",
                      f"  Virtual time after:  {timestamp(data['after']['virtual_client_unix_ns'])}",
                      '  Step timeline: measurement_start -> before_correction -> after_correction',
                      '  Before/after share one reference instant. Only virtual time changes.'])
    lines.extend(['', 'Assumptions & Limitations'])
    for text in document['assumptions']:
        lines.extend(textwrap.wrap(text, width=94, initial_indent='  - ', subsequent_indent='    '))
    conclusion = data.get('conclusion', 'Four timestamps estimate relative time; unknown path asymmetry and software timing limit accuracy.')
    lines.extend(['', 'Conclusion', conclusion])
    return '\n'.join(lines)


def format_document(document):
    replay = document.get('source') == 'replay'
    original = original_recording(document)
    label = f"REPLAY (original {original['source'].upper()}; no request sent)" if replay else original['source'].upper()
    prefix = ''
    if replay:
        prefix = f"{label}\nReplayed at: {document['provenance']['replayed_at_utc']}\nOriginal capture/creation dates are preserved below.\n\n"
    if 'attempts' in original:
        lines = [prefix + f"{label} | requested {original['requested_count']}; completed {len(original['attempts'])}"]
        for attempt in original['attempts']:
            lines.append(f"\nAttempt {attempt['number']}")
            if attempt['result'] is not None:
                lines.append(_single(attempt['result'], label))
            else:
                error = attempt['error']
                details = error['details']
                lines.append('\n'.join([
                    'Experiment Objective', OBJECTIVES['real_exchange'], 'Inputs & Conditions',
                    f"{label}; server {original['server']}", 'Four NTP Timestamps',
                    '  No validated quartet available. Unobserved server timestamps remain unavailable.',
                    *[f"  Captured {key}: {timestamp(details[key])}" for key in ('t1_unix_ns', 't4_unix_ns') if key in details],
                    'Calculations', '  Offset/RTT are not computed from an invalid exchange.',
                    'Results', error_text(error), 'Assumptions & Limitations',
                    '  No successful observation or true offset is inferred from a failed attempt.',
                    'Conclusion', 'The measurement failed; use the explicit offline workflow if needed.',
                ]))
        summary = original['summary']
        lines.append('\nDescriptive batch summary (valid results only; not an accuracy bound)')
        lines.append('  No valid samples.' if summary is None else
                     f"  {summary['valid_count']} valid; median offset {ms(summary['median_offset_ns'])}; minimum RTT {ms(summary['minimum_round_trip_delay_ns'])}; offset range {ms(summary['offset_range_ns'])}")
        if original['interrupted']:
            lines.append('Interrupted; completed attempts preserved.')
        return '\n'.join(lines)
    if 'points' in original.get('data', {}):
        points = original['data']['points']
        blocks = [prefix + f"{label} | {original['parameters']['sweep_kind']} sweep",
                  'Worked first point (all points are preserved completely in JSON):',
                  _single(points[0], label),
                  '\nSweep comparison — all columns in milliseconds',
                  'Point | Forward | Reverse | RTT | True offset | Estimate | Error']
        for index, point in enumerate(points, 1):
            data = point['data']
            values = [data[key] for key in ('forward_delay_ns', 'reverse_delay_ns',
                      'round_trip_delay_ns', 'true_offset_ns', 'estimated_offset_ns', 'estimation_error_ns')]
            blocks.append(f'{index:5} | ' + ' | '.join(exact_decimal(Fraction(v) / 1_000_000) for v in values))
        blocks.append('Use --format json or --output PATH to inspect every point quartet and its substitutions.')
        return '\n'.join(blocks)
    return prefix + _single(original, label)
