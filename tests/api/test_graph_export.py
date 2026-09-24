import json

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
    dave = client.post(
        "/entities", json={"entity_type": "person", "attributes": {"name": "Dave"}}
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
            "confidence_score": 90,
            "trust_weight": 80,
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


class TestGraphExportAPI:
    def test_export_graphml(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/graphml")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml"
        xml = resp.text
        assert '<?xml version="1.0"' in xml
        assert "<graphml" in xml
        assert "<node " in xml
        assert "<edge " in xml

    def test_export_dot(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/dot")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/vnd.graphviz")
        dot = resp.text
        assert dot.startswith("graph G {")
        assert " -- " in dot

    def test_export_json(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        data = resp.json()
        assert "graph" in data
        assert len(data["graph"]["nodes"]) == 4
        assert len(data["graph"]["edges"]) == 3

    def test_export_unsupported_format(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/pdf")
        assert resp.status_code == 400

    def test_export_empty_graph(self, client):
        resp = client.get("/graph/export/json")
        assert resp.status_code == 404

    def test_export_pretty_json(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json?pretty=true")
        assert resp.status_code == 200
        assert resp.text.count("\n") > 5
        assert "  " in resp.text

    def test_export_compressed(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json?compressed=true")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/gzip"
        assert resp.headers.get("content-encoding") == "gzip"
        data = resp.json()
        assert len(data["graph"]["nodes"]) == 4

    def test_export_headers(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json")
        assert resp.status_code == 200
        assert "X-Export-Node-Count" in resp.headers
        assert "X-Export-Edge-Count" in resp.headers
        assert resp.headers["X-Export-Node-Count"] == "4"
        assert resp.headers["X-Export-Edge-Count"] == "3"

    def test_export_content_disposition(self, seeded_client):
        client, *_ = seeded_client
        for fmt in ("graphml", "dot", "json"):
            resp = client.get(f"/graph/export/{fmt}")
            assert resp.status_code == 200
            assert "Content-Disposition" in resp.headers
            assert f"intelgraph.{fmt}" in resp.headers["Content-Disposition"]

    def test_export_filter_by_entity_type(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json?entity_type=person")
        assert resp.status_code == 200
        data = resp.json()
        for node in data["graph"]["nodes"]:
            assert node.get("entity_type") == "person"

    def test_export_min_confidence(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json?min_confidence=80")
        assert resp.status_code == 200
        data = resp.json()
        for edge in data["graph"]["edges"]:
            assert edge["confidence_score"] >= 80

    def test_export_subgraph(self, seeded_client):
        client, alice, bob, carol, dave = seeded_client
        resp = client.get(f"/graph/export/json?subgraph_node_id={alice}&subgraph_depth=1")
        assert resp.status_code == 200
        data = resp.json()
        node_ids = {n["id"] for n in data["graph"]["nodes"]}
        assert alice in node_ids
        assert bob in node_ids
        assert carol not in node_ids
        assert dave not in node_ids

    def test_export_subgraph_depth_2(self, seeded_client):
        client, alice, bob, carol, dave = seeded_client
        resp = client.get(f"/graph/export/json?subgraph_node_id={alice}&subgraph_depth=2")
        assert resp.status_code == 200
        data = resp.json()
        node_ids = {n["id"] for n in data["graph"]["nodes"]}
        assert alice in node_ids
        assert bob in node_ids
        assert carol in node_ids
        assert dave not in node_ids

    def test_export_exclude_entity_type(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json?exclude_entity_type=person")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["graph"]["nodes"]) == 0

    def test_export_metadata(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json")
        assert resp.status_code == 200
        data = resp.json()
        assert "metadata" in data
        assert data["metadata"]["graph"]["node_count"] == 4

    def test_dot_contains_metadata_comment(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/dot")
        assert resp.status_code == 200
        assert "// Metadata:" in resp.text

    def test_graphml_contains_metadata(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/graphml")
        assert resp.status_code == 200
        assert "exported_at" in resp.text

    def test_export_invalid_params(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json?min_confidence=200")
        assert resp.status_code == 422

    def test_export_community_annotations(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json?include_community=true")
        assert resp.status_code == 200
        data = resp.json()
        for node in data["graph"]["nodes"]:
            assert node.get("community_id") is None

    def test_export_centrality_annotations(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json?include_centrality=true")
        assert resp.status_code == 200

    def test_export_streaming(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json")
        assert resp.status_code == 200
        assert len(resp.content) > 0
        data = json.loads(resp.content)
        assert len(data["graph"]["nodes"]) == 4


class TestGraphExportAuth:
    def test_unauthenticated_empty_graph_not_found(self, client):
        resp = client.get("/graph/export/json")
        assert resp.status_code == 404

    def test_authenticated_access_succeeds(self, seeded_client):
        client, *_ = seeded_client
        resp = client.get("/graph/export/json")
        assert resp.status_code == 200
