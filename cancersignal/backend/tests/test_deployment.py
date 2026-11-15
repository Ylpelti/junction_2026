import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.core.config import Settings
from app.main import create_app


def test_database_url_preserves_tls_and_encoded_password(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgres://demo:p%40ss@db.example/demo?sslmode=verify-full&sslrootcert=/certs/ca.pem')
    settings = Settings(_env_file=None)
    assert settings.database_url.drivername == 'postgresql+psycopg'
    assert settings.database_url.password == 'p@ss'
    assert settings.database_url.query['sslmode'] == 'verify-full'
    assert settings.database_url.query['sslrootcert'] == '/certs/ca.pem'
    assert 'p%40ss' not in repr(settings)


def test_database_url_rejects_non_postgres(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///demo.db')
    with pytest.raises(ValueError, match='PostgreSQL URL'):
        Settings(_env_file=None)


def test_ready_tracks_migration_and_recovers(database_engine, monkeypatch):
    monkeypatch.setattr('app.db.session.get_engine', lambda: database_engine)
    with TestClient(create_app()) as client:
        assert client.get('/ready').json() == {'status': 'ready'}
        with database_engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='review_0001'"))
        try:
            assert client.get('/ready').status_code == 503
            assert client.get('/health').status_code == 200
        finally:
            with database_engine.begin() as connection:
                connection.execute(text("UPDATE alembic_version SET version_num='workflow_0001'"))
        assert client.get('/ready').status_code == 200


def test_ready_hides_connection_errors(monkeypatch):
    def unavailable():
        raise RuntimeError('sensitive connection information')
    monkeypatch.setattr('app.db.session.get_engine', unavailable)
    with TestClient(create_app()) as client:
        response = client.get('/ready')
        assert response.status_code == 503
        assert response.json() == {'status': 'unavailable'}
        assert client.get('/health').status_code == 200


def test_invalid_database_url_does_not_disclose_secret(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://demo:private-token@host:bad/demo')
    with pytest.raises(ValueError) as error:
        Settings(_env_file=None)
    assert 'private-token' not in str(error.value)


def test_pool_is_bounded(monkeypatch):
    from app.db import session
    monkeypatch.setenv('DATABASE_URL', 'postgresql://demo:demo@localhost/demo')
    monkeypatch.setenv('DB_POOL_SIZE', '2')
    monkeypatch.setenv('DB_MAX_OVERFLOW', '1')
    monkeypatch.setattr(session, 'get_settings', lambda: Settings(_env_file=None))
    session.get_engine.cache_clear()
    engine = session.get_engine()
    try:
        assert engine.pool.size() == 2
        assert engine.pool._max_overflow == 1
        assert engine.hide_parameters
    finally:
        engine.dispose()
        session.get_engine.cache_clear()
