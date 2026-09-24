from __future__ import annotations

import pytest

from intelgraph.core.enterprise.observability import PerformanceCollector, get_performance_collector


def _fresh_collector():
    """Return a fresh PerformanceCollector with clean state."""
    return PerformanceCollector()


class TestPipelineMetrics:
    def test_record_pipeline_run(self):
        p = _fresh_collector()
        p.record_pipeline_run(1000.0, 50, 3, 1, 0, source_count=2)
        history = p.get_pipeline_history(10)
        assert len(history) == 1
        assert history[0]["duration_ms"] == 1000.0
        assert history[0]["entity_count"] == 50
        assert history[0]["alert_count"] == 3
        assert history[0]["incident_count"] == 1
        assert history[0]["error_count"] == 0
        assert history[0]["source_count"] == 2

    def test_multiple_runs(self):
        p = _fresh_collector()
        for i in range(5):
            p.record_pipeline_run(500.0 + i * 100, 10 + i, 1, 0, 0)
        history = p.get_pipeline_history(10)
        assert len(history) == 5

    def test_pipeline_stats(self):
        p = _fresh_collector()
        p.record_pipeline_run(1000.0, 50, 3, 1, 0)
        p.record_pipeline_run(2000.0, 80, 5, 2, 1)
        stats = p.get_pipeline_stats()
        assert stats["run_count"] == 2
        assert stats["avg_duration_ms"] == 1500.0
        assert stats["min_duration_ms"] == 1000.0
        assert stats["max_duration_ms"] == 2000.0
        assert stats["last_duration_ms"] == 2000.0

    def test_pipeline_history_limit(self):
        p = _fresh_collector()
        for i in range(20):
            p.record_pipeline_run(float(i), i, 0, 0, 0)
        history = p.get_pipeline_history(5)
        assert len(history) == 5

    def test_empty_pipeline_stats(self):
        p = _fresh_collector()
        stats = p.get_pipeline_stats()
        assert stats["run_count"] == 0


class TestAPILatencyMetrics:
    def test_record_latency(self):
        p = _fresh_collector()
        p.record_api_latency("/api/test", 50.0)
        p.record_api_latency("/api/test", 100.0)
        p.record_api_latency("/api/test", 150.0)
        p.record_api_latency("/api/test", 200.0)

        latency = p.get_api_latency()
        assert "/api/test" in latency
        stats = latency["/api/test"]
        assert stats["sample_count"] == 4
        assert stats["avg_ms"] == 125.0
        # For 4 samples: p50 = (100+150)/2=125, p95=index 3=200, p99=200
        assert stats["p50_ms"] == 125.0
        assert stats["p95_ms"] == 192.5
        assert stats["p99_ms"] == 198.5

    def test_multiple_endpoints(self):
        p = _fresh_collector()
        p.record_api_latency("/api/a", 10.0)
        p.record_api_latency("/api/b", 20.0)
        latency = p.get_api_latency()
        assert len(latency) == 2

    def test_empty_latency(self):
        p = _fresh_collector()
        assert p.get_api_latency() == {}


class TestSystemMetrics:
    def test_record_system_metrics_returns_values(self):
        p = _fresh_collector()
        metrics = p.record_system_metrics()
        assert "cpu_percent" in metrics
        assert "memory_percent" in metrics
        assert "disk_percent" in metrics
        assert 0 <= metrics["cpu_percent"] <= 100
        assert 0 <= metrics["memory_percent"] <= 100
        assert 0 <= metrics["disk_percent"] <= 100

    def test_get_system_metrics(self):
        p = _fresh_collector()
        p.record_system_metrics()
        p.record_system_metrics()
        sys_metrics = p.get_system_metrics()
        assert "current" in sys_metrics
        assert "trend" in sys_metrics
        assert len(sys_metrics["trend"]) == 2

    def test_system_trend_contains_fields(self):
        p = _fresh_collector()
        p.record_system_metrics()
        trend = p.get_system_metrics()["trend"]
        assert len(trend) == 1
        entry = trend[0]
        assert "timestamp" in entry
        assert "cpu" in entry
        assert "memory" in entry
        assert "disk" in entry


