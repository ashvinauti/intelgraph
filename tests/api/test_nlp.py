from __future__ import annotations

from fastapi.testclient import TestClient

from intelgraph.api.main import create_app


def _get_client():
    app = create_app({"storage": {"path": ":memory:"}})
    return TestClient(app)


class TestNLPEndpointsUnauthenticated:
    def setup_method(self):
        self.client = _get_client()

    def _auth_headers(self):
        resp = self.client.post(
            "/auth/register",
            json={
                "username": "analyst1",
                "password": "test123",
                "role": "analyst",
            },
        )
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_extract_entities(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/nlp/extract-entities",
            json={
                "text": "CVE-2024-1234 at 192.168.1.1",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2
        labels = {e["label"] for e in data["entities"]}
        assert "IP" in labels
        assert "CVE" in labels

    def test_extract_entities_empty_text(self):
        headers = self._auth_headers()
        resp = self.client.post("/nlp/extract-entities", json={"text": ""}, headers=headers)
        assert resp.status_code == 422

    def test_extract_relationships(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/nlp/extract-relationships",
            json={
                "text": "IP 192.168.1.1 connects to evil.com.",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "relationships" in data

    def test_extract_events(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/nlp/extract-events",
            json={
                "text": "The breach occurred at the network.",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data

    def test_classify_text(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/nlp/classify-text",
            json={
                "text": "CVE-2024-1234 ransomware attack.",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "threat_types" in data
        assert "top_type" in data

    def test_summarize_document(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/nlp/summarize-document",
            json={
                "text": "A vulnerability CVE-2024-1234 was found. It affects many systems. Ransomware is spreading.",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data

    def test_link_to_graph(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/nlp/link-to-graph",
            json={
                "text": "192.168.1.1 is bad.",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "link_accuracy" in data

    def test_ingest_text(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/nlp/ingest-text",
            json={
                "text": "CVE-2024-1234 was exploited by ransomware at 10.0.0.1 targeting corp.com.",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_count"] >= 3
        assert "classification" in data
        assert "summary" in data

    def test_list_models(self):
        headers = self._auth_headers()
        resp = self.client.get("/nlp/models", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert "count" in data

    def test_deploy_model_not_found(self):
        headers = self._auth_headers()
        resp = self.client.post("/nlp/models/nonexistent/deploy", headers=headers)
        assert resp.status_code in (403, 404)

    def test_analyze_roi(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/nlp/analyze-roi",
            json={
                "query_id": "test-1",
                "estimated_value": 100,
                "estimated_cost": 10,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "roi" in data
        assert data["decision"] == "approve"

    def test_budget_status(self):
        headers = self._auth_headers()
        resp = self.client.get("/nlp/budget-status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "budget_limit" in data


class TestNLPModelDeployment:
    def test_register_and_deploy_model_via_api(self):
        app = create_app({"storage": {"path": ":memory:"}})
        client = TestClient(app)
        resp = client.post(
            "/auth/register",
            json={
                "username": "admin1",
                "password": "admin123",
                "role": "admin",
            },
        )
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/nlp/models/some-model/deploy", headers=headers)
        assert resp.status_code == 404

    def test_full_pipeline_with_authz(self):
        app = create_app({"storage": {"path": ":memory:"}})
        client = TestClient(app)

        resp = client.post(
            "/auth/register",
            json={
                "username": "user1",
                "password": "test123",
                "role": "user",
            },
        )
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/nlp/extract-entities", json={"text": "test"}, headers=headers)
        assert resp.status_code == 200

        resp = client.post("/nlp/ingest-text", json={"text": "test"}, headers=headers)
        assert resp.status_code == 403
