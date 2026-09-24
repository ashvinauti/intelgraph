import pytest
from fastapi.testclient import TestClient

from intelgraph.api.main import create_app


@pytest.fixture(scope="session")
def _admin_token():
    app = create_app({"storage": {"path": ":memory:"}})
    with TestClient(app) as c:
        resp = c.post(
            "/auth/register",
            json={
                "username": "admin",
                "password": "admin123",
                "role": "admin",
            },
        )
        assert resp.status_code == 200
        return resp.json()["access_token"]


@pytest.fixture
def client():
    app = create_app({"storage": {"path": ":memory:"}})
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client, _admin_token):
    client.headers["Authorization"] = f"Bearer {_admin_token}"
    return client


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_liveness_returns_alive(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"
        assert "metrics" in data

    def test_readiness_checks_storage(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ready", "unhealthy")
        assert "storage" in data


class TestAuth:
    def test_register(self, client):
        resp = client.post("/auth/register", json={"username": "alice", "password": "secret"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_success(self, client):
        client.post("/auth/register", json={"username": "bob", "password": "pass"})
        resp = client.post("/auth/login", json={"username": "bob", "password": "pass"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_failure(self, client):
        resp = client.post("/auth/login", json={"username": "nobody", "password": "wrong"})
        assert resp.status_code == 401


class TestEntities:
    def test_create_entity(self, auth_client):
        resp = auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "Alice"}}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["entity_type"] == "person"

    def test_get_entity_not_found(self, auth_client):
        resp = auth_client.get("/entities/nonexistent")
        assert resp.status_code == 404

    def test_get_entity(self, auth_client):
        create = auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "Bob"}}
        )
        eid = create.json()["id"]
        resp = auth_client.get(f"/entities/{eid}")
        assert resp.status_code == 200

    def test_update_entity(self, auth_client):
        create = auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "Carol"}}
        )
        eid = create.json()["id"]
        resp = auth_client.put(f"/entities/{eid}", json={"attributes": {"name": "Carol Updated"}})
        assert resp.status_code == 200

    def test_update_entity_not_found(self, auth_client):
        resp = auth_client.put("/entities/nonexistent", json={"attributes": {"name": "x"}})
        assert resp.status_code == 404

    def test_delete_entity(self, auth_client):
        create = auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "Dave"}}
        )
        eid = create.json()["id"]
        resp = auth_client.delete(f"/entities/{eid}")
        assert resp.status_code == 200

    def test_delete_entity_not_found(self, auth_client):
        resp = auth_client.delete("/entities/nonexistent")
        assert resp.status_code == 404


class TestRelationships:
    def test_create_relationship(self, auth_client):
        src = auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "A"}}
        ).json()["id"]
        tgt = auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "B"}}
        ).json()["id"]
        resp = auth_client.post(
            "/relationships",
            json={
                "type": "RELATED_TO",
                "source_id": src,
                "target_id": tgt,
                "confidence_score": 80,
                "trust_weight": 70,
            },
        )
        assert resp.status_code == 200
        assert "id" in resp.json()

    def test_get_relationship_not_found(self, auth_client):
        resp = auth_client.get("/relationships/nonexistent")
        assert resp.status_code == 404

    def test_delete_relationship(self, auth_client):
        src = auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "C"}}
        ).json()["id"]
        tgt = auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "D"}}
        ).json()["id"]
        rid = auth_client.post(
            "/relationships",
            json={
                "type": "RELATED_TO",
                "source_id": src,
                "target_id": tgt,
            },
        ).json()["id"]
        resp = auth_client.delete(f"/relationships/{rid}")
        assert resp.status_code == 200


class TestEvidence:
    def test_evidence_not_found(self, auth_client):
        resp = auth_client.get("/entities/nonexistent/evidence")
        assert resp.status_code == 404


class TestVerification:
    def test_verification_not_found(self, auth_client):
        resp = auth_client.get("/entities/nonexistent/verification")
        assert resp.status_code == 404


class TestSources:
    def test_list_sources(self, auth_client):
        resp = auth_client.get("/sources")
        assert resp.status_code == 200

    def test_get_source_not_found(self, auth_client):
        resp = auth_client.get("/sources/nonexistent")
        assert resp.status_code == 404


class TestQuery:
    def test_query_all(self, auth_client):
        auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "Alice"}}
        )
        resp = auth_client.get("/query")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestSearch:
    def test_search(self, auth_client):
        auth_client.post(
            "/entities", json={"entity_type": "person", "attributes": {"name": "Alice"}}
        )
        resp = auth_client.get("/search")
        assert resp.status_code == 200


class TestRateLimit:
    def test_rate_limit_headers(self, auth_client):
        for _ in range(5):
            resp = auth_client.get("/health")
            assert resp.status_code == 200
        assert "x-ratelimit-remaining" in resp.headers
