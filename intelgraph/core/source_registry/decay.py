from datetime import UTC, datetime
from typing import Any


class TrustDecayModel:
    HALF_LIFE_DAYS: dict[int, float] = {
        1: 90.0,
        2: 30.0,
        3: 7.0,
    }

    def __init__(self, half_life_override: dict[int, float] | None = None) -> None:
        if half_life_override:
            self._half_lives = {**self.HALF_LIFE_DAYS, **half_life_override}
        else:
            self._half_lives = dict(self.HALF_LIFE_DAYS)

    def decay_factor(self, source_tier: int, days_since_validation: float) -> float:
        if days_since_validation <= 0:
            return 1.0
        half_life = self._half_lives.get(source_tier, 30.0)
        return 2.0 ** (-days_since_validation / half_life)

    def apply_decay(self, source_record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        last_val = source_record.get("last_validated")
        if not last_val:
            return source_record

        try:
            last_dt = datetime.fromisoformat(last_val)
        except (ValueError, TypeError):
            return source_record

        days = (now - last_dt).total_seconds() / 86400.0
        if days <= 0:
            return source_record

        tier = source_record.get("source_tier", 3)
        factor = self.decay_factor(tier, days)
        original_trust = source_record.get(
            "_original_trust_score", source_record.get("trust_score", 0)
        )
        source_record["_original_trust_score"] = original_trust
        decayed = round(original_trust * factor)
        source_record["trust_score"] = max(0, min(100, decayed))
        source_record["decay_factor"] = round(factor, 4)
        source_record["days_since_validation"] = round(days, 1)
        return source_record

    def needs_revalidation(self, source_record: dict[str, Any]) -> bool:
        tier = source_record.get("source_tier", 3)
        half_life = self._half_lives.get(tier, 30.0)
        last_val = source_record.get("last_validated")
        if not last_val:
            return True
        try:
            last_dt = datetime.fromisoformat(str(last_val))
        except (ValueError, TypeError):
            return True
        days = (datetime.now(UTC) - last_dt).total_seconds() / 86400.0
        return days > half_life

    def effective_trust(self, source_record: dict[str, Any]) -> int:
        decayed = self.apply_decay(dict(source_record))
        return decayed.get("trust_score", 0)
