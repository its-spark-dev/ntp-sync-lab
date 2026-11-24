"""Optional same-origin static release; build React separately before startup."""
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from ntp_sync_lab.api.app import create_app


def create_web_app():
    directory = Path(os.environ.get('NTP_LAB_WEB_DIST', 'frontend/dist')).resolve()
    if not (directory / 'index.html').is_file():
        raise RuntimeError('Build frontend first (npm run build in frontend), or set NTP_LAB_WEB_DIST')
    app = create_app()
    app.mount('/', StaticFiles(directory=directory, html=True), name='frontend')
    return app
