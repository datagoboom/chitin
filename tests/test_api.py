"""Tests for API server."""

import pytest
from fastapi.testclient import TestClient

from chitin_agent.api.auth import APIAuth, get_auth
from chitin_agent.api.server import create_app
from chitin_agent.config import AgentConfig


@pytest.fixture
def api_client():
    """Create test API client."""
    config = AgentConfig()
    app = create_app(config)
    return TestClient(app)


@pytest.fixture
def auth_token():
    """Get a valid auth token."""
    auth = get_auth()
    return auth.get_token()


def test_api_requires_auth(api_client):
    """Test that API endpoints require authentication."""
    response = api_client.get("/api/sessions")
    assert response.status_code == 401  # FastAPI returns 401 for missing auth


def test_api_with_valid_token(api_client, auth_token):
    """Test API access with valid token."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = api_client.get("/api/sessions", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_with_invalid_token(api_client):
    """Test API access with invalid token."""
    headers = {"Authorization": "Bearer invalid_token"}
    response = api_client.get("/api/sessions", headers=headers)
    assert response.status_code == 401


def test_list_sessions_empty(api_client, auth_token):
    """Test listing sessions when none exist."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = api_client.get("/api/sessions", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_get_session_not_found(api_client, auth_token):
    """Test getting non-existent session."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = api_client.get("/api/sessions/nonexistent", headers=headers)
    assert response.status_code == 404


def test_list_tools(api_client, auth_token):
    """Test listing tools."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = api_client.get("/api/tools", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_auth_token_generation():
    """Test token generation."""
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        token_file = Path(tmpdir) / "test_token"
        auth = APIAuth(token_file=token_file)

        # Generate token
        token1 = auth.generate_token()
        assert len(token1) > 0

        # Token should be saved
        assert token_file.exists()
        assert token_file.read_text().strip() == token1

        # New instance should load token
        auth2 = APIAuth(token_file=token_file)
        token2 = auth2.get_token()
        assert token2 == token1


def test_auth_token_verification():
    """Test token verification."""
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        token_file = Path(tmpdir) / "test_token"
        auth = APIAuth(token_file=token_file)

        token = auth.generate_token()
        assert auth.verify_token(token) is True
        assert auth.verify_token("wrong_token") is False
