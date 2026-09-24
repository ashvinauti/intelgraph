from fastapi.testclient import TestClient

from intelgraph.api.main import create_app


class TestMetricsEndpoint:
    def test_metrics_returns_prometheus(self):
        app = create_app({"storage": {"path": ":memory:"}})
        with TestClient(app) as c:
            resp = c.get("/metrics")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        text = resp.text
        assert "intelgraph_request_count_total" in text
        assert "intelgraph_error_count_total" in text
        assert "intelgraph_request_latency_ms" in text
        assert "intelgraph_active_connections" in text
        assert "# HELP" in text
        assert "# TYPE" in text

    def test_metrics_counts_update(self):
        app = create_app({"storage": {"path": ":memory:"}})
        with TestClient(app) as c:
            c.get("/health")
            c.get("/health/live")
            c.get("/nonexistent-endpoint")
            resp = c.get("/metrics")
        text = resp.text
        assert 'intelgraph_endpoint_requests_total{endpoint="/health"}' in text
        assert 'intelgraph_endpoint_requests_total{endpoint="/health/live"}' in text

    def test_metrics_plaintext_format(self):
        app = create_app({"storage": {"path": ":memory:"}})
        with TestClient(app) as c:
            resp = c.get("/metrics")
        lines = resp.text.strip().split("\n")
        for line in lines:
            if line.startswith("#"):
                assert (
                    line.startswith("# ") or line.startswith("# TYPE") or line.startswith("# HELP")
                )
            elif line:
                parts = line.split(" ")
                assert len(parts) >= 2
