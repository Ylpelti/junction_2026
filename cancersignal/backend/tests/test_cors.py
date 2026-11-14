import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import WebSettings
from app.main import create_app


def client(origins=None):
    settings = WebSettings(_env_file=None, cors_origins=origins if origins is not None else
                           ["http://localhost:3000", "http://127.0.0.1:3000"])
    return TestClient(create_app(settings))


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
def test_frontend_gets_cors_headers_and_json_post_preflight(origin):
    with client() as browser:
        response = browser.get("/health", headers={"Origin": origin})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        preflight = browser.options("/api/v1/patients/example/analyses", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin
        assert "POST" in preflight.headers["access-control-allow-methods"]
        assert "access-control-allow-credentials" not in preflight.headers
        assert "Origin" in preflight.headers["vary"]


def test_unlisted_origins_and_methods_are_rejected():
    with client() as browser:
        for origin, method in [("https://unlisted.example", "POST"), ("http://localhost:3000", "DELETE")]:
            response = browser.options("/api/v1/patients", headers={
                "Origin": origin, "Access-Control-Request-Method": method})
            assert response.status_code == 400
        response = browser.get("/health", headers={"Origin": "http://localhost:3001"})
        assert "access-control-allow-origin" not in response.headers


def test_custom_origin_and_errors_keep_cors_headers():
    with client(["https://demo.example"]) as browser:
        response = browser.get("/api/v1/patients/not-a-uuid", headers={"Origin": "https://demo.example"})
        assert response.status_code == 422
        assert response.headers["access-control-allow-origin"] == "https://demo.example"
        assert "access-control-allow-origin" not in browser.get("/health").headers


def test_origin_list_loads_from_environment_without_database_configuration(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3001/","http://localhost:3001"]')
    settings = WebSettings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3001"]
    with TestClient(create_app(settings)) as browser:
        assert browser.get("/health", headers={"Origin": "http://localhost:3001"}).headers[
            "access-control-allow-origin"] == "http://localhost:3001"


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "https://demo.example/path", "file:///tmp", "https://user:password@demo.example", "http://localhost:wrong", "https://demo.example?key=value"])
def test_malformed_origins_are_rejected(origin):
    with pytest.raises(ValidationError):
        WebSettings(_env_file=None, cors_origins=[origin])
