from intelgraph.core.enterprise.observability import MetricsCollector
from intelgraph.core.operations.alerting import AlertEngine


class TestAlertEngine:
    def test_no_thresholds_no_alerts(self):
        engine = AlertEngine({})
        alerts = engine.evaluate()
        assert alerts == []

    def test_error_rate_triggered(self):
        m = MetricsCollector()
        m.record_request("/test", 0.1, 500)
        m.record_request("/test", 0.1, 500)
        engine = AlertEngine(
            {
                "thresholds": {
                    "error_rate": {"enabled": True, "max": 1, "severity": "warning"},
                },
            }
        )
        engine._metrics = m
        alerts = engine.evaluate()
        assert len(alerts) == 1
        assert alerts[0].category == "error_rate"
        assert alerts[0].severity == "warning"
        assert alerts[0].current_value >= 2.0

    def test_latency_triggered(self):
        m = MetricsCollector()
        for _ in range(3):
            m.record_request("/slow", 2.0, 200)
        engine = AlertEngine(
            {
                "thresholds": {
                    "request_latency": {"enabled": True, "max_ms": 500.0, "severity": "critical"},
                },
            }
        )
        engine._metrics = m
        alerts = engine.evaluate()
        assert len(alerts) == 1
        assert alerts[0].category == "request_latency"
        assert alerts[0].severity == "critical"

    def test_cooldown_prevents_duplicate(self):
        m = MetricsCollector()
        m.record_request("/test", 0.1, 500)
        m.record_request("/test", 0.1, 500)
        engine = AlertEngine(
            {
                "thresholds": {
                    "error_rate": {"enabled": True, "max": 1, "severity": "warning"},
                },
                "cooldown_seconds": 3600,
            }
        )
        engine._metrics = m
        alerts1 = engine.evaluate()
        assert len(alerts1) == 1
        alerts2 = engine.evaluate()
        assert len(alerts2) == 0

    def test_get_alerts(self):
        m = MetricsCollector()
        m.record_request("/x", 0.1, 500)
        engine = AlertEngine(
            {
                "thresholds": {
                    "error_rate": {"enabled": True, "max": 0, "severity": "warning"},
                },
            }
        )
        engine._metrics = m
        engine.evaluate()
        history = engine.get_alerts()
        assert len(history) >= 1
        assert history[0]["category"] == "error_rate"

    def test_get_alerts_filtered(self):
        engine = AlertEngine({})
        alerts = engine.get_alerts(category="error_rate")
        assert isinstance(alerts, list)
