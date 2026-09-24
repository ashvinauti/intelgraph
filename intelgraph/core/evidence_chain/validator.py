from dataclasses import dataclass, field

from intelgraph.core.evidence_chain.base import EvidenceChain, EvidenceItem, EvidenceStatus


@dataclass
class ValidationReport:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


class ChainValidator:
    MIN_SOURCE_TRUST: int = 20
    MIN_CHAIN_CONFIDENCE: float = 10.0
    MIN_DOCUMENT_LENGTH: int = 1
    MIN_CLAIM_LENGTH: int = 1

    def validate(self, chain: EvidenceChain) -> ValidationReport:
        report = ValidationReport()

        if not chain.entity_id:
            report.is_valid = False
            report.errors.append("entity_id is empty")

        if not chain.evidence:
            report.is_valid = False
            report.errors.append("evidence list is empty")

        seen_ids: set[str] = set()
        for item in chain.evidence:
            item_errors = self._validate_item(item, seen_ids)
            if item_errors:
                report.errors.extend(item_errors)
                report.is_valid = False
            seen_ids.add(item.evidence_id)

        quality_flags = self._quality_flags(chain)
        report.quality_flags.extend(quality_flags)

        if quality_flags:
            report.warnings.extend(quality_flags)

        return report

    def _validate_item(self, item: EvidenceItem, seen_ids: set[str]) -> list[str]:
        errors: list[str] = []

        if not item.source_id:
            errors.append(f"evidence_item {item.evidence_id}: source_id is empty")
        if not item.document_id:
            errors.append(f"evidence_item {item.evidence_id}: document_id is empty")
        if not item.claim:
            errors.append(f"evidence_item {item.evidence_id}: claim is empty")
        if len(item.claim) < self.MIN_CLAIM_LENGTH:
            errors.append(f"evidence_item {item.evidence_id}: claim too short")
        if item.evidence_id in seen_ids:
            errors.append(f"evidence_item {item.evidence_id}: duplicate evidence_id")
        if not 0.0 <= item.confidence <= 100.0:
            errors.append(
                f"evidence_item {item.evidence_id}: confidence {item.confidence} out of range"
            )

        return errors

    def _quality_flags(self, chain: EvidenceChain) -> list[str]:
        flags: list[str] = []

        if chain.source_count < 2:
            flags.append("needs_corroboration: single-source chain")

        if chain.confidence < self.MIN_CHAIN_CONFIDENCE:
            flags.append("low_confidence: chain confidence below threshold")

        if chain.contradiction_score >= 50:
            flags.append("high_contradiction: chain has significant conflicts")

        if chain.status == EvidenceStatus.CONTESTED:
            flags.append("contested: chain has more contradictions than supports")

        return flags
