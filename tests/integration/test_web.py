"""Same-origin static release boundaries, without frontend build dependencies."""
import pytest
pytest.importorskip('fastapi')
pytest.importorskip('httpx')
from ntp_sync_lab.api.web import create_web_app
from tests.integration.test_api import request


def test_static_release_preserves_api_and_blocks_path_escape(tmp_path, monkeypatch):
    (tmp_path / 'index.html').write_text('<!doctype html><title>Local lab release</title>')
    monkeypatch.setenv('NTP_LAB_WEB_DIST', str(tmp_path))
    app = create_web_app()
    assert 'Local lab release' in request(app, 'GET', '/').text
    assert request(app, 'GET', '/api/v1/health').json()['status'] == 'ok'
    replay = request(app, 'POST', '/api/v1/replays', json={'recording_id': 'captured-public-ntp'},
                     headers={'Origin': 'http://127.0.0.1:8000'})
    assert replay.status_code == 200 and replay.json()['source'] == 'replay'
    assert request(app, 'GET', '/%2e%2e/LICENSE').status_code == 404
    assert request(app, 'POST', '/api/v1/replays', json={'recording_id': 'captured-public-ntp'},
                   headers={'Origin': 'https://unrelated.example'}).status_code == 403


def test_missing_build_has_actionable_startup_error(tmp_path, monkeypatch):
    monkeypatch.setenv('NTP_LAB_WEB_DIST', str(tmp_path))
    with pytest.raises(RuntimeError, match='Build frontend first'):
        create_web_app()
