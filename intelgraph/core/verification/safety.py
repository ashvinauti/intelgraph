from dataclasses import dataclass, field


@dataclass
class SafetyReport:
    flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return len(self.flags) == 0

    @property
    def severity(self) -> str:
        if not self.flags:
            return "NONE"
        if any("dominance" in f for f in self.flags):
            return "HIGH"
        if any("bias" in f for f in self.flags):
            return "MEDIUM"
        return "LOW"


class SafetyChecker:
    SOURCE_DOMINANCE_THRESHOLD: float = 0.60
    SINGLE_DOMAIN_BIAS_THRESHOLD: float = 0.50
    RAPID_CHANGE_WINDOW_HOURS: float = 24.0
    MAX_CONFIDENCE_CHANGE: float = 20.0

    @staticmethod
    def check_source_dominance(source_trust_scores: list[int]) -> list[str]:
        flags: list[str] = []
        if not source_trust_scores:
            return flags
        total = sum(source_trust_scores)
        if total > 0:
            for score in source_trust_scores:
                ratio = score / total
                if ratio > SafetyChecker.SOURCE_DOMINANCE_THRESHOLD:
                    flags.append(
                        f"source dominance: single source contributes {ratio:.0%} of trust weight"
                    )
        return flags

    @staticmethod
    def check_domain_bias(source_domains: list[str]) -> list[str]:
        flags: list[str] = []
        if len(source_domains) < 2:
            return flags
        from collections import Counter

        domain_counts: Counter[str] = Counter()
        for d in source_domains:
            parts = d.split("/")
            if len(parts) >= 3:
                domain_counts[parts[2]] += 1
            else:
                domain_counts[d] += 1
        total = sum(domain_counts.values())
        for domain, count in domain_counts.items():
            if count / total > SafetyChecker.SINGLE_DOMAIN_BIAS_THRESHOLD:
                flags.append(f"domain bias: {domain} represents {count / total:.0%} of sources")
        return flags

    @staticmethod
    def check_rapid_change(previous_confidence: float, new_confidence: float) -> list[str]:
        flags: list[str] = []
        if previous_confidence > 0:
            change = abs(new_confidence - previous_confidence)
            if change > SafetyChecker.MAX_CONFIDENCE_CHANGE:
                flags.append(
                    f"rapid change: confidence changed by {change:.1f} points "
                    f"({previous_confidence:.1f} -> {new_confidence:.1f})"
                )
        return flags

    @staticmethod
    def check_contradiction_for_confirmed(
        contradiction: float, verification_state: str
    ) -> list[str]:
        flags: list[str] = []
        if verification_state == "confirmed" and contradiction >= 20:
            flags.append(f"contradiction({contradiction:.1f}) should be resolved before CONFIRMED")
        return flags

    @staticmethod
    def full_check(
        source_trust_scores: list[int],
        source_domains: list[str],
        contradiction: float,
        verification_state: str,
        previous_confidence: float = 0.0,
        new_confidence: float = 0.0,
    ) -> SafetyReport:
        report = SafetyReport()
        report.flags.extend(SafetyChecker.check_source_dominance(source_trust_scores))
        report.flags.extend(SafetyChecker.check_domain_bias(source_domains))
        report.flags.extend(SafetyChecker.check_rapid_change(previous_confidence, new_confidence))
        report.flags.extend(
            SafetyChecker.check_contradiction_for_confirmed(contradiction, verification_state)
        )

        if report.flags:
            report.warnings = report.flags

        return report
