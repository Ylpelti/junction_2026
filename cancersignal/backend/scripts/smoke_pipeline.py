"""Actual uvicorn + disposable PostgreSQL smoke. No external LLM calls.
Run from backend: .venv/bin/python scripts/smoke_pipeline.py [--hybrid]
--hybrid requires cached real E5 weights and asserts actual hybrid execution.
"""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.seed import seed, synthetic_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hybrid", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    name = f"cancersignal_smoke_{uuid4().hex[:12]}"
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(settings.database_url.set(database=name))
    try:
        config = Config("alembic.ini")
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with Session(engine) as session:
            seed(session)
            session.commit()
        for mode in (["lexical", "hybrid"] if args.hybrid else ["lexical"]):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, POSTGRES_DB=name, CANCERSIGNAL_RETRIEVAL=mode,
                       CANCERSIGNAL_EXTRACTION="off", CANCERSIGNAL_EXPLANATION="deterministic",
                       CANCERSIGNAL_EXTRACTION_ALLOW_LIVE="false", CANCERSIGNAL_EXPLANATION_ALLOW_LIVE="false")
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=120) as client:
                    for _ in range(100):
                        try:
                            if client.get("/health").is_success:
                                break
                        except httpx.ConnectError:
                            pass
                        if process.poll() is not None:
                            raise RuntimeError("uvicorn exited before readiness")
                        time.sleep(.1)
                    patient = str(synthetic_id("patient/0"))
                    response = client.post(f"/api/v1/patients/{patient}/analyses", json={"note_observation_id": str(synthetic_id("note/0/3"))})
                    response.raise_for_status()
                    result = response.json()
                    assert result["status"] == "completed", result["provenance"]["error_code"]
                    method = result["provenance"]["retrieval_method"]
                    assert f":{mode}" in method, method
                    assert result["clinical_explanation"]["language"] == "fi"
                    assert client.get(f"/api/v1/analyses/{result['id']}").json() == result
                    payload = {"analysis_id": result["id"], "submitted_by": "Synthetic HTTP smoke"}
                    first = client.post(f"/api/v1/patients/{patient}/review-requests", json=payload)
                    second = client.post(f"/api/v1/patients/{patient}/review-requests", json=payload)
                    assert (first.status_code, second.status_code) == (201, 200)
                    assert first.json()["id"] == second.json()["id"]
                    assert client.get(f"/api/v1/review-requests/{first.json()['id']}").json()["analysis"] == result
                    print(f"PASS actual HTTP + PostgreSQL: {method}; explanation saved; handoff idempotent")
            finally:
                process.terminate()
                process.wait(timeout=10)
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
