"""HTTP acceptance: ASGI in-process, fake services, no public networking."""
import asyncio
import json
import subprocess
import sys
import threading

import pytest
httpx = pytest.importorskip("httpx", reason="install .[web-test] for API tests")

pytest.importorskip('fastapi', reason='install .[web,web-test] for optional API checks')
from ntp_sync_lab.api.app import LiveService, create_app
from ntp_sync_lab.core.polling import PollGuard
from ntp_sync_lab.errors import (
    DnsFailureError, InvalidRecordingError, InvalidTimingError, LiveStateUnavailableError,
    LocalClockDiscontinuityError, MalformedPacketError, NetworkError, NtpTimeoutError,
    OriginMismatchError, PeerMismatchError, RateLimitedError, ServerControlError,
    ServerUnsynchronizedError, UnsupportedResponseError,
)
from ntp_sync_lab.experiments.replay import validate_recording
from ntp_sync_lab.experiments.scenarios import scenario_recording
from tests.helpers import Delivery, FakeClock, FakeTransport, StaticResolver


def request(app, method, path, **kwargs):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                     base_url='http://127.0.0.1:8000') as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(execute())


@pytest.fixture
def live(tmp_path):
    clock = FakeClock()
    transport = FakeTransport(clock, [[Delivery()], [Delivery()]])
    service = LiveService(clock=clock, resolver=StaticResolver(), transport=transport,
                          guard=PollGuard(clock, tmp_path))
    return service, transport


def normalized(document):
    if isinstance(document, dict):
        return {k: normalized(v) for k, v in document.items() if k not in ('result_id', 'created_at_utc')}
    if isinstance(document, list):
        return [normalized(v) for v in document]
    return document