class TestComponentHealth:
    def test_register_component(self):
        p = _fresh_collector()
        p.register_component("TestEngine")
        health = p.get_component_health()
        names = [c["name"] for c in health]
        assert "TestEngine" in names

    def test_record_component_run_success(self):
        p = _fresh_collector()
        p.register_component("TestEngine")
        p.record_component_run("TestEngine", success=True)
        health = p.get_component_health()
        te = [c for c in health if c["name"] == "TestEngine"][0]
        assert te["status"] == "healthy"
        assert te["run_count"] == 1
        assert te["error_count"] == 0

    def test_record_component_run_failure_degraded(self):
        p = _fresh_collector()
        p.register_component("TestEngine")
        p.record_component_run("TestEngine", success=False, error="timeout")
        health = p.get_component_health()
        te = [c for c in health if c["name"] == "TestEngine"][0]
        assert te["status"] == "degraded"
        assert te["error_count"] == 1
        assert te["last_error"] == "timeout"

    def test_three_failures_triggers_down(self):
        p = _fresh_collector()
        p.register_component("TestEngine")
        for _ in range(3):
            p.record_component_run("TestEngine", success=False, error="error")
        health = p.get_component_health()
        te = [c for c in health if c["name"] == "TestEngine"][0]
        assert te["status"] == "down"
        assert te["error_count"] == 3

    def test_recovery_from_degraded(self):
        p = _fresh_collector()
        p.register_component("TestEngine")
        p.record_component_run("TestEngine", success=False, error="fail")
        p.record_component_run("TestEngine", success=True)
        health = p.get_component_health()
        te = [c for c in health if c["name"] == "TestEngine"][0]
        assert te["status"] == "healthy"
        assert te["last_error"] == ""

    def test_overall_health_unknown_when_no_components(self):
        p = _fresh_collector()
        oh = p.get_overall_health()
        assert oh["overall_status"] == "unknown"

    def test_overall_health_healthy(self):
        p = _fresh_collector()
        p.register_component("A")
        p.record_component_run("A", success=True)
        oh = p.get_overall_health()
        assert oh["overall_status"] == "healthy"

    def test_overall_health_degraded(self):
        p = _fresh_collector()
        p.register_component("A")
        p.record_component_run("A", success=False, error="fail")
        oh = p.get_overall_health()
        assert oh["overall_status"] == "degraded"

    def test_overall_health_down(self):
        p = _fresh_collector()
        p.register_component("A")
        for _ in range(3):
            p.record_component_run("A", success=False, error="fail")
        oh = p.get_overall_health()
        assert oh["overall_status"] == "down"


class TestFullSnapshot:
    def test_snapshot_contains_all_keys(self):
        p = _fresh_collector()
        p.record_pipeline_run(500.0, 10, 1, 0, 0)
        p.record_api_latency("/api/test", 50.0)
        p.record_system_metrics()
        p.register_component("Test")
        p.record_component_run("Test", success=True)
        snap = p.full_snapshot()
        assert "pipeline" in snap
        assert "pipeline_history" in snap
        assert "api_latency" in snap
        assert "system" in snap
        assert "health" in snap

    def test_snapshot_pipeline_stats(self):
        p = _fresh_collector()
        p.record_pipeline_run(1000.0, 50, 3, 1, 0)
        snap = p.full_snapshot()
        assert snap["pipeline"]["run_count"] == 1
        assert snap["pipeline_history"][0]["duration_ms"] == 1000.0


class TestSingleton:
    def test_get_performance_collector_returns_same(self):
        p1 = get_performance_collector()
        p2 = get_performance_collector()
        assert p1 is p2

    def test_singleton_records_pipeline(self):
        p = get_performance_collector()
        # Record on singleton
        p.record_pipeline_run(500.0, 10, 1, 0, 0)
        stats = p.get_pipeline_stats()
        assert stats["run_count"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
