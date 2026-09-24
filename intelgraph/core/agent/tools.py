from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ToolType(Enum):
    REST = "rest"
    GRAPHQL = "graphql"
    DATABASE = "database"
    FILE = "file"
    WEBHOOK = "webhook"
    SOC = "soc"
    CLOUD = "cloud"
    INTERNAL = "internal"


class ActionRisk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ToolCall:
    call_id: str
    tool_type: ToolType
    action: str
    params: dict[str, Any]
    risk_score: float
    requires_approval: bool
    sandbox_level: str
    created_at: float = 0.0
    result: Any = None
    success: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_type": self.tool_type.value,
            "action": self.action,
            "params": {
                k: "***" if k in ("password", "secret", "token", "api_key") else v
                for k, v in self.params.items()
            },
            "risk_score": round(self.risk_score, 4),
            "requires_approval": self.requires_approval,
            "sandbox_level": self.sandbox_level,
            "success": self.success,
            "error": self.error,
        }


class ToolExecutor:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._calls: list[ToolCall] = []
        self._pre_hooks: list[Callable] = []
        self._post_hooks: list[Callable] = []
        self._sandbox_enabled = self._cfg.get("sandbox_enabled", True)
        self._sandbox_levels = {"none": 0, "light": 1, "medium": 2, "strict": 3}

    def register_pre_hook(self, hook: Callable) -> None:
        self._pre_hooks.append(hook)

    def register_post_hook(self, hook: Callable) -> None:
        self._post_hooks.append(hook)

    def execute(
        self, tool_type: ToolType, action: str, params: dict[str, Any], sandbox: str = "medium"
    ) -> ToolCall:
        call = ToolCall(
            call_id=f"tc_{uuid.uuid4().hex[:12]}",
            tool_type=tool_type,
            action=action,
            params=params,
            risk_score=self._compute_risk(tool_type, action),
            requires_approval=self._needs_approval(tool_type, action),
            sandbox_level=sandbox,
            created_at=time.time(),
        )
        for hook in self._pre_hooks:
            hook(call)
        if self._sandbox_enabled and self._sandbox_levels.get(sandbox, 0) >= 2:
            call = self._apply_sandbox(call)
        if call.risk_score > 0.7 and not call.requires_approval:
            call.requires_approval = True
        if not call.requires_approval:
            call.result = self._simulate_execution(tool_type, action, params)
            call.success = True
        for hook in self._post_hooks:
            hook(call)
        self._calls.append(call)
        return call

    def approve(self, call_id: str) -> bool:
        for call in self._calls:
            if call.call_id == call_id and call.requires_approval:
                call.result = self._simulate_execution(call.tool_type, call.action, call.params)
                call.success = True
                call.requires_approval = False
                return True
        return False

    def rollback(self, call_id: str) -> bool:
        for call in self._calls:
            if call.call_id == call_id and call.success:
                call.success = False
                call.error = "Rolled back"
                return True
        return False

    def _compute_risk(self, tool_type: ToolType, action: str) -> float:
        risk_map = {
            ToolType.REST: 0.4,
            ToolType.GRAPHQL: 0.5,
            ToolType.DATABASE: 0.7,
            ToolType.FILE: 0.6,
            ToolType.WEBHOOK: 0.5,
            ToolType.SOC: 0.8,
            ToolType.CLOUD: 0.9,
            ToolType.INTERNAL: 0.3,
        }
        base = risk_map.get(tool_type, 0.5)
        if "delete" in action.lower() or "drop" in action.lower():
            base = min(1.0, base + 0.3)
        if "read" in action.lower() or "get" in action.lower():
            base = max(0.1, base - 0.2)
        return base

    def _needs_approval(self, tool_type: ToolType, action: str) -> bool:
        high_risk_actions = ["delete", "drop", "truncate", "shutdown", "terminate", "destroy"]
        if tool_type in (ToolType.CLOUD, ToolType.SOC, ToolType.DATABASE):
            if any(a in action.lower() for a in high_risk_actions):
                return True
        return self._compute_risk(tool_type, action) > 0.7

    def _apply_sandbox(self, call: ToolCall) -> ToolCall:
        if call.tool_type == ToolType.FILE:
            safe_params = {}
            for k, v in call.params.items():
                if isinstance(v, str) and ".." in v:
                    v = v.replace("..", "")
                safe_params[k] = v
            call.params = safe_params
        return call

    def _simulate_execution(
        self, tool_type: ToolType, action: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if tool_type == ToolType.REST:
            return {"status": 200, "body": f"Simulated {action} on {params.get('url', 'unknown')}"}
        if tool_type == ToolType.DATABASE:
            return {"rows_affected": 1, "query": action}
        if tool_type == ToolType.FILE:
            return {"path": params.get("path", ""), "written": True}
        if tool_type == ToolType.WEBHOOK:
            return {"delivered": True, "target": params.get("url", "")}
        return {"simulated": True, "action": action}

    def get_history(self, limit: int = 100) -> list[ToolCall]:
        return self._calls[-limit:]
