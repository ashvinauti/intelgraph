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
    dave = client.post(
        "/entities", json={"entity_type": "person", "attributes": {"name": "Dave"}}
    ).json()["id"]
    client.post(
        "/relationships",
        json={
            "type": "RELATED_TO",
            "source_id": alice,
            "target_id": bob,
            "confidence_score": 90,
            "trust_weight": 80,
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
    client.post(
        "/relationships",
        json={
            "type": "RELATED_TO",
            "source_id": carol,
            "target_id": dave,
            "confidence_score": 70,
            "trust_weight": 60,
        },
    ).raise_for_status()
    return client, alice, bob, carol, dave


class TestMSTAPI:
    def test_mst_kruskal(self, seeded_client):
        client, *_ = seeded_client
        resp = client.post("/graph/algorithms/mst", params={"algorithm": "kruskal"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["algorithm"] == "kruskal"
        assert data["edge_count"] > 0
        assert "execution_time_ms" in data

    def test_mst_prim(self, seeded_client):
        client, *_ = seeded_client
        resp = client.post("/graph/algorithms/mst", params={"algorithm": "prim"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["algorithm"] == "prim"
        assert data["edge_count"] > 0

    def test_mst_empty_graph(self, auth_client):
        resp = auth_client.post("/graph/algorithms/mst", params={"algorithm": "kruskal"})
        assert resp.status_code == 404

    def test_mst_invalid_algorithm(self, seeded_client):
        client, *_ = seeded_client
        resp = client.post("/graph/algorithms/mst", params={"algorithm": "invalid"})
        assert resp.status_code == 400

    def test_mst_equal_weight(self, seeded_client):
        client, *_ = seeded_client
        r1 = client.post("/graph/algorithms/mst", params={"algorithm": "kruskal"}).json()
        r2 = client.post("/graph/algorithms/mst", params={"algorithm": "prim"}).json()
        assert r1["edge_count"] == r2["edge_count"]


class TestSCCAPI:
    def test_scc(self, seeded_client):
        client, *_ = seeded_client
        resp = client.post("/graph/algorithms/scc")
        assert resp.status_code == 200
        data = resp.json()
        assert "components" in data
        assert data["count"] >= 1
        assert "execution_time_ms" in data

    def test_scc_empty_graph(self, auth_client):
        resp = auth_client.post("/graph/algorithms/scc")
        assert resp.status_code == 404


class TestDiameterAPI:
    def test_diameter(self, seeded_client):
        client, *_ = seeded_client
        resp = client.post("/graph/algorithms/diameter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["diameter"] >= 1
        assert "path" in data
        assert "execution_time_ms" in data

    def test_diameter_empty_graph(self, auth_client):
        resp = auth_client.post("/graph/algorithms/diameter")
        assert resp.status_code == 404


class TestShortestPathAPI:
    def test_shortest_path(self, seeded_client):
        client, alice, bob, carol, dave = seeded_client
        resp = client.post(
            "/graph/algorithms/shortest-path",
            params={"source_id": alice, "target_id": dave},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["length"] == 3
        assert data["path"][0] == alice
        assert data["path"][-1] == dave

    def test_shortest_path_direct(self, seeded_client):
        client, alice, bob, carol, dave = seeded_client
        resp = client.post(
            "/graph/algorithms/shortest-path",
            params={"source_id": alice, "target_id": bob},
        )
        assert resp.status_code == 200
        assert resp.json()["length"] == 1

    def test_shortest_path_same_node(self, seeded_client):
        client, alice, bob, carol, dave = seeded_client
        resp = client.post(
            "/graph/algorithms/shortest-path",
            params={"source_id": alice, "target_id": alice},
        )
        assert resp.status_code == 200
        assert resp.json()["length"] == 0

    def test_shortest_path_nonexistent_source(self, seeded_client):
        client, *_ = seeded_client
        resp = client.post(
            "/graph/algorithms/shortest-path",
            params={
                "source_id": "nonexistent",
                "target_id": [
                    client.post(
                        "/entities", json={"entity_type": "person", "attributes": {"name": "X"}}
                    ).json()["id"]
                    for _ in range(1)
                ][0],
            },
        )
        assert resp.status_code == 404

    def test_shortest_path_nonexistent_target(self, seeded_client):
        client, alice, *_ = seeded_client
        resp = client.post(
            "/graph/algorithms/shortest-path",
            params={"source_id": alice, "target_id": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_shortest_path_invalid_heuristic(self, seeded_client):
        client, alice, bob, *_ = seeded_client
        resp = client.post(
            "/graph/algorithms/shortest-path",
            params={"source_id": alice, "target_id": bob, "heuristic_type": "euclidean"},
        )
        assert resp.status_code == 400


class TestAnalyticsAPI:
    def test_analytics(self, seeded_client):
        client, *_ = seeded_client
        resp = client.post("/graph/algorithms/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert "path_statistics" in data
        assert "component_distribution" in data
        assert "connectivity_metrics" in data
        assert data["component_distribution"]["component_count"] == 1

    def test_analytics_empty_graph(self, auth_client):
        resp = auth_client.post("/graph/algorithms/analytics")
        assert resp.status_code == 404


class TestMetricsIntegration:
    def test_mst_records_gauge(self, seeded_client):
        from intelgraph.core.enterprise import get_metrics

        client, *_ = seeded_client
        client.post("/graph/algorithms/mst", params={"algorithm": "kruskal"})
        snap = get_metrics().snapshot()
        gauges = snap.get("gauges", {})
        assert any("algorithm_mst" in k for k in gauges)

    def test_diameter_records_gauge(self, seeded_client):
        from intelgraph.core.enterprise import get_metrics

        client, *_ = seeded_client
        client.post("/graph/algorithms/diameter")
        snap = get_metrics().snapshot()
        gauges = snap.get("gauges", {})
        assert any("algorithm_diameter" in k for k in gauges)
