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


class TestAuditOnWrite:
    def test_create_entity_audit(self, auth_client):
        from intelgraph.api.main import _container

        resp = auth_client.post(
            "/entities",
            json={
                "entity_type": "person",
                "attributes": {"name": "audited"},
            },
        )
        assert resp.status_code == 200
        eid = resp.json()["id"]
        audit = _container.backend.query_audit(entity_id=eid, limit=10)
        assert len(audit) >= 1
        assert audit[0]["operation"] in ("CREATE", "UPDATE")

    def test_create_relationship_audit(self, auth_client):
        from intelgraph.api.main import _container

        src = auth_client.post(
            "/entities",
            json={
                "entity_type": "person",
                "attributes": {"name": "src"},
            },
        ).json()["id"]
        tgt = auth_client.post(
            "/entities",
            json={
                "entity_type": "person",
                "attributes": {"name": "tgt"},
            },
        ).json()["id"]
        resp = auth_client.post(
            "/relationships",
            json={
                "type": "RELATED_TO",
                "source_id": src,
                "target_id": tgt,
            },
        )
        assert resp.status_code == 200
        rid = resp.json()["id"]
        audit = _container.backend.query_audit(entity_id=rid, limit=10)
        assert len(audit) >= 1
        assert audit[0]["operation"] == "CREATE"

    def test_task_enqueue_audit(self, auth_client):
        from intelgraph.api.main import _container

        resp = auth_client.post("/tasks/collect_entity")
        assert resp.status_code == 200
        tid = resp.json()["task_id"]
        audit = _container.backend.query_audit(entity_id=tid, limit=10)
        assert len(audit) >= 1
