from fastapi.testclient import TestClient

from intelgraph.api.main import create_app


def _get_client():
    app = create_app({"storage": {"path": ":memory:"}})
    return TestClient(app)


class TestCognitiveEndpoints:
    def setup_method(self):
        self.client = _get_client()

    def _auth_headers(self, role: str = "analyst"):
        resp = self.client.post(
            "/auth/register",
            json={
                "username": f"{role}1",
                "password": "test123",
                "role": role,
            },
        )
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_reasoning_query(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/query",
            json={
                "start": "A",
                "end": "B",
                "type": "multi_hop",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data
        assert "trace_id" in data

    def test_reasoning_query_invalid(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/query",
            json={
                "start": "",
                "end": "",
            },
            headers=headers,
        )
        assert resp.status_code == 422

    def test_reasoning_explain_nonexistent(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/explain",
            json={
                "trace_id": "nonexistent",
            },
            headers=headers,
        )
        assert resp.status_code == 404

    def test_hypothesis_generate(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/hypothesis/generate",
            json={
                "graph": None,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "hypotheses" in data

    def test_learning_feedback(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/learning/feedback",
            json={
                "query_id": "q1",
                "analyst_id": "analyst_1",
                "feedback_type": "correction",
                "score": 0.9,
                "correction": {"key": "value"},
                "original_output": {"key": "original"},
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["feedback_type"] == "correction"
        assert data["applied"]

    def test_learning_feedback_invalid(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/learning/feedback",
            json={
                "query_id": "",
                "analyst_id": "",
            },
            headers=headers,
        )
        assert resp.status_code == 422

    def test_get_trace_nonexistent(self):
        headers = self._auth_headers()
        resp = self.client.get("/reasoning/reasoning/trace/nonexistent", headers=headers)
        assert resp.status_code == 404

    def test_validate_hypothesis(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/validate",
            json={
                "hypothesis_id": "nonexistent",
                "confidence": 0.8,
            },
            headers=headers,
        )
        assert resp.status_code == 404

    def test_validate_hypothesis_invalid(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/validate",
            json={
                "hypothesis_id": "",
            },
            headers=headers,
        )
        assert resp.status_code == 422

    def test_detect_contradictions(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/reasoning/contradictions/detect",
            json={
                "facts": [
                    {"entity": "E1", "attribute": "score", "value": 100, "confidence": 0.9},
                    {"entity": "E1", "attribute": "score", "value": 0, "confidence": 0.9},
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

    def test_authz_rejection(self):
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
        resp = client.post(
            "/reasoning/validate",
            json={
                "hypothesis_id": "h1",
                "confidence": 0.5,
            },
            headers=headers,
        )
        assert resp.status_code == 403
