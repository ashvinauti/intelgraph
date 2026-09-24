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


class TestTaskEndpoints:
    def test_list_tasks_empty(self, auth_client):
        resp = auth_client.get("/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_enqueue_collect_entity(self, auth_client):
        resp = auth_client.post("/tasks/collect_entity")
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["task_type"] == "collect_entity"
        assert data["status"] == "pending"

    def test_enqueue_verify_entity(self, auth_client):
        resp = auth_client.post("/tasks/verify_entity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_type"] == "verify_entity"

    def test_enqueue_generate_report(self, auth_client):
        resp = auth_client.post("/tasks/generate_report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_type"] == "generate_report"

    def test_get_task(self, auth_client):
        create = auth_client.post("/tasks/collect_entity").json()
        tid = create["task_id"]
        resp = auth_client.get(f"/tasks/{tid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tid
        assert data["type"] == "collect_entity"

    def test_get_task_not_found(self, auth_client):
        resp = auth_client.get("/tasks/nonexistent")
        assert resp.status_code == 404

    def test_list_tasks_after_enqueue(self, auth_client):
        auth_client.post("/tasks/collect_entity")
        auth_client.post("/tasks/verify_entity")
        resp = auth_client.get("/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
