from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class MetaAlert:
    alert_id: str
    category: str
    severity: str
    message: str
    source_layers: list[str]
    current_value: float
    threshold_value: float
    triggered_at: float = 0.0
    resolved: bool = False
    confirmed: bool = False
    entity_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "source_layers": self.source_layers,
            "current_value": round(self.current_value, 4),
            "threshold_value": self.threshold_value,
            "resolved": self.resolved,
            "confirmed": self.confirmed,
            "entity_id": self.entity_id,
        }


class IncidentControlCenter:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._alerts: list[MetaAlert] = []
        self._cooldowns: dict[str, float] = {}
        self._resolved_count = 0

    def evaluate(
        self,
        metrics: dict[str, Any],
        thresholds: dict[str, dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[MetaAlert]:
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
                alert = MetaAlert(
                    alert_id=f"mal_{uuid.uuid4().hex[:12]}",
                    category=key,
                    severity=threshold.get("severity", "warning"),
                    message=threshold.get("message", f"{key} exceeded threshold"),
                    source_layers=threshold.get("layers", ["metaintel"]),
                    current_value=current,
                    threshold_value=max_val,
                    triggered_at=now,
                    entity_id=ctx.get("entity_id", ""),
                )
                if self._can_alert(key, now):
                    triggered.append(alert)
                    self._alerts.append(alert)
        return triggered

    def _can_alert(self, key: str, now: float) -> bool:
        cooldown = self._cfg.get("cooldown_seconds", 300)
        last = self._cooldowns.get(key, 0.0)
        if now - last < cooldown:
            return False
        self._cooldowns[key] = now
        return True

    def resolve_alert(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                self._resolved_count += 1
                return True
        return False

    def confirm_alert(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.confirmed = True
                return True
        return False

    def mark_remediated(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                self._resolved_count += 1
                return True
        return False

    def get_active_alerts(self) -> list[MetaAlert]:
        return [a for a in self._alerts if not a.resolved]

    def get_alerts(self, category: str | None = None, limit: int = 100) -> list[MetaAlert]:
        results = list(self._alerts)
        if category:
            results = [a for a in results if a.category == category]
        return results[-limit:]
