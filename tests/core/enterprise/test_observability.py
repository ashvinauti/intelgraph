from intelgraph.core.enterprise.observability import MetricsCollector, get_metrics


class TestMetricsCollector:
    def test_initial_snapshot(self):
        m = MetricsCollector()
        s = m.snapshot()
        assert s["total_requests"] == 0
        assert s["total_errors"] == 0

    def test_record_request(self):
        m = MetricsCollector()
        m.record_request("/test", 0.1, 200)
        s = m.snapshot()
        assert s["total_requests"] == 1
        assert s["endpoints"] == {"/test": 1}
        assert s["avg_duration_ms"] > 0

    def test_record_error(self):
        m = MetricsCollector()
        m.record_request("/error", 0.05, 500)
        s = m.snapshot()
        assert s["total_errors"] == 1
        assert s["status_codes"]["500"] == 1

    def test_multiple_endpoints(self):
        m = MetricsCollector()
        m.record_request("/a", 0.1, 200)
        m.record_request("/b", 0.2, 200)
        m.record_request("/a", 0.15, 404)
        s = m.snapshot()
        assert s["total_requests"] == 3
        assert s["endpoints"]["/a"] == 2
        assert s["endpoints"]["/b"] == 1

    def test_get_metrics_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2
