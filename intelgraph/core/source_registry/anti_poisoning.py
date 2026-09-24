from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class PoisoningFlag(Enum):
    LOW_TRUST_SOURCE = auto()
    SINGLE_SOURCE_DOMINANCE = auto()
    INSUFFICIENT_CORROBORATION = auto()
    SUSPICIOUS_PATTERN = auto()
    STALE_SOURCE = auto()


@dataclass
class PoisoningReport:
    flags: list[PoisoningFlag] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    @property
    def is_poisoned(self) -> bool:
        return len(self.flags) > 0

    @property
    def severity(self) -> str:
        if PoisoningFlag.SINGLE_SOURCE_DOMINANCE in self.flags:
            return "HIGH"
        if PoisoningFlag.LOW_TRUST_SOURCE in self.flags:
            return "MEDIUM"
        if self.flags:
            return "LOW"
        return "NONE"


class AntiPoisoningEngine:
    LOW_TRUST_THRESHOLD: int = 30
    SINGLE_SOURCE_THRESHOLD: float = 0.70
    MIN_CORROBORATION: int = 2

    def evaluate(
        self,
        source_records: list[dict[str, Any]],
        entity_trust_score: int | None = None,
    ) -> PoisoningReport:
        report = PoisoningReport()

        low_trust = [
            s for s in source_records if s.get("trust_score", 0) < self.LOW_TRUST_THRESHOLD
        ]
        for s in low_trust:
            report.flags.append(PoisoningFlag.LOW_TRUST_SOURCE)
            report.details.append(
                f"Low-trust source '{s.get('source_name', s.get('source_url', '?'))}' "
                f"(trust={s.get('trust_score', 0)})"
            )

        if source_records:
            max(s.get("trust_score", 0) for s in source_records)
            total_trust = sum(s.get("trust_score", 0) for s in source_records)
            if total_trust > 0:
                for s in source_records:
                    ratio = s.get("trust_score", 0) / total_trust
                    if ratio > self.SINGLE_SOURCE_THRESHOLD:
                        report.flags.append(PoisoningFlag.SINGLE_SOURCE_DOMINANCE)
                        report.details.append(
                            f"Single-source dominance: '{s.get('source_name', '?')}' "
                            f"contributes {ratio:.0%} of trust weight"
                        )

        if len(source_records) < self.MIN_CORROBORATION and entity_trust_score is not None:
            report.flags.append(PoisoningFlag.INSUFFICIENT_CORROBORATION)
            report.details.append(
                f"Only {len(source_records)} source(s); minimum {self.MIN_CORROBORATION} required"
            )

        return report

    def requires_multi_source(self, impact_level: str) -> bool:
        return impact_level in ("MEDIUM", "HIGH")

    def multi_source_confirm(self, source_records: list[dict[str, Any]]) -> bool:
        return len(source_records) >= self.MIN_CORROBORATION
