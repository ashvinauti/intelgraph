from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from typing import Any

import psutil


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_count: int = 0
        self._error_count: int = 0
        self._total_duration: float = 0.0
        self._endpoint_counts: dict[str, int] = defaultdict(int)
        self._status_counts: dict[int, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}

    def record_request(self, endpoint: str, duration: float, status_code: int) -> None:
        with self._lock:
            self._request_count += 1
            self._total_duration += duration
            self._endpoint_counts[endpoint] += 1
            self._status_counts[status_code] += 1
            if status_code >= 500:
                self._error_count += 1

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg_duration = self._total_duration / max(self._request_count, 1)
            result: dict[str, Any] = {
                "total_requests": self._request_count,
                "total_errors": self._error_count,
                "avg_duration_ms": round(avg_duration * 1000, 2),
                "endpoints": dict(self._endpoint_counts),
                "status_codes": {str(k): v for k, v in self._status_counts.items()},
            }
            if self._gauges:
                result["gauges"] = dict(self._gauges)
            return result


# ---------------------------------------------------------------------------
# PerformanceCollector — pipeline, API percentiles, system, component health
# ---------------------------------------------------------------------------

_WINDOW_SECONDS = 86400  # 24h rolling window
_MAX_LATENCY_SAMPLES = 10000


def _percentile(sorted_samples: list[float], p: float) -> float:
    if not sorted_samples:
        return 0.0
    k = (len(sorted_samples) - 1) * p / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_samples[int(k)]
    return sorted_samples[f] * (c - k) + sorted_samples[c] * (k - f)


class PerformanceCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Pipeline history (last 50)
        self._pipeline_runs: deque[dict[str, Any]] = deque(maxlen=50)
        # API latency samples per endpoint: {endpoint: [(timestamp, ms), ...]}
        self._latency_samples: dict[str, list[tuple[float, float]]] = defaultdict(list)
        # Component health: {name: {"last_run": ts, "status": "healthy"|"degraded"|"down",
        #                           "last_error": "", "run_count": int}}
        self._components: dict[str, dict[str, Any]] = {}
        # System metric snapshots for trend: deque of (timestamp, cpu, mem, disk)
        self._system_history: deque[tuple[float, float, float, float]] = deque(
            maxlen=720
        )  # 5sn * 720 = 1h
        # Pipeline run counts for alert thresholds
        self._pipeline_avg_duration: float = 0.0
        self._pipeline_run_count: int = 0

    # ------------------------------------------------------------------ #
    # Pipeline
    # ------------------------------------------------------------------ #
    def record_pipeline_run(
        self,
        duration_ms: float,
        entity_count: int,
        alert_count: int,
        incident_count: int,
        error_count: int,
        source_count: int = 0,
    ) -> None:
        with self._lock:
            now = time.time()
            record = {
                "timestamp": now,
                "duration_ms": round(duration_ms, 2),
                "entity_count": entity_count,
                "alert_count": alert_count,
                "incident_count": incident_count,
                "error_count": error_count,
                "source_count": source_count,
            }
            self._pipeline_runs.append(record)
            # Update rolling average
            total = self._pipeline_avg_duration * self._pipeline_run_count + duration_ms
            self._pipeline_run_count += 1
            self._pipeline_avg_duration = total / self._pipeline_run_count

    def get_pipeline_history(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._pipeline_runs)[-limit:]

    def get_pipeline_stats(self) -> dict[str, Any]:
        with self._lock:
            runs = list(self._pipeline_runs)
            if not runs:
                return {"run_count": 0}
            durations = [r["duration_ms"] for r in runs]
            return {
                "run_count": len(runs),
                "avg_duration_ms": round(sum(durations) / len(durations), 2),
                "min_duration_ms": round(min(durations), 2),
                "max_duration_ms": round(max(durations), 2),
                "last_duration_ms": round(durations[-1], 2),
            }

    # ------------------------------------------------------------------ #
    # API latency (p95/p99)
    # ------------------------------------------------------------------ #
    def record_api_latency(self, endpoint: str, duration_ms: float) -> None:
        with self._lock:
            samples = self._latency_samples[endpoint]
            samples.append((time.time(), duration_ms))
            # Trim old samples
            self._trim_samples(samples)
            # Cap list size
            if len(samples) > _MAX_LATENCY_SAMPLES:
                self._latency_samples[endpoint] = samples[-_MAX_LATENCY_SAMPLES:]

    def _trim_samples(self, samples: list[tuple[float, float]]) -> None:
        cutoff = time.time() - _WINDOW_SECONDS
        while samples and samples[0][0] < cutoff:
            samples.pop(0)

    def get_api_latency(self) -> dict[str, dict[str, float]]:
        with self._lock:
            result: dict[str, dict[str, float]] = {}
            for endpoint, samples in self._latency_samples.items():
                self._trim_samples(samples)
                if not samples:
                    continue
                vals = sorted(s for _, s in samples)
                result[endpoint] = {
                    "avg_ms": round(sum(vals) / len(vals), 2),
                    "p50_ms": round(_percentile(vals, 50), 2),
                    "p95_ms": round(_percentile(vals, 95), 2),
                    "p99_ms": round(_percentile(vals, 99), 2),
                    "sample_count": len(vals),
                }
            return result

    # ------------------------------------------------------------------ #
    # System metrics
    # ------------------------------------------------------------------ #
    def record_system_metrics(self) -> dict[str, float]:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        now = time.time()
        with self._lock:
            self._system_history.append((now, cpu, mem, disk))
        return {"cpu_percent": cpu, "memory_percent": mem, "disk_percent": disk}

    def get_system_metrics(self) -> dict[str, Any]:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        with self._lock:
            trend = list(self._system_history)
        return {
            "current": {
                "cpu_percent": cpu,
                "memory_percent": mem,
                "disk_percent": disk,
            },
            "trend": [
                {"timestamp": ts, "cpu": c, "memory": m, "disk": d}
                for ts, c, m, d in trend[-60:]  # last 5 min
            ],
        }

    # ------------------------------------------------------------------ #
    # Component health
    # ------------------------------------------------------------------ #
    def register_component(self, name: str) -> None:
        with self._lock:
            if name not in self._components:
                self._components[name] = {
                    "last_run": 0.0,
                    "status": "healthy",
                    "last_error": "",
                    "run_count": 0,
                    "error_count": 0,
                }

    def record_component_run(self, name: str, success: bool, error: str = "") -> None:
        with self._lock:
            comp = self._components.get(name)
            if comp is None:
                comp = {
                    "last_run": 0.0,
                    "status": "healthy",
                    "last_error": "",
                    "run_count": 0,
                    "error_count": 0,
                }
                self._components[name] = comp
            comp["last_run"] = time.time()
            comp["run_count"] += 1
            if success:
                if comp["status"] != "healthy":
                    comp["status"] = "healthy"
                comp["last_error"] = ""
            else:
                comp["error_count"] += 1
                comp["last_error"] = error
                if comp["error_count"] >= 3:
                    comp["status"] = "down"
                else:
                    comp["status"] = "degraded"

    def get_component_health(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": name,
                    "status": comp["status"],
                    "last_run": comp["last_run"],
                    "last_error": comp["last_error"],
                    "run_count": comp["run_count"],
                    "error_count": comp["error_count"],
                }
                for name, comp in sorted(self._components.items())
            ]

    def get_overall_health(self) -> dict[str, Any]:
        components = self.get_component_health()
        statuses = {c["status"] for c in components}
        if "down" in statuses:
            overall = "down"
        elif "degraded" in statuses:
            overall = "degraded"
        else:
            overall = "healthy" if components else "unknown"
        return {
            "overall_status": overall,
            "component_count": len(components),
            "healthy_count": sum(1 for c in components if c["status"] == "healthy"),
            "degraded_count": sum(1 for c in components if c["status"] == "degraded"),
            "down_count": sum(1 for c in components if c["status"] == "down"),
            "components": components,
        }

    # ------------------------------------------------------------------ #
    # Full snapshot
    # ------------------------------------------------------------------ #
    def full_snapshot(self) -> dict[str, Any]:
        return {
            "pipeline": self.get_pipeline_stats(),
            "pipeline_history": self.get_pipeline_history(10),
            "api_latency": self.get_api_latency(),
            "system": self.get_system_metrics(),
            "health": self.get_overall_health(),
        }


_perf = PerformanceCollector()


def get_performance_collector() -> PerformanceCollector:
    return _perf


# Original MetricsCollector singleton (Faz 14)
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    return _metrics
