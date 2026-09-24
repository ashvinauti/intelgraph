from dataclasses import dataclass


@dataclass
class ThresholdResult:
    needs_review: bool = False
    reason: str = ""
    suggested_action: str = ""


class ReviewThresholds:
    AUTO_APPROVE_MIN_CONFIDENCE: float = 90.0
    REVIEW_REQUIRED_MIN_CONFIDENCE: float = 70.0
    REVIEW_REQUIRED_SOURCE_COUNT: int = 1
    CONTESTED_FLAG_THRESHOLD: float = 50.0

    @staticmethod
    def evaluate(
        confidence: float,
        source_count: int,
        contradiction_score: float,
        single_source: bool | None = None,
    ) -> ThresholdResult:
        if single_source is None:
            single_source = source_count < 2
        if (
            confidence >= ReviewThresholds.AUTO_APPROVE_MIN_CONFIDENCE
            and source_count >= 2
            and not single_source
        ):
            return ThresholdResult(
                needs_review=False,
                reason="High confidence with multi-source corroboration",
                suggested_action="auto_approve",
            )

        if single_source:
            return ThresholdResult(
                needs_review=True,
                reason="Single-source chain needs corroboration",
                suggested_action="needs_more_evidence",
            )

        if contradiction_score >= ReviewThresholds.CONTESTED_FLAG_THRESHOLD:
            return ThresholdResult(
                needs_review=True,
                reason=f"High contradiction score ({contradiction_score:.1f})",
                suggested_action="needs_more_evidence",
            )

        if confidence >= ReviewThresholds.REVIEW_REQUIRED_MIN_CONFIDENCE:
            return ThresholdResult(
                needs_review=True,
                reason=f"Confidence {confidence:.1f} in review range ({ReviewThresholds.REVIEW_REQUIRED_MIN_CONFIDENCE}-{ReviewThresholds.AUTO_APPROVE_MIN_CONFIDENCE})",
                suggested_action="human_review",
            )

        return ThresholdResult(
            needs_review=True,
            reason=f"Low confidence ({confidence:.1f}), requires human evaluation",
            suggested_action="human_review",
        )
