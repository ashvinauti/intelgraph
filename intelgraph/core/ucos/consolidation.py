from __future__ import annotations

import importlib
import inspect
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

UCOS_SCHEMA_VERSION = "1.0"


@dataclass
class EngineRecord:
    engine_id: str
    name: str
    module_path: str
    class_name: str
    phase: str
    function: str
    status: str
    duplicate_of: str = ""
    consolidation_action: str = ""
    detected_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "name": self.name,
            "module_path": self.module_path,
            "class_name": self.class_name,
            "phase": self.phase,
            "function": self.function,
            "status": self.status,
            "duplicate_of": self.duplicate_of,
            "consolidation_action": self.consolidation_action,
        }


class ConsolidationEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._engines: list[EngineRecord] = []
        self._duplicates: list[dict[str, Any]] = []
        self._consolidation_log: list[dict[str, Any]] = []
        self._scan_core_modules()

    def _scan_core_modules(self) -> None:
        phases = {
            "intelgraph.core.nlp": "29",
            "intelgraph.core.cognitive": "30",
            "intelgraph.core.agent": "31",
            "intelgraph.core.metaintel": "32",
            "intelgraph.core.graph": "16",
            "intelgraph.core.kernel": "27",
            "intelgraph.core.governance": "27",
            "intelgraph.core.safety": "27",
        }
        function_labels = {
            "SafetyGovernor": "safety",
            "SafetyGuard": "safety",
            "PolicyEvolutionEngine": "policy",
            "PolicyEvaluator": "policy",
            "GlobalGovernanceEngine": "governance",
            "GovernancePolicyEngine": "governance",
            "TruthConsistencyGovernor": "truth",
            "GlobalObservabilityDashboard": "observability",
            "SystemDiagnostics": "diagnostics",
            "AgentOrchestrator": "execution",
            "ToolExecutor": "execution",
            "ReasoningEngine": "reasoning",
            "MetaReasoningEngine": "reasoning",
            "HypothesisGenerator": "hypothesis",
            "SelfLearningLoop": "learning",
            "SelfImprovementController": "optimization",
            "IdentityConsistencyLayer": "identity",
            "RealWorldAlignmentLayer": "alignment",
            "SafetyMetaControlLayer": "safety",
            "IncidentControlCenter": "alerting",
            "ArchitectureEvolutionEngine": "architecture",
            "VersionedSystemState": "state",
            "ExecutionAudit": "audit",
            "ExecutionFeedbackLoop": "feedback",
            "SimulationEngine": "simulation",
            "Predictor": "prediction",
            "ModelRegistry": "models",
            "AnomalyDetector": "anomaly",
            "AttackPathAnalyzer": "attack_path",
            "CausalReasoner": "causal",
            "CommunityDetector": "community",
            "InfluencePropagation": "influence",
            "NEREngine": "ner",
            "NLPModelRegistry": "nlp_models",
        }
        for mod_name, phase in phases.items():
            try:
                mod = importlib.import_module(mod_name)
                for name, _cls in inspect.getmembers(mod, inspect.isclass):
                    fn = function_labels.get(name, "other")
                    self._engines.append(
                        EngineRecord(
                            engine_id=f"e_{uuid.uuid4().hex[:8]}",
                            name=name,
                            module_path=mod_name,
                            class_name=name,
                            phase=phase,
                            function=fn,
                            status="active",
                            detected_at=time.time(),
                        )
                    )
            except Exception:
                pass

    def detect_duplicates(self) -> list[dict[str, Any]]:
        by_function: dict[str, list[EngineRecord]] = defaultdict(list)
        for eng in self._engines:
            if eng.function != "other":
                by_function[eng.function].append(eng)
        duplicates = []
        for fn, engines in by_function.items():
            if len(engines) > 1:
                phases = [e.phase for e in engines]
                if len(set(phases)) > 1:
                    engines.sort(key=lambda e: int(e.phase))
                    primary = engines[0]
                    for dup in engines[1:]:
                        record = {
                            "function": fn,
                            "primary": primary.to_dict(),
                            "duplicate": dup.to_dict(),
                            "consolidation": f"Merge {dup.class_name} (Phase {dup.phase}) into {primary.class_name} (Phase {primary.phase})",
                        }
                        duplicates.append(record)
                        dup.duplicate_of = primary.engine_id
                        dup.status = "consolidated"
                        dup.consolidation_action = record["consolidation"]
        self._duplicates = duplicates
        return duplicates

    def consolidation_plan(self) -> dict[str, Any]:
        dups = self.detect_duplicates()
        by_fn: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for d in dups:
            by_fn[d["function"]].append(d)
        plan = []
        for fn, items in by_fn.items():
            for item in items:
                plan.append(
                    {
                        "action": item["consolidation"],
                        "target_function": fn,
                        "remove_module": item["duplicate"]["module_path"],
                        "keep_module": item["primary"]["module_path"],
                    }
                )
                self._consolidation_log.append(
                    {
                        "action": item["consolidation"],
                        "timestamp": time.time(),
                        "status": "planned",
                    }
                )
        return {
            "duplicates_found": len(dups),
            "functions_affected": len(by_fn),
            "consolidation_plan": plan,
            "engines_scanned": len(self._engines),
        }

    def get_engines(self) -> list[EngineRecord]:
        return list(self._engines)

    def get_consolidation_log(self) -> list[dict[str, Any]]:
        return list(self._consolidation_log)

    def compute_complexity_index(self) -> float:
        active = [e for e in self._engines if e.status == "active"]
        dups = len(self._duplicates)
        return max(0.0, 1.0 - (dups / max(len(active), 1)))
