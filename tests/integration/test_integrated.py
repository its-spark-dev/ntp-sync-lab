"""P3.4 parity and shared policy checks, without public networking."""
import json
import subprocess
import sys
from unittest.mock import patch
import pytest
pytest.importorskip('fastapi')
pytest.importorskip('httpx')
from tests.integration.test_api import request, normalized
from tests.helpers import FakeClock, FakeTransport, StaticResolver, Delivery
from ntp_sync_lab.api.app import create_app, LiveService
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.cli.main import main
from ntp_sync_lab.experiments.measurement import run_measurements
from ntp_sync_lab.experiments.replay import validate_recording

CASES=[]
for forward,reverse in [('20','20'),('80','80'),('60','20'),('20','60')]:
    body=dict(true_offset_ms='100',forward_ms=forward,reverse_ms=reverse,processing_ms='5')
    CASES.append(('delay',body,['delay','--true-offset-ms','100','--forward-ms',forward,'--reverse-ms',reverse,'--processing-ms','5']))
CASES += [
    ('delay',dict(round_trip_ms='80',sweep_points=3),['delay','--round-trip-ms','80','--sweep-points','3']),
    ('delay',dict(true_offset_ms='100',forward_ms='20',reverse_ms='20',processing_ms='5',increments_ms=['0','60']),['delay','--true-offset-ms','100','--forward-ms','20','--reverse-ms','20','--processing-ms','5','--increments-ms','0','60']),
]
for offset,forward,reverse in [('120','20','20'),('120','60','20'),('120','20','60'),('-120','20','20'),('0','60','20'),('0.000001','0.000001','0')]:
    body=dict(client_offset_ms=offset,forward_ms=forward,reverse_ms=reverse,processing_ms='5',mode='step')
    CASES.append(('sync',body,['sync','--client-offset-ms',offset,'--forward-ms',forward,'--reverse-ms',reverse,'--processing-ms','5']))

@pytest.mark.parametrize('endpoint,body,args',CASES)
def test_ui_payloads_api_cli_parity(endpoint,body,args,tmp_path):
    api=request(create_app(),'POST','/api/v1/experiments/'+endpoint,json=body)
    cli=subprocess.run([sys.executable,'-I','-m','ntp_sync_lab',*args,'--format','json'],cwd=tmp_path,capture_output=True,text=True,timeout=10)
    assert api.status_code==200 and cli.returncode==0
    assert normalized(api.json())==normalized(json.loads(cli.stdout))
    validate_recording(api.json())


def test_live_cli_and_api_share_cooldown_and_reset_after_time(tmp_path,capsys):
    clock=FakeClock();guard=PollGuard(clock,tmp_path)
    transport=FakeTransport(clock,[[Delivery()]]*4);resolver=StaticResolver()
    service=LiveService(clock=clock,guard=guard,transport=transport,resolver=resolver)
    app=create_app(live_service=service)
    api=request(app,'POST','/api/v1/measurements',json={})
    assert api.status_code==200
    def cli_run():
        def injected(config,**kwargs):
            return run_measurements(config,clock=clock,guard=guard,transport=transport,resolver=resolver,**kwargs)
        with patch('ntp_sync_lab.experiments.measurement.run_measurements',injected):
            code=main(['measure','--format','json'])
        output=capsys.readouterr()
        return code,json.loads(output.out)
    code,blocked=cli_run()
    assert code==3 and blocked['attempts'][0]['error']['code']=='RATE_LIMITED'
    assert sum(len(s.sent) for s in transport.sessions)==1
    clock.advance(64_000_000_000)
    code,cli=cli_run()
    assert code==0
    # Exact metrics/timestamps from equivalent clock-relative fixtures; capture epochs differ by elapsed time.
    for field in ['estimated_offset_ns','round_trip_delay_ns','server_processing_ns','true_offset_ns','estimation_error_ns']:
        assert cli['attempts'][0]['result']['data'][field]==api.json()['data'][field]
    retry=request(app,'POST','/api/v1/measurements',json={})
    assert retry.status_code==429 and sum(len(s.sent) for s in transport.sessions)==2


def test_archived_api_cli_replay_preserves_same_original(tmp_path):
    api=request(create_app(),'POST','/api/v1/replays',json={'recording_id':'captured-public-ntp'})
    cli=subprocess.run([sys.executable,'-I','-m','ntp_sync_lab','replay','--scenario','captured-public-ntp','--format','json'],cwd=tmp_path,capture_output=True,text=True,timeout=10)
    doc=json.loads(cli.stdout)
    assert api.status_code==200 and cli.returncode==0
    assert api.json()['recording']==doc['recording']
    assert api.json()['provenance']['original_source']==doc['provenance']['original_source']=='live'


def test_live_api_cli_full_result_parity_with_same_fixture_epoch(tmp_path,capsys):
    api_clock=FakeClock();api_transport=FakeTransport(api_clock)
    api=request(create_app(live_service=LiveService(clock=api_clock,transport=api_transport,
        resolver=StaticResolver(),guard=PollGuard(api_clock,tmp_path/'api'))),
        'POST','/api/v1/measurements',json={})
    cli_clock=FakeClock();cli_transport=FakeTransport(cli_clock)
    def injected(config,**kwargs):
        return run_measurements(config,clock=cli_clock,transport=cli_transport,resolver=StaticResolver(),
                                guard=PollGuard(cli_clock,tmp_path/'cli'),**kwargs)
    with patch('ntp_sync_lab.experiments.measurement.run_measurements',injected):
        assert main(['measure','--format','json'])==0
    cli=json.loads(capsys.readouterr().out)['attempts'][0]['result']
    assert api.status_code==200
    assert normalized(cli)==normalized(api.json())
    assert cli['data']['true_offset_ns'] is None and cli['data']['estimation_error_ns'] is None
    assert len(api_transport.sessions[0].sent)==len(cli_transport.sessions[0].sent)==1
