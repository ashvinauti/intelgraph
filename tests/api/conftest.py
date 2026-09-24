from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intelgraph.api.main import create_app


@pytest.fixture(scope="module")
def _app_config():
    return {"storage": {"path": ":memory:"}}


@pytest.fixture
def client(_app_config):
    app = create_app(_app_config)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    resp = client.post(
        "/auth/register",
        json={
            "username": "admin",
            "password": "admin123",
            "role": "admin",
        },
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
