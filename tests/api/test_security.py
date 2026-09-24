from datetime import UTC

import pytest
from fastapi.testclient import TestClient

from intelgraph.api.auth import (
    TOKEN_EXPIRY_HOURS,
    _hash_password,
    _verify_password,
    login_user,
    register_user,
    validate_token,
)
from intelgraph.api.main import create_app
from intelgraph.core.enterprise.config_validator import ConfigValidationError


@pytest.fixture
def client():
    app = create_app({"storage": {"path": ":memory:"}})
    with TestClient(app) as c:
        yield c


class TestRBACEnforcement:
    def _register_and_get_header(self, client, role: str = "user"):
        resp = client.post(
            "/auth/register",
            json={
                "username": f"user_{role}",
                "password": "pass",
                "role": role,
            },
        )
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_unauthenticated_create_entity_returns_401(self, client):
        resp = client.post(
            "/entities",
            json={
                "entity_type": "person",
                "attributes": {"name": "Alice"},
            },
        )
        assert resp.status_code == 401

    def test_unauthenticated_update_entity_returns_401(self, client):
        resp = client.put("/entities/some-id", json={"attributes": {"name": "x"}})
        assert resp.status_code == 401

    def test_unauthenticated_delete_entity_returns_401(self, client):
        resp = client.delete("/entities/some-id")
        assert resp.status_code == 401

    def test_unauthenticated_create_relationship_returns_401(self, client):
        resp = client.post(
            "/relationships",
            json={
                "type": "RELATED_TO",
                "source_id": "a",
                "target_id": "b",
            },
        )
        assert resp.status_code == 401

    def test_unauthenticated_delete_relationship_returns_401(self, client):
        resp = client.delete("/relationships/some-id")
        assert resp.status_code == 401

    def test_unauthenticated_task_enqueue_returns_401(self, client):
        resp = client.post("/tasks/collect_entity")
        assert resp.status_code == 401

    def test_user_cannot_create_entity_returns_403(self, client):
        headers = self._register_and_get_header(client, "user")
        resp = client.post(
            "/entities",
            json={
                "entity_type": "person",
                "attributes": {"name": "Alice"},
            },
            headers=headers,
        )
        assert resp.status_code == 403

    def test_user_cannot_delete_entity_returns_403(self, client):
        headers = self._register_and_get_header(client, "user")
        resp = client.delete("/entities/some-id", headers=headers)
        assert resp.status_code == 403

    def test_analyst_can_create_entity(self, client):
        headers = self._register_and_get_header(client, "analyst")
        resp = client.post(
            "/entities",
            json={
                "entity_type": "person",
                "attributes": {"name": "Alice"},
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_analyst_cannot_delete_entity_returns_403(self, client):
        headers = self._register_and_get_header(client, "analyst")
        eid = client.post(
            "/entities",
            json={
                "entity_type": "person",
                "attributes": {"name": "X"},
            },
            headers=headers,
        ).json()["id"]
        resp = client.delete(f"/entities/{eid}", headers=headers)
        assert resp.status_code == 403

    def test_admin_can_delete_entity(self, client):
        headers = self._register_and_get_header(client, "admin")
        eid = client.post(
            "/entities",
            json={
                "entity_type": "person",
                "attributes": {"name": "Y"},
            },
            headers=headers,
        ).json()["id"]
        resp = client.delete(f"/entities/{eid}", headers=headers)
        assert resp.status_code == 200

    def test_read_endpoints_accessible_without_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        resp = client.get("/entities/nonexistent")
        assert resp.status_code == 404


class TestAuthHardening:
    def test_password_hashing_uses_salt(self):
        h1 = _hash_password("samepassword")
        h2 = _hash_password("samepassword")
        assert h1 != h2

    def test_password_verification(self):
        h = _hash_password("mypassword")
        assert _verify_password("mypassword", h) is True
        assert _verify_password("wrong", h) is False

    def test_token_is_jwt_format(self):
        result = register_user("jwt_test", "pass", "admin")
        token = result["access_token"]
        assert isinstance(token, str)
        parts = token.split(".")
        assert len(parts) == 3

    def test_validate_valid_token(self):
        uid = "test_validate"
        import hashlib

        uid_hash = hashlib.sha256(uid.encode()).hexdigest()[:16]
        token = register_user(uid, "pass")["access_token"]
        result = validate_token(token)
        assert result == uid_hash

    def test_validate_invalid_token(self):
        assert validate_token("invalid.token.here") is None

    def test_validate_expired_token(self):
        import os

        import jwt

        secret = os.environ.get("INTELGRAPH_SECRET_KEY", "test_secret")
        expired = jwt.encode(
            {"sub": "test", "iat": 0, "exp": 1},
            secret,
            algorithm="HS256",
        )
        assert validate_token(expired) is None

    def test_login_returns_valid_token(self):
        register_user("logintest", "mypass", "user")
        result = login_user("logintest", "mypass")
        assert result is not None
        assert validate_token(result["access_token"]) is not None

    def test_login_wrong_password(self):
        register_user("logintest2", "correctpass", "user")
        assert login_user("logintest2", "wrongpass") is None

    def test_token_response_includes_expiry(self):
        result = register_user("expiry_test", "pass")
        assert "expires_in" in result
        assert result["expires_in"] == TOKEN_EXPIRY_HOURS * 3600


class TestConfigValidation:
    def test_app_creation_fails_on_invalid_config(self):
        with pytest.raises((Exception, ConfigValidationError)):
            create_app({"storage": {"backend": 123}})

    def test_valid_config_creates_app(self):
        app = create_app({"storage": {"path": ":memory:"}, "logging": {"level": "DEBUG"}})
        assert app is not None


class TestEvidencePersistence:
    def test_store_and_retrieve_evidence(self, client):
        from datetime import datetime

        from intelgraph.api.main import _container
        from intelgraph.core.evidence.evidence import Evidence

        ev = Evidence(
            id="ev-1",
            source="https://example.com",
            content="test content",
            collected_at=datetime.now(UTC),
            source_tier=1,
            trust_score=80,
            reliability_score=70,
        )
        _container.backend.store_collection_evidence(ev, entity_id="entity-123")
        results = _container.backend.get_collection_evidence("entity-123")
        assert len(results) == 1
        assert results[0].id == "ev-1"

    def test_evidence_not_found_when_wrong_entity_id(self, client):
        from intelgraph.api.main import _container

        results = _container.backend.get_collection_evidence("nonexistent-entity")
        assert results == []


class TestRateLimitCategories:
    def test_rate_limit_category_header_present(self, client):
        resp = client.get("/health")
        assert "X-RateLimit-Category" in resp.headers
        assert resp.headers["X-RateLimit-Category"] == "health"

    def test_auth_category(self, client):
        resp = client.post("/auth/login", json={"username": "x", "password": "y"})
        assert resp.headers["X-RateLimit-Category"] == "auth"

    def test_write_category(self, client):
        resp = client.post("/tasks/collect_entity")
        assert resp.status_code == 401
        assert resp.headers.get("X-RateLimit-Category") == "write"
