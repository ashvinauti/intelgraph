from __future__ import annotations

import os
import threading
import time
from typing import Any

from intelgraph.core.enterprise import get_performance_collector

_CHECK_INTERVAL = 60  # seconds
_ALERT_THRESHOLDS: dict[str, Any] = {
    "memory_percent": float(os.environ.get("INTELGRAPH_ALERT_MEMORY_PCT", "90")),
    "cpu_percent": float(os.environ.get("INTELGRAPH_ALERT_CPU_PCT", "95")),
    "pipeline_duration_multiplier": float(os.environ.get("INTELGRAPH_ALERT_PIPELINE_MULT", "3.0")),
}


def _start_alert_checker() -> None:
    """Start a daemon thread that periodically checks performance thresholds
    and sends notifications via the notification system."""
    thread = threading.Thread(target=_alert_loop, daemon=True)
    thread.start()


def _alert_loop() -> None:
    while True:
        try:
            _check_thresholds()
        except Exception:
            pass
        time.sleep(_CHECK_INTERVAL)


def _check_thresholds() -> None:
    perf = get_performance_collector()
    system = perf.get_system_metrics()
    current = system.get("current", {})
    health = perf.get_overall_health()
    pipeline = perf.get_pipeline_stats()
    triggered: list[str] = []

    # Memory threshold
    mem = current.get("memory_percent", 0)
    if mem >= _ALERT_THRESHOLDS["memory_percent"]:
        triggered.append(f"Memory at {mem}% (threshold: {_ALERT_THRESHOLDS['memory_percent']}%)")

    # CPU threshold
    cpu = current.get("cpu_percent", 0)
    if cpu >= _ALERT_THRESHOLDS["cpu_percent"]:
        triggered.append(f"CPU at {cpu}% (threshold: {_ALERT_THRESHOLDS['cpu_percent']}%)")

    # Pipeline duration threshold (3x rolling average)
    if pipeline.get("run_count", 0) >= 3:
        avg = pipeline.get("avg_duration_ms", 0)
        last = pipeline.get("last_duration_ms", 0)
        if avg > 0 and last > avg * _ALERT_THRESHOLDS["pipeline_duration_multiplier"]:
            triggered.append(
                f"Pipeline duration {last}ms exceeds {_ALERT_THRESHOLDS['pipeline_duration_multiplier']}x average ({avg}ms)"
            )

    # Component down
    if health.get("down_count", 0) > 0:
        down_comps = [c["name"] for c in health.get("components", []) if c["status"] == "down"]
        if down_comps:
            triggered.append(f"Down components: {', '.join(down_comps)}")

    if triggered:
        _send_alert(triggered)


def _send_alert(messages: list[str]) -> None:
    try:
        from intelgraph.core.notification.manager import NotificationManager

        notifier = NotificationManager()
        notifier.send_event_async(
            NotificationManager.build_event(
                event_type="performance_alert",
                severity="high",
                title="Performance threshold exceeded",
                body=" | ".join(messages),
                metadata={"alerts": messages},
            )
        )
    except Exception:
        pass


# Start on import
_start_alert_checker()
