"""Tests des endpoints de l'API LGC (squelette S1.1)."""

from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)


def test_root_endpoint():
    """La racine identifie l'API LGC."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "LGC API", "status": "ok"}


def test_health_endpoint():
    """Le health check répond healthy."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_cors_allows_frontend_origin():
    """Le CORS autorise l'origine du front local."""
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"