@pytest.mark.parametrize('path,body,args', [
    ('delay', {}, ['delay']),
    ('delay', {'preset': 'asymmetric-forward'}, ['delay', '--preset', 'asymmetric-forward']),
    ('delay', {'true_offset_ms': '-60000', 'forward_ms': '0.000001', 'reverse_ms': '0'},
     ['delay', '--true-offset-ms', '-60000', '--forward-ms', '0.000001', '--reverse-ms', '0']),
    ('delay', {'round_trip_ms': '0.000001', 'sweep_points': 3},
     ['delay', '--round-trip-ms', '0.000001', '--sweep-points', '3']),
    ('delay', {'preset': 'symmetric-low', 'increments_ms': ['0', '60']},
     ['delay', '--preset', 'symmetric-low', '--increments-ms', '0', '60']),
    ('delay', {'reference_unix_ns': str(2**100)}, ['delay', '--reference-unix-ns', str(2**100)]),
    ('sync', {}, ['sync']),
    ('sync', {'client_offset_ms': '-120', 'forward_ms': '60', 'reverse_ms': '20'},
     ['sync', '--client-offset-ms', '-120', '--forward-ms', '60', '--reverse-ms', '20']),
    ('sync', {'client_offset_ms': '0', 'forward_ms': '0', 'reverse_ms': '0.000001'},
     ['sync', '--client-offset-ms', '0', '--forward-ms', '0', '--reverse-ms', '0.000001']),
])
def test_api_cli_parity(path, body, args, tmp_path):
    response = request(create_app(), 'POST', '/api/v1/experiments/'+path, json=body)
    assert response.status_code == 200, response.text
    cli = subprocess.run([sys.executable, '-I', '-m', 'ntp_sync_lab', *args, '--format', 'json'],
                         cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert cli.returncode == 0, cli.stderr
    assert normalized(response.json()) == normalized(json.loads(cli.stdout))
    validate_recording(response.json())


@pytest.mark.parametrize('path,body', [
    ('delay', {'preset':'nope'}), ('delay', {'forward_ms':20}),
    ('delay', {'forward_ms':'NaN'}), ('delay', {'forward_ms':'-1'}),
    ('delay', {'forward_ms':'2001'}), ('delay', {'true_offset_ms':'60001'}),
    ('delay', {'processing_ms':'501'}), ('delay', {'forward_ms':'0.0000001'}),
    ('delay', {'preset':'symmetric-low', 'forward_ms':'20'}),
    ('delay', {'round_trip_ms':'80', 'forward_ms':'20'}),
    ('delay', {'sweep_points':3}), ('delay', {'round_trip_ms':'80','sweep_points':True}),
    ('delay', {'round_trip_ms':'2001'}),
    ('delay', {'increments_ms':['1','0']}), ('delay', {'increments_ms':['0']*201}),
    ('delay', {'reference_unix_ns':2**60}), ('delay', {'unknown':'x'}),
    ('sync', {'client_offset_ms':True}), ('sync', {'client_offset_ms':'Infinity'}),
    ('sync', {'mode':'slew'}), ('sync', {'client_offset_ms':'-60001'}),
])
def test_invalid_experiments(path, body):
    r = request(create_app(), 'POST', '/api/v1/experiments/'+path, json=body)
    assert r.status_code == 422 and r.json()['error']['code']=='INVALID_INPUT'


@pytest.mark.parametrize('body', [{'server':'example.com'}, {'server_id':'unknown'},
                                  {'timeout_seconds':True}, {'timeout_seconds':'3'},
                                  {'timeout_seconds':0.01}, {'timeout_seconds':11}, {'count':2}])
def test_measurement_input_never_sends(body, live):
    service, transport = live
    r = request(create_app(live_service=service), 'POST', '/api/v1/measurements', json=body)
    assert r.status_code in (404,422) and not transport.sessions


def test_live_parity_cooldown_and_config(live):
    from ntp_sync_lab.serialization import measurement_to_contract
    service, transport = live
    original = service.measure
    captured = []
    def capture(config):
        result = original(config)
        captured.append(measurement_to_contract(result))
        return result
    service.measure = capture
    app = create_app(live_service=service)
    initial = request(app,'GET','/api/v1/config').json()
    assert initial['servers'][0]['cooldown']['state']=='unknown'
    r = request(app,'POST','/api/v1/measurements',json={})
    assert r.status_code==200, r.text
    result=r.json()
    assert result == captured[0]
    validate_recording(result)
    assert result['source']=='live' and result['data']['true_offset_ns'] is None
    assert result['data']['estimation_error_ns'] is None
    assert len(transport.sessions)==1 and len(transport.sessions[0].sent)==1
    assert transport.sessions[0].closed
    assert request(app,'GET','/api/v1/config').json()['servers'][0]['cooldown']['retry_after_ns']=='63955000000'
    r=request(app,'POST','/api/v1/measurements',json={})
    assert r.status_code==429 and r.headers['retry-after']=='64'
    assert sum(len(s.sent) for s in transport.sessions)==1


@pytest.mark.parametrize('error,status', [
    (DnsFailureError('fixture'),503),(NetworkError('fixture'),503),
    (LiveStateUnavailableError('fixture'),503),(NtpTimeoutError('fixture'),504),
    (RateLimitedError('fixture',retry_after_ns=1),429),(ServerControlError(b'RATE'),502),
    (MalformedPacketError('fixture'),502),(UnsupportedResponseError('fixture'),502),
    (ServerUnsynchronizedError('fixture'),502),(InvalidTimingError('fixture'),502),
    (LocalClockDiscontinuityError('fixture'),502),(OriginMismatchError('fixture'),502),
    (PeerMismatchError('fixture'),502),(InvalidRecordingError('fixture'),503),
])
def test_error_mapping(error,status):
    class Service:
        def measure(self, config):
            raise error
    app=create_app(live_service=Service())
    for _ in range(2):  # failure releases the slot
        r=request(app,'POST','/api/v1/measurements',json={})
        assert r.status_code==status and r.json()['error']['code']==error.code


@pytest.mark.parametrize('body', [{}, {'scenario_id':'symmetric-low','recording_id':'captured-public-ntp'},
                                 {'file':'/etc/passwd'}, {'scenario_id':'../../LICENSE'},
                                 {'recording_id':'symmetric-low'}])
def test_replay_rejects_invalid_selection(body):
    r=request(create_app(),'POST','/api/v1/replays',json=body)
    assert r.status_code in (404,422)


@pytest.mark.parametrize('selection', [{'recording_id':'captured-public-ntp'},
                                      {'scenario_id':'captured-public-ntp'},
                                      {'scenario_id':'sync-asymmetric-forward'}])
def test_replay_preserves_source(selection):
    r=request(create_app(),'POST','/api/v1/replays',json=selection)
    assert r.status_code==200
    doc=r.json()
    assert doc['source']=='replay'
    assert doc['recording']==scenario_recording(next(iter(selection.values())))
    validate_recording(doc)



def test_no_network_for_gets_or_offline_routes(monkeypatch):
    async def execute():
        def forbidden(*args, **kwargs):
            raise AssertionError('unexpected network')
        import socket
        monkeypatch.setattr(socket,'getaddrinfo',forbidden)
        monkeypatch.setattr(socket,'socket',forbidden)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),base_url='http://localhost') as c:
            for path in ('health','config','scenarios','recordings'):
                assert (await c.get('/api/v1/'+path)).status_code==200
            for path,body in [('experiments/delay',{}),('experiments/sync',{}),
                              ('replays',{'recording_id':'captured-public-ntp'})]:
                assert (await c.post('/api/v1/'+path,json=body)).status_code==200
    asyncio.run(execute())


