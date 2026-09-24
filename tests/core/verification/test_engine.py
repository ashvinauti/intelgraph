from intelgraph.core.verification.base import OperationalState, VerificationState
from intelgraph.core.verification.engine import VerificationEngine


def test_engine_initial_state():
    result = VerificationEngine.compute(
        confidence=0.0,
        consensus=0.0,
        contradiction=0.0,
        source_count=0,
        source_trust_scores=[],
    )
    assert result.verification_state == VerificationState.SPECULATIVE
    assert result.operational_state == OperationalState.ACTIVE
    assert "confidence" in result.reasoning


def test_engine_confirmed_all_criteria():
    result = VerificationEngine.compute(
        confidence=95.0,
        consensus=95.0,
        contradiction=5.0,
        source_count=5,
        source_trust_scores=[85, 90, 88, 92, 87],
    )
    assert result.verification_state == VerificationState.CONFIRMED
    assert result.operational_state == OperationalState.ACTIVE
    assert any("CONFIRMED" in r for r in result.matched_rules)


def test_engine_confirmed_exact_threshold():
    result = VerificationEngine.compute(
        confidence=90.0,
        consensus=90.0,
        contradiction=19.0,
        source_count=3,
        source_trust_scores=[80, 85, 90],
    )
    assert result.verification_state == VerificationState.CONFIRMED


def test_engine_probable_two_sources():
    result = VerificationEngine.compute(
        confidence=75.0,
        consensus=72.0,
        contradiction=25.0,
        source_count=2,
        source_trust_scores=[70, 80],
    )
    assert result.verification_state == VerificationState.PROBABLE


def test_engine_probable_single_high_trust():
    result = VerificationEngine.compute(
        confidence=80.0,
        consensus=75.0,
        contradiction=15.0,
        source_count=1,
        source_trust_scores=[95],
    )
    assert result.verification_state == VerificationState.PROBABLE


def test_engine_possible():
    result = VerificationEngine.compute(
        confidence=55.0,
        consensus=50.0,
        contradiction=30.0,
        source_count=1,
        source_trust_scores=[60],
    )
    assert result.verification_state == VerificationState.POSSIBLE


def test_engine_speculative_low_confidence():
    result = VerificationEngine.compute(
        confidence=30.0,
        consensus=40.0,
        contradiction=10.0,
        source_count=1,
        source_trust_scores=[40],
    )
    assert result.verification_state == VerificationState.SPECULATIVE


def test_engine_speculative_high_contradiction():
    result = VerificationEngine.compute(
        confidence=80.0,
        consensus=75.0,
        contradiction=65.0,
        source_count=3,
        source_trust_scores=[70, 80, 75],
    )
    assert result.verification_state == VerificationState.SPECULATIVE


def test_engine_contested():
    result = VerificationEngine.compute(
        confidence=50.0,
        consensus=50.0,
        contradiction=75.0,
        source_count=3,
        source_trust_scores=[60, 55, 70],
    )
    assert result.operational_state == OperationalState.CONTESTED


def test_engine_debunked():
    result = VerificationEngine.compute(
        confidence=10.0,
        consensus=10.0,
        contradiction=95.0,
        source_count=5,
        source_trust_scores=[20, 15, 10, 5, 30],
    )
    assert result.operational_state == OperationalState.DEBUNKED


def test_engine_human_review_boost():
    result = VerificationEngine.compute(
        confidence=85.0,
        consensus=95.0,
        contradiction=5.0,
        source_count=3,
        source_trust_scores=[80, 85, 90],
        human_review_boost=10.0,
    )
    assert result.verification_state == VerificationState.CONFIRMED


def test_engine_high_impact_not_confirmed():
    result = VerificationEngine.compute(
        confidence=85.0,
        consensus=85.0,
        contradiction=10.0,
        source_count=3,
        source_trust_scores=[80, 80, 85],
        is_high_impact=True,
    )
    assert result.verification_state == VerificationState.PROBABLE
    assert any("high-impact" in r for r in result.matched_rules)


def test_engine_high_impact_confirmed():
    result = VerificationEngine.compute(
        confidence=95.0,
        consensus=95.0,
        contradiction=5.0,
        source_count=5,
        source_trust_scores=[90, 90, 90, 90, 90],
        is_high_impact=True,
    )
    assert result.verification_state == VerificationState.CONFIRMED


def test_engine_confidence_capped():
    result = VerificationEngine.compute(
        confidence=200.0,
        consensus=95.0,
        contradiction=5.0,
        source_count=3,
        source_trust_scores=[85, 90, 88],
    )
    assert result.verification_state == VerificationState.CONFIRMED


def test_engine_consensus_capped():
    result = VerificationEngine.compute(
        confidence=95.0,
        consensus=-10.0,
        contradiction=5.0,
        source_count=3,
        source_trust_scores=[85, 90, 88],
    )
    # consensus capped to 0, below 50 threshold → SPECULATIVE
    assert result.verification_state == VerificationState.SPECULATIVE


def test_engine_result_to_dict():
    result = VerificationEngine.compute(
        confidence=95.0,
        consensus=95.0,
        contradiction=5.0,
        source_count=3,
        source_trust_scores=[85, 90, 88],
    )
    d = result.to_dict()
    assert d["verification_state"] == "confirmed"
    assert d["operational_state"] == "active"
    assert isinstance(d["matched_rules"], list)
    assert isinstance(d["reasoning"], str)
    assert isinstance(d["computation_steps"], list)
