from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class ResolutionAudit:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def record(
        self,
        source_id: str,
        target_id: str,
        strategy: str,
        fields_merged: list[str],
        confidence: float,
        source_attribution: str | None = None,
    ) -> dict[str, Any]:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "merge_strategy": strategy,
            "fields_merged": fields_merged,
            "confidence": confidence,
            "source_attribution": source_attribution or "",
        }
        self._entries.append(entry)
        return entry

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._entries[-limit:]

    def clear(self) -> None:
        self._entries.clear()


class EntityMatcher:
    def __init__(self, match_threshold: float = 0.7, exact_fields: list[str] | None = None) -> None:
        self._threshold = match_threshold
        self._exact_fields = exact_fields or ["id", "email", "domain_name"]

    def _normalize(self, value: Any) -> str:
        return str(value).lower().strip().replace("-", "").replace("_", "").replace(".", "")

    def _exact_match(self, a: dict[str, Any], b: dict[str, Any]) -> bool:
        for field in self._exact_fields:
            va = self._normalize(a.get(field, ""))
            vb = self._normalize(b.get(field, ""))
            if va and vb and va == vb:
                return True
        return False

    def _name_similarity(self, a: str, b: str) -> float:
        na = self._normalize(a)
        nb = self._normalize(b)
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0
        if len(na) < 3 or len(nb) < 3:
            return 0.0
        longer = na if len(na) > len(nb) else nb
        shorter = nb if len(na) > len(nb) else na
        if shorter in longer:
            return 0.8
        common = sum(1 for c in shorter if c in longer)
        return common / len(longer)

    def match(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        if self._exact_match(a, b):
            return 1.0
        name_a = str(a.get("name", a.get("label", "")))
        name_b = str(b.get("name", b.get("label", "")))
        sim = self._name_similarity(name_a, name_b)
        if sim >= self._threshold:
            return sim
        return 0.0

    def find_duplicates(
        self,
        entries: list[dict[str, Any]],
        existing: list[dict[str, Any]] | None = None,
    ) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
        candidates: list[dict[str, Any]] = list(existing) if existing else []
        candidates.extend(entries)
        duplicates: list[tuple[dict[str, Any], dict[str, Any], float]] = []
        seen = set()
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                key = (i, j)
                if key in seen:
                    continue
                score = self.match(candidates[i], candidates[j])
                if score >= self._threshold:
                    seen.add(key)
                    duplicates.append((candidates[i], candidates[j], score))
        return duplicates


class MergeEngine:
    STRATEGIES = frozenset({"priority", "newest", "most_confident", "keep_source", "keep_target"})

    def __init__(self, default_strategy: str = "priority") -> None:
        if default_strategy not in self.STRATEGIES:
            raise ValueError(
                f"Unknown strategy: {default_strategy}. Use one of: {', '.join(sorted(self.STRATEGIES))}"
            )
        self._default_strategy = default_strategy
        self._audit = ResolutionAudit()

    @property
    def audit(self) -> ResolutionAudit:
        return self._audit

    def merge(
        self,
        source: dict[str, Any],
        target: dict[str, Any],
        strategy: str | None = None,
        priority_fields: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        strategy = strategy or self._default_strategy
        if strategy == "keep_source":
            return dict(source)
        if strategy == "keep_target":
            return dict(target)

        if strategy == "newest":
            t_src = source.get("created_at", source.get("updated_at", ""))
            t_tgt = target.get("created_at", target.get("updated_at", ""))
            base = target if t_tgt >= t_src else source
            other = source if t_tgt >= t_src else target
        elif strategy == "most_confident":
            cs_src = source.get("confidence_score", 0)
            cs_tgt = target.get("confidence_score", 0)
            base = target if cs_tgt >= cs_src else source
            other = source if cs_tgt >= cs_src else target
        else:
            base = target
            other = source

        merged = dict(base)
        fields_merged: list[str] = []
        priority = priority_fields or {}

        for key, val in other.items():
            if key not in merged or merged[key] is None or str(merged[key]).strip() == "":
                merged[key] = val
                fields_merged.append(key)
            elif key in priority:
                if priority[key] == "other":
                    merged[key] = val
                    fields_merged.append(key)
            elif key == "id":
                pass
            elif key in ("confidence_score", "trust_score", "trust_weight"):
                merged[key] = max(int(merged.get(key, 0) or 0), int(val or 0))
                fields_merged.append(key)

        self._audit.record(
            source_id=source.get("id", ""),
            target_id=target.get("id", ""),
            strategy=strategy,
            fields_merged=fields_merged,
            confidence=0.95,
        )
        return merged
