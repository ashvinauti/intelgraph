from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class AlignmentScore:
    score_id: str
    metric: str
    value: float
    threshold: float
    aligned: bool
    source: str
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "metric": self.metric,
            "value": round(self.value, 4),
            "threshold": self.threshold,
            "aligned": self.aligned,
            "source": self.source,
        }


class RealWorldAlignmentLayer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._alignment_scores: list[AlignmentScore] = []
        self._external_signals: list[dict[str, Any]] = []
        self._drift_events: list[dict[str, Any]] = []
        self._ground_truth: dict[str, Any] = {}

    def compare_output_vs_reality(
        self, system_output: dict[str, Any], real_world_data: dict[str, Any]
    ) -> list[AlignmentScore]:
        scores = []
        for key in set(system_output.keys()) & set(real_world_data.keys()):
            sys_val = system_output[key]
            real_val = real_world_data[key]
            if isinstance(sys_val, (int, float)) and isinstance(real_val, (int, float)):
                if abs(real_val) > 0:
                    deviation = abs(sys_val - real_val) / abs(real_val)
                    aligned = deviation < 0.2
                else:
                    deviation = abs(sys_val)
                    aligned = deviation < 0.1
                score = AlignmentScore(
                    score_id=f"al_{uuid.uuid4().hex[:12]}",
                    metric=key,
                    value=deviation,
                    threshold=0.2,
                    aligned=aligned,
                    source="output_vs_reality",
                    timestamp=time.time(),
                )
                scores.append(score)
        self._alignment_scores.extend(scores)
        return scores

    def detect_reality_drift(self, current_scores: list[AlignmentScore]) -> list[dict[str, Any]]:
        drifts = []
        for score in current_scores:
            if not score.aligned:
                drifts.append(
                    {
                        "metric": score.metric,
                        "deviation": score.value,
                        "threshold": score.threshold,
                        "severity": "high" if score.value > 0.5 else "medium",
                    }
                )
        return drifts

    def integrate_external_signal(self, signal: dict[str, Any]) -> None:
        signal["received_at"] = time.time()
        self._external_signals.append(signal)

    def reconcile_belief_vs_truth(
        self, belief: dict[str, Any], truth: dict[str, Any]
    ) -> dict[str, Any]:
        reconciled = {}
        for key in set(belief.keys()) | set(truth.keys()):
            if key in belief and key in truth:
                if belief[key] != truth[key]:
                    reconciled[key] = {
                        "value": truth[key],
                        "source": "ground_truth",
                        "corrected": True,
                    }
                else:
                    reconciled[key] = {
                        "value": belief[key],
                        "source": "consistent",
                        "corrected": False,
                    }
            elif key in truth:
                reconciled[key] = {
                    "value": truth[key],
                    "source": "ground_truth",
                    "corrected": False,
                }
        return reconciled

    def validate_ground_truth(self, claim: dict[str, Any]) -> bool:
        claim_key = claim.get("key", "")
        claim_value = claim.get("value")
        truth_value = self._ground_truth.get(claim_key)
        if truth_value is None:
            return False
        return truth_value == claim_value

    def set_ground_truth(self, key: str, value: Any) -> None:
        self._ground_truth[key] = value

    def get_alignment_scores(self, limit: int = 100) -> list[AlignmentScore]:
        return self._alignment_scores[-limit:]

    def get_drift_events(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._drift_events[-limit:]
