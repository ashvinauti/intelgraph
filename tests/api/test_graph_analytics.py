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
def seeded_client(client, _admin_token):
    client.headers["Authorization"] = f"Bearer {_admin_token}"
    alice = client.post(
        "/entities", json={"entity_type": "person", "attributes": {"name": "Alice"}}
    ).json()["id"]
    bob = client.post(
        "/entities", json={"entity_type": "person", "attributes": {"name": "Bob"}}
    ).json()["id"]
    carol = client.post(
        "/entities", json={"entity_type": "person", "attributes": {"name": "Carol"}}
    ).json()["id"]
    client.post(
        "/relationships",
        json={
            "type": "RELATED_TO",
            "source_id": alice,
            "target_id": bob,
            "confidence_score": 80,
            "trust_weight": 70,
        },
    ).raise_for_status()
    client.post(
        "/relationships",
        json={
            "type": "RELATED_TO",
            "source_id": bob,
            "target_id": carol,
            "confidence_score": 80,
            "trust_weight": 70,
        },
    ).raise_for_status()
    return client, alice, bob, carol


class TestGraphAnalyticsAPI:
    def test_centrality_degree(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get(f"/graph/centrality/{alice}?algorithm=degree")
        assert resp.status_code == 200
        data = resp.json()
        assert data["node_id"] == alice
        assert data["algorithm"] == "degree"
        assert isinstance(data["centrality"], float)

    def test_centrality_pagerank(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get(f"/graph/centrality/{alice}?algorithm=pagerank")
        assert resp.status_code == 200
        data = resp.json()
        assert data["algorithm"] == "pagerank"
        assert isinstance(data["centrality"], float)

    def test_centrality_default_algorithm(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get(f"/graph/centrality/{alice}")
        assert resp.status_code == 200
        assert resp.json()["algorithm"] == "degree"

    def test_centrality_nonexistent_node(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get("/graph/centrality/nonexistent")
        assert resp.status_code == 200
        assert resp.json()["centrality"] == 0.0

    def test_centrality_betweenness(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get(f"/graph/centrality/{alice}?algorithm=betweenness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["algorithm"] == "betweenness"
        assert isinstance(data["centrality"], float)

    def test_centrality_closeness(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get(f"/graph/centrality/{alice}?algorithm=closeness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["algorithm"] == "closeness"
        assert isinstance(data["centrality"], float)

    def test_centrality_invalid_algorithm(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get(f"/graph/centrality/{alice}?algorithm=authority")
        assert resp.status_code == 400

    def test_stats(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get("/graph/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "node_count" in data
        assert "edge_count" in data
        assert "density" in data
        assert "average_degree" in data
        assert data["node_count"] >= 3

    def test_stats_empty_graph(self, client):
        resp = client.get("/graph/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["node_count"] == 0
        assert data["edge_count"] == 0
        assert data["density"] == 0.0

    def test_stats_detail(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get("/graph/stats?detail=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "clustering_coefficient" in data
        assert "max_degree" in data
        assert "min_degree" in data
        assert "degree_histogram" in data
        assert isinstance(data["degree_histogram"], list)

    def test_stats_detail_false_excludes_extra(self, seeded_client):
        client, alice, bob, carol = seeded_client
        resp = client.get("/graph/stats?detail=false")
        assert resp.status_code == 200
        data = resp.json()
        assert "clustering_coefficient" not in data
