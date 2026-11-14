"""Run from frontend with the backend virtualenv Python.
Creates/migrates/seeds/drops ONLY a uniquely named disposable PostgreSQL DB.
Uses the existing four-patient fixture and deterministic pipeline, no paid calls.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
sys.path.insert(0, str(BACKEND))
import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.demo import seed_demo
from app.db.seed_rules import seed_rules


def main():
    name = f'cancersignal_browser_{uuid4().hex[:12]}'
    settings = get_settings()
    admin = create_engine(settings.database_url, isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(settings.database_url.set(database=name))
    api = None
    try:
        config = Config(str(BACKEND / 'alembic.ini'))
        config.set_main_option('script_location', str(BACKEND / 'alembic'))
        with engine.begin() as conn:
            config.attributes['connection'] = conn
            command.upgrade(config, 'head')
        with Session(engine) as session:
            seed_demo(session)
            seed_rules(session)
            session.commit()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, POSTGRES_DB=name, PYTHONPATH=str(BACKEND),
                   CANCERSIGNAL_EXTRACTION='off', CANCERSIGNAL_EXTRACTION_ALLOW_LIVE='false',
                   CANCERSIGNAL_EXPLANATION='deterministic', CANCERSIGNAL_EXPLANATION_ALLOW_LIVE='false',
                   CANCERSIGNAL_RETRIEVAL='auto', CORS_ORIGINS='["http://127.0.0.1:3107"]',
                   E2E_REAL='1', E2E_API_URL=f'http://127.0.0.1:{port}')
        api = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                               cwd=BACKEND, env=env, stdout=subprocess.DEVNULL)
        with httpx.Client() as client:
            for _ in range(100):
                try:
                    if client.get(f'http://127.0.0.1:{port}/health').is_success:
                        break
                except httpx.ConnectError:
                    pass
                if api.poll() is not None:
                    raise RuntimeError('FastAPI exited before readiness')
                time.sleep(.1)
            else:
                raise RuntimeError('FastAPI readiness timeout')
        subprocess.run(['npm', 'run', 'test:e2e'], cwd=ROOT / 'frontend', env=env, check=True)
    finally:
        if api:
            api.terminate()
            api.wait(timeout=10)
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == '__main__':
    main()
