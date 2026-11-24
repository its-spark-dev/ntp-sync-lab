"""Rebuild deterministic simulation fixtures from the existing Python engine; no clock reads or networking."""
import json
from datetime import datetime, timezone
from pathlib import Path
from ntp_sync_lab.experiments.delay import make_delay_config, run_delay
from ntp_sync_lab.experiments.synchronization import make_sync_config, run_sync
from ntp_sync_lab.serialization import delay_to_contract, sync_to_contract
from ntp_sync_lab.api.app import delay_document
from unittest.mock import patch

created = datetime(2026,11,23,tzinfo=timezone.utc)
def meta(name):
    return dict(result_id=f'test:{name}', created_at_utc=created)
fixtures={}
for preset in ('symmetric-low','symmetric-high','asymmetric-forward','asymmetric-reverse'):
    fixtures[preset]=delay_to_contract(run_delay(make_delay_config(preset=preset)),**meta(preset))
from ntp_sync_lab.api.schemas import DelayInput
with patch('ntp_sync_lab.api.app.metadata',return_value=meta('series')):
    fixtures['fixed']=delay_document(DelayInput(round_trip_ms='80',sweep_points=3))
    fixtures['equal']=delay_document(DelayInput(**dict(true_offset_ms='100',forward_ms='20',reverse_ms='20',processing_ms='5',increments_ms=['0','60'])))
for name,params in {
    'sync-symmetric':{},'sync-forward':{'forward_ms':'60'},'sync-reverse':{'reverse_ms':'60'},
    'sync-behind':{'client_offset_ms':'-120'},'sync-aligned':{'client_offset_ms':'0','forward_ms':'60'},
    'sync-half':{'client_offset_ms':'0.000001','forward_ms':'0.000001','reverse_ms':'0'},
}.items():
    fixtures[name]=sync_to_contract(run_sync(make_sync_config(**params)),**meta(name))
path=Path(__file__).resolve().parents[1]/'src/__fixtures__/simulations.json'
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(fixtures,indent=2)+'\n')
