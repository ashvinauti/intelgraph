from __future__ import annotations

import time
import uuid
from typing import Any


class UnifiedAlertingCore:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._alerts: list[dict[str, Any]] = []
        self._cooldowns: dict[str, float] = {}

    def evaluate(
        self,
        metrics: dict[str, Any],
        thresholds: dict[str, dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        triggered = []
        now = time.time()
        ctx = context or {}
        for key, threshold in thresholds.items():
            if not threshold.get("enabled", False):
                continue
            metric_key = threshold.get("metric_key", key)
            current = metrics.get(metric_key, 0.0)
            max_val = threshold.get("max", 1.0)
            if current > max_val:
                parts = [f"{key}: {current:.4f} exceeds {max_val}"]
                if ctx.get("entity_id"):
                    parts.insert(0, ctx["entity_id"])
                if ctx.get("source_summary"):
                    parts.append(f"source={{{ctx['source_summary']}}}")
                if ctx.get("confidence") is not None:
                    parts.append(f"conf={ctx['confidence']}")
                if ctx.get("path_summary"):
                    parts.append(f"path={{{ctx['path_summary']}}}")
                if ctx.get("contradiction"):
                    parts.append(f"contradiction={{{ctx['contradiction']}}}")
                if ctx.get("raw_context"):
                    parts.append(f"context='{ctx['raw_context'][:80]}'")
                alert = {
                    "alert_id": f"ua_{uuid.uuid4().hex[:12]}",
                    "category": key,
                    "severity": threshold.get("severity", "warning"),
                    "message": " — ".join(parts),
                    "metric_key": metric_key,
                    "current_value": current,
                    "threshold_value": max_val,
                    "context": dict(ctx),
                    "triggered_at": now,
                    "resolved": False,
                }
                if self._can_alert(key, now):
                    triggered.append(alert)
                    self._alerts.append(alert)
        return triggered

    def _can_alert(self, key: str, now: float) -> bool:
        cooldown = self._cfg.get("cooldown_seconds", 60)
        last = self._cooldowns.get(key, 0.0)
        if now - last < cooldown:
            return False
        self._cooldowns[key] = now
        return True

    def resolve_alert(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert["alert_id"] == alert_id:
                alert["resolved"] = True
                return True
        return False

    def get_active_alerts(self) -> list[dict[str, Any]]:
        return [a for a in self._alerts if not a["resolved"]]

    def get_alerts(self, category: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        results = list(self._alerts)
        if category:
            results = [a for a in results if a["category"] == category]
        return results[-limit:]