def test_busy_request_is_rejected_without_queue_and_health_stays_responsive(live):
    service,transport=live
    entered,release=threading.Event(),threading.Event()
    original=service.measure
    def slow(config):
        entered.set()
        assert release.wait(3)
        return original(config)
    service.measure=slow
    async def execute():
        app=create_app(live_service=service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as c:
            first=asyncio.create_task(c.post('/api/v1/measurements',json={}))
            try:
                assert await asyncio.to_thread(entered.wait,2)
                r=await c.post('/api/v1/measurements',json={})
                assert r.status_code==429 and r.headers['retry-after']=='1'
                assert (await c.get('/api/v1/health')).status_code==200
                assert (await c.get('/api/v1/config')).json()['live_busy'] is True
            finally:
                release.set()
            assert (await first).status_code==200
    asyncio.run(execute())
    assert sum(len(s.sent) for s in transport.sessions)==1


def test_cancel_scope_does_not_release_slot_before_worker_finishes(live):
    import anyio
    service,transport=live
    entered,release,finished=threading.Event(),threading.Event(),threading.Event()
    original=service.measure
    def slow(config):
        entered.set()
        assert release.wait(3)
        result=original(config)
        finished.set()
        return result
    service.measure=slow
    async def execute():
        app=create_app(live_service=service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as c:
            scope=anyio.CancelScope()
            async def operation():
                with scope:
                    await c.post('/api/v1/measurements',json={})
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(operation)
                try:
                    assert await anyio.to_thread.run_sync(entered.wait,2)
                    scope.cancel()
                    assert (await c.post('/api/v1/measurements',json={})).status_code==429
                finally:
                    release.set()
            assert finished.is_set()
            assert (await c.post('/api/v1/measurements',json={})).status_code==429 # persisted cooldown
    anyio.run(execute)
    assert sum(len(s.sent) for s in transport.sessions)==1


def test_origin_host_and_safe_internal_error():
    app=create_app()
    assert request(app,'POST','/api/v1/experiments/delay',json={},headers={'Origin':'https://evil.example'}).status_code==403
    assert request(app,'POST','/api/v1/experiments/delay',json={},headers={'Origin':'http://127.0.0.1:8000'}).status_code==200
    assert request(app,'POST','/api/v1/experiments/delay',json={},headers={'Origin':'http://['}).status_code==403
    assert request(app,'GET','/api/v1/health',headers={'Host':'evil.example'}).status_code==400
    assert request(app,'GET','/api/v1/missing').json()['error']['code']=='NOT_FOUND'
    class Broken:
        def measure(self, config):
            raise RuntimeError('secret internal path')
    r=request(create_app(live_service=Broken()),'POST','/api/v1/measurements',json={})
    assert r.status_code==500 and 'secret' not in r.text


def test_openapi_exposes_string_precision_and_null_truth():
    app=create_app()
    schema=request(app,'GET','/openapi.json').json()
    models=schema['components']['schemas']
    for field in models['Timestamps']['properties'].values():
        assert field['type']=='string'
    for field in ('true_offset_ns','estimation_error_ns'):
        assert {s['type'] for s in models['ExchangeData']['properties'][field]['anyOf']}=={'string','null'}
    assert models['SyncData']['properties']['applied_correction_ns']['type']=='string'
    assert len([p for p in schema['paths'] if p.startswith('/api/v1/')])==8


@pytest.mark.parametrize('control', [False, True])
def test_real_service_persists_timeout_or_control(tmp_path, control):
    def control_packet(request):
        return bytes.fromhex('240006ec')+bytes(8)+b'RATE'+bytes(8)+request[40:48]+bytes(16)
    clock=FakeClock()
    transport=FakeTransport(clock, [[Delivery(data=control_packet)] if control else [NtpTimeoutError('fixture')]])
    guard=PollGuard(clock,tmp_path)
    service=LiveService(clock=clock, resolver=StaticResolver(), transport=transport, guard=guard)
    app=create_app(live_service=service)
    r=request(app,'POST','/api/v1/measurements',json={})
    assert r.status_code==(502 if control else 504)
    status=request(app,'GET','/api/v1/config').json()['servers'][0]['cooldown']
    if control:
        assert status['state']=='blocked' and status['code']=='SERVER_CONTROL'
    else:
        assert status['state']=='cooldown' and int(status['retry_after_ns'])>120_000_000_000
    assert transport.sessions[0].closed


def test_api_actual_local_udp(tmp_path):
    import socket
    import time
    from ntp_sync_lab.core.clock import SystemClock
    from ntp_sync_lab.core.packet import NtpPeer
    from ntp_sync_lab.core.timestamps import encode_timestamp
    from ntp_sync_lab.core.transport import ResolvedTarget, UdpTransport
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as server:
        server.bind(('127.0.0.1',0))
        server.settimeout(3)
        port=server.getsockname()[1]
        seen,errors=[],[]
        def respond():
            try:
                packet,peer=server.recvfrom(65535)
                received=time.time_ns()
                seen.append(packet)
                server.sendto(bytes.fromhex('240106ec')+bytes(8)+b'TEST'+bytes(8)+packet[40:48]
                              +encode_timestamp(received).to_bytes()+encode_timestamp(time.time_ns()).to_bytes(),peer)
            except BaseException as error:
                errors.append(error)
        worker=threading.Thread(target=respond)
        worker.start()
        clock=SystemClock()
        service=LiveService(clock=clock, transport=UdpTransport(), guard=PollGuard(clock,tmp_path),
                            resolver=StaticResolver(ResolvedTarget(NtpPeer('127.0.0.1',port),socket.AF_INET)))
        try:
            r=request(create_app(live_service=service,servers={'fixture':'127.0.0.1'}),
                      'POST','/api/v1/measurements',json={'server_id':'fixture'})
        finally:
            worker.join(4)
        assert not worker.is_alive() and not errors and len(seen)==1
        assert r.status_code==200, r.text
        assert r.json()['provenance']['peer']['port']==port
        assert r.json()['data']['true_offset_ns'] is None
        validate_recording(r.json())


def test_import_and_offline_cli_do_not_require_web(tmp_path):
    script='''
import sys
class BlockWeb:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in ('fastapi','pydantic','starlette','uvicorn','anyio','httpx'):
            raise AssertionError('CLI imported optional web dependency: '+fullname)
sys.meta_path.insert(0,BlockWeb())
from ntp_sync_lab.cli.main import main
raise SystemExit(main(['sync','--format','json']))
'''
    result=subprocess.run([sys.executable,'-I','-c',script],cwd=tmp_path,capture_output=True,text=True,timeout=10)
    assert result.returncode==0, result.stderr
    assert json.loads(result.stdout)['source']=='simulation'
