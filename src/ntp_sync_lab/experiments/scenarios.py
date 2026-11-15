"""Packaged reproducible definitions and genuine saved-capture catalog."""

from importlib.resources import files
import json

from ntp_sync_lab.errors import InvalidInputError, InvalidRecordingError
from ntp_sync_lab.experiments.delay import make_delay_config, run_delay
from ntp_sync_lab.experiments.replay import parse_recording, utc_date
from ntp_sync_lab.experiments.synchronization import make_sync_config, run_sync
from ntp_sync_lab.serialization import delay_to_contract, sync_to_contract


def list_scenarios():
    resource = files('ntp_sync_lab').joinpath('fixtures', 'scenarios', 'catalog.json')
    catalog = json.loads(resource.read_text(encoding='utf-8'))
    if catalog.get('schema_version') != '1':
        raise InvalidRecordingError('unsupported packaged scenario catalog')
    return catalog['scenarios']


def scenario_recording(scenario_id):
    entries = [entry for entry in list_scenarios() if entry['id'] == scenario_id]
    if not entries:
        raise InvalidInputError(f'unknown scenario {scenario_id!r}; use scenarios list')
    entry = entries[0]
    if entry['source'] == 'live':
        name = entry['recording_resource']
        if '/' in name or '\\' in name or name in ('.', '..'):
            raise InvalidRecordingError('invalid packaged recording path')
        data = files('ntp_sync_lab').joinpath('fixtures', 'recordings', name).read_text(encoding='utf-8')
        return parse_recording(data)
    metadata = dict(result_id=f'scenario:{scenario_id}', created_at_utc=utc_date(entry['defined_at_utc']))
    if entry['experiment'] == 'network_delay':
        return delay_to_contract(run_delay(make_delay_config(**entry['parameters'])), **metadata)
    if entry['experiment'] == 'clock_sync':
        return sync_to_contract(run_sync(make_sync_config(**entry['parameters'])), **metadata)
    raise InvalidRecordingError('unsupported packaged scenario experiment')
