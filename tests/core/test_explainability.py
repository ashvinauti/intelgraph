from __future__ import annotations

import pytest

from intelgraph.core.explainability.interpreter import (
    CounterfactualExplainer,
    FeatureContribution,
    FeatureImportance,
    ModelInterpreter,
    PredictionExplanation,
)
from intelgraph.core.governance.policy import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalWorkflow,
    AuditTrail,
    ComplianceChecker,
    ComplianceStatus,
    PolicyEvaluator,
)
from intelgraph.core.safety.guard import (
    BoundsChecker,
    ConstraintValidator,
    FallbackHandler,
    SafetyGuard,
    SafetyReport,
    SafetyViolation,
    Severity,
)

# ===================================================================
# Explainability Tests
# ===================================================================


class TestFeatureContribution:
    def test_creation(self) -> None:
        fc = FeatureContribution("risk", 0.5, 0.3, "positive", 0.8)
        assert fc.feature_name == "risk"
        assert fc.contribution == 0.3

    def test_to_dict(self) -> None:
        fc = FeatureContribution("risk", 0.5, 0.3, "positive", 0.8)
        d = fc.to_dict()
        assert d["feature_name"] == "risk"
        assert d["direction"] == "positive"


class TestPredictionExplanation:
    def test_creation(self) -> None:
        fc = FeatureContribution("risk", 0.5, 0.3, "positive", 0.8)
        pe = PredictionExplanation("exp1", "A", "risk_forecast", [fc], "test", 0.9, 0.1, 0.85)
        assert pe.explanation_id == "exp1"
        assert len(pe.top_contributions) == 1

    def test_to_dict(self) -> None:
        fc = FeatureContribution("risk", 0.5, 0.3, "positive", 0.8)
        pe = PredictionExplanation("exp1", "A", "risk_forecast", [fc], "test", 0.9, 0.1, 0.85)
        d = pe.to_dict()
        assert d["summary"] == "test"
        assert d["model_fidelity"] == 0.85


class TestFeatureImportance:
    def test_compute_importance(self) -> None:
        fi = FeatureImportance()
        features = {"risk": 0.8, "influence": 0.5, "anomaly": 0.3, "degree": 0.1}
        contributions = {"risk": 0.6, "influence": 0.3, "anomaly": -0.1, "degree": 0.05}
        result = fi.compute_importance(features, contributions, top_n=3)
        assert len(result) == 3
        assert result[0].feature_name == "risk"
        assert result[0].direction == "positive"

    def test_empty_contributions(self) -> None:
        fi = FeatureImportance()
        assert fi.compute_importance({}, {}) == []

    def test_negative_contributions(self) -> None:
        fi = FeatureImportance()
        features = {"a": 0.5, "b": 0.5}
        contributions = {"a": -0.8, "b": 0.2}
        result = fi.compute_importance(features, contributions, top_n=2)
        assert result[0].feature_name == "a"
        assert result[0].direction == "negative"

    def test_global_importance(self) -> None:
        fi = FeatureImportance()
        preds = [
            {"contributions": {"risk": 0.5, "influence": 0.3}},
            {"contributions": {"risk": 0.4, "anomaly": 0.2}},
        ]
        result = fi.global_importance(preds, top_n=5)
        assert result["risk"] == pytest.approx(0.9)
        assert len(result) == 3


class TestModelInterpreter:
    def test_empty_report(self) -> None:
        mi = ModelInterpreter()
        report = mi.generate_report("test_model", [])
        assert report.prediction_count == 0
        assert report.average_confidence == 0.0

    def test_generate_report(self) -> None:
        mi = ModelInterpreter()
        predictions = [
            {"confidence": 0.9, "uncertainty": 0.1, "contributions": {"risk": 0.5}},
            {"confidence": 0.8, "uncertainty": 0.2, "contributions": {"influence": 0.3}},
        ]
        report = mi.generate_report("test_model", predictions)
        assert report.prediction_count == 2
        assert report.average_confidence == pytest.approx(0.85)
        assert report.average_uncertainty == pytest.approx(0.15)

    def test_feature_stability(self) -> None:
        mi = ModelInterpreter()
        preds = [
            {
                "confidence": 0.9,
                "uncertainty": 0.1,
                "contributions": {"risk": 0.5, "influence": 0.5},
            },
            {
                "confidence": 0.8,
                "uncertainty": 0.2,
                "contributions": {"risk": 0.5, "influence": 0.5},
            },
        ]
        report = mi.generate_report("m", preds)
        assert report.feature_stability["risk"] == pytest.approx(1.0, rel=1e-3)


class TestCounterfactualExplainer:
    def test_minimal_change(self) -> None:
        ce = CounterfactualExplainer()
        features = {"risk": 0.3, "influence": 0.5, "anomaly": 0.2}
        result = ce.minimal_change(features, 0.8, 0.5)
        assert len(result) > 0
        assert "feature" in result[0]
        assert "suggested_value" in result[0]

    def test_already_at_target(self) -> None:
        ce = CounterfactualExplainer()
        result = ce.minimal_change({"risk": 0.5}, 0.5, 0.5)
        assert result[0]["message"] == "already at target"

    def test_empty_features(self) -> None:
        ce = CounterfactualExplainer()
        assert ce.minimal_change({}, 0.8, 0.5) == []

    def test_what_if_summary(self) -> None:
        ce = CounterfactualExplainer()
        summary = ce.what_if_summary("risk", 0.5, 0.8, 0.6, 0.9)
        assert summary["feature"] == "risk"
        assert summary["impact"] == 0.3
        assert summary["impact_direction"] == "increase"


# ===================================================================
# Safety Tests
# ===================================================================


class TestSeverity:
    def test_values(self) -> None:
        assert Severity.INFO.name == "INFO"
        assert Severity.WARNING.name == "WARNING"
        assert Severity.ERROR.name == "ERROR"
        assert Severity.CRITICAL.name == "CRITICAL"


class TestSafetyViolation:
    def test_creation(self) -> None:
        sv = SafetyViolation("test_rule", Severity.WARNING, "test msg", 0.9, 0.8)
        assert sv.rule_name == "test_rule"
        assert sv.severity == Severity.WARNING

    def test_to_dict(self) -> None:
        sv = SafetyViolation("test_rule", Severity.WARNING, "test msg", 0.9, 0.8)
        d = sv.to_dict()
        assert d["rule_name"] == "test_rule"
        assert d["severity"] == "warning"


class TestSafetyReport:
    def test_passed(self) -> None:
        sr = SafetyReport("sr1", passed=True, violations=[], fallback_used=False)
        assert sr.passed is True

    def test_failed(self) -> None:
        v = SafetyViolation("r", Severity.ERROR, "msg", 0.9, 0.8)
        sr = SafetyReport(
            "sr1", passed=False, violations=[v], fallback_used=True, fallback_value=0.5
        )
        assert sr.passed is False
        assert sr.fallback_value == 0.5

    def test_to_dict(self) -> None:
        sr = SafetyReport("sr1", passed=True, violations=[], fallback_used=False)
        d = sr.to_dict()
        assert d["passed"] is True


class TestConstraintValidator:
    def test_no_constraint(self) -> None:
        cv = ConstraintValidator()
        assert cv.validate("risk", 0.5) is None

    def test_below_min(self) -> None:
        cv = ConstraintValidator({"risk": {"min": 0.1, "max": 1.0}})
        v = cv.validate("risk", 0.0)
        assert v is not None
        assert "below" in v.message

    def test_above_max(self) -> None:
        cv = ConstraintValidator({"risk": {"min": 0.0, "max": 0.8}})
        v = cv.validate("risk", 0.9)
        assert v is not None
        assert "above" in v.message

    def test_within_bounds(self) -> None:
        cv = ConstraintValidator({"risk": {"min": 0.0, "max": 1.0}})
        assert cv.validate("risk", 0.5) is None

    def test_set_constraint(self) -> None:
        cv = ConstraintValidator()
        cv.set_constraint("test", 0.0, 0.5)
        assert cv.validate("test", 0.6) is not None


class TestBoundsChecker:
    def test_default_bounds(self) -> None:
        bc = BoundsChecker()
        assert bc.check("any", 0.5) is None
        assert bc.check("any", -0.1) is not None
        assert bc.check("any", 1.1) is not None

    def test_per_type_bounds(self) -> None:
        bc = BoundsChecker()
        bc.set_bounds("risk", 0.0, 0.9)
        assert bc.check("risk", 0.95) is not None
        assert bc.check("risk", 0.5) is None
        assert bc.check("trend", 0.95) is None  # uses global

    def test_violation_details(self) -> None:
        bc = BoundsChecker(0.0, 0.8)
        v = bc.check("test", 0.9)
        assert v is not None
        assert v.rule_name == "bounds_test_max"


class TestFallbackHandler:
    def test_no_fallback(self) -> None:
        fh = FallbackHandler()
        val, used = fh.apply("risk", 0.5)
        assert val == 0.5
        assert used is False

    def test_infinity_handling(self) -> None:
        fh = FallbackHandler(default_value=0.0)
        val, used = fh.apply("risk", float("inf"))
        assert val == 0.0
        assert used is True

    def test_nan_handling(self) -> None:
        fh = FallbackHandler(default_value=0.0)
        val, used = fh.apply("risk", float("nan"))
        assert val == 0.0
        assert used is True

    def test_type_fallback(self) -> None:
        fh = FallbackHandler()
        fh.set_fallback("risk", 0.8)
        val, used = fh.apply("risk", 0.9)
        assert val == 0.8
        assert used is True


class TestSafetyGuard:
    def test_passes_no_violations(self) -> None:
        guard = SafetyGuard()
        report = guard.check_prediction("risk_forecast", 0.5)
        assert report.passed is True
        assert report.fallback_used is False

    def test_bounds_violation(self) -> None:
        guard = SafetyGuard(bounds={"risk_forecast": (0.0, 0.8)})
        report = guard.check_prediction("risk_forecast", 0.9)
        assert report.passed is False
        assert len(report.violations) == 1

    def test_fallback_on_inf(self) -> None:
        guard = SafetyGuard(fallbacks={"risk_forecast": 0.5})
        report = guard.check_prediction("risk_forecast", float("inf"))
        assert report.fallback_used is True
        assert report.fallback_value == 0.5

    def test_extra_constraints(self) -> None:
        guard = SafetyGuard(constraints={"confidence": {"min": 0.5, "max": 1.0}})
        report = guard.check_prediction("risk_forecast", 0.5, extra_constraints={"confidence": 0.3})
        assert report.passed is False
        assert len(report.violations) == 1

    def test_callback_invocation(self) -> None:
        cb_results: list[SafetyReport] = []
        guard = SafetyGuard(callbacks=[lambda r: cb_results.append(r)])
        guard.check_prediction("risk_forecast", 0.5)
        assert len(cb_results) == 1

    def test_add_callback(self) -> None:
        cb_results: list[SafetyReport] = []
        guard = SafetyGuard()
        guard.add_callback(lambda r: cb_results.append(r))
        guard.check_prediction("risk_forecast", 0.5)
        assert len(cb_results) == 1


# ===================================================================
# Governance Tests
# ===================================================================


class TestAuditTrail:
    def test_record(self) -> None:
        trail = AuditTrail()
        entry = trail.record("predict", "A", "risk", 0.5)
        assert entry.action == "predict"
        assert entry.entity_id == "A"

    def test_query_by_entity(self) -> None:
        trail = AuditTrail()
        trail.record("predict", "A", "risk", 0.5)
        trail.record("predict", "B", "risk", 0.6)
        results = trail.query(entity_id="A")
        assert len(results) == 1

    def test_query_by_action(self) -> None:
        trail = AuditTrail()
        trail.record("predict", "A", "risk", 0.5)
        trail.record("explain", "A", "risk", 0.5)
        results = trail.query(action="predict")
        assert len(results) == 1

    def test_query_limit(self) -> None:
        trail = AuditTrail(max_entries=100)
        for i in range(10):
            trail.record("predict", "A", "risk", float(i) / 10)
        results = trail.query(limit=3)
        assert len(results) == 3

    def test_summary(self) -> None:
        trail = AuditTrail()
        trail.record("predict", "A", "risk", 0.5)
        trail.record("predict", "B", "risk", 0.6)
        trail.record("explain", "A", "risk", 0.5)
        s = trail.summary()
        assert s["total_entries"] == 3
        assert s["action_counts"]["predict"] == 2


class TestComplianceChecker:
    def test_no_rules(self) -> None:
        cc = ComplianceChecker()
        report = cc.check("risk_forecast", 0.5)
        assert report.status == ComplianceStatus.COMPLIANT

    def test_max_value_violation(self) -> None:
        cc = ComplianceChecker(
            {"max_risk": {"type": "max_value", "threshold": 0.7, "enabled": True}}
        )
        report = cc.check("risk_forecast", 0.9)
        assert report.status == ComplianceStatus.NON_COMPLIANT
        assert len(report.violations) == 1

    def test_min_value_violation(self) -> None:
        cc = ComplianceChecker(
            {"min_risk": {"type": "min_value", "threshold": 0.3, "enabled": True}}
        )
        report = cc.check("risk_forecast", 0.1)
        assert report.status == ComplianceStatus.NON_COMPLIANT

    def test_risk_based_violation(self) -> None:
        cc = ComplianceChecker(
            {"entity_risk": {"type": "risk_based", "threshold": 0.7, "enabled": True}}
        )
        report = cc.check("risk_forecast", 0.5, entity_risk=0.9)
        assert report.status == ComplianceStatus.NON_COMPLIANT

    def test_skipped_type(self) -> None:
        cc = ComplianceChecker(
            {
                "rule1": {
                    "type": "max_value",
                    "threshold": 0.7,
                    "prediction_types": ["trend"],
                    "enabled": True,
                },
            }
        )
        report = cc.check("risk_forecast", 0.9)
        assert report.status == ComplianceStatus.COMPLIANT
        assert "rule1" in report.passed_rules

    def test_disabled_rule(self) -> None:
        cc = ComplianceChecker(
            {
                "rule1": {"type": "max_value", "threshold": 0.7, "enabled": False},
            }
        )
        report = cc.check("risk_forecast", 0.9)
        assert report.status == ComplianceStatus.COMPLIANT

    def test_add_rule(self) -> None:
        cc = ComplianceChecker()
        cc.add_rule("new_rule", {"type": "max_value", "threshold": 0.5, "enabled": True})
        report = cc.check("risk_forecast", 0.9)
        assert report.status == ComplianceStatus.NON_COMPLIANT

    def test_report_serialization(self) -> None:
        cc = ComplianceChecker({"r": {"type": "max_value", "threshold": 0.5, "enabled": True}})
        report = cc.check("risk_forecast", 0.9)
        d = report.to_dict()
        assert d["status"] == "non_compliant"
        assert len(d["violations"]) == 1
        assert "r" in d["passed_rules"] or len(d["passed_rules"]) == 0


class TestApprovalWorkflow:
    def test_low_risk_auto_approve(self) -> None:
        wf = ApprovalWorkflow(risk_threshold=0.7)
        req = wf.request_approval("risk_forecast", "A", 0.5, 0.3)
        assert req.status == ApprovalStatus.APPROVED

    def test_high_risk_pending(self) -> None:
        wf = ApprovalWorkflow(risk_threshold=0.7)
        req = wf.request_approval("risk_forecast", "A", 0.9, 0.9)
        assert req.status == ApprovalStatus.PENDING

    def test_review_approve(self) -> None:
        wf = ApprovalWorkflow(risk_threshold=0.0)
        req = wf.request_approval("risk_forecast", "A", 0.9, 0.9)
        assert wf.review(req.request_id, approved=True, reviewer="admin") is True
        assert req.status == ApprovalStatus.APPROVED

    def test_review_reject(self) -> None:
        wf = ApprovalWorkflow(risk_threshold=0.0)
        req = wf.request_approval("risk_forecast", "A", 0.9, 0.9)
        assert wf.review(req.request_id, approved=False, reviewer="admin") is True
        assert req.status == ApprovalStatus.REJECTED

    def test_escalate(self) -> None:
        wf = ApprovalWorkflow(risk_threshold=0.0)
        req = wf.request_approval("risk_forecast", "A", 0.9, 0.9)
        assert wf.escalate(req.request_id) is True
        assert req.status == ApprovalStatus.ESCALATED

    def test_list_pending(self) -> None:
        wf = ApprovalWorkflow(risk_threshold=0.0)
        wf.request_approval("risk_forecast", "A", 0.9, 0.9)
        wf.request_approval("risk_forecast", "B", 0.5, 0.3)
        pending = wf.list_pending()
        assert len(pending) == 2

    def test_get_request(self) -> None:
        wf = ApprovalWorkflow()
        req = wf.request_approval("risk_forecast", "A", 0.5, 0.3)
        assert wf.get_request(req.request_id) is req

    def test_callback(self) -> None:
        cb_results: list[ApprovalRequest] = []
        wf = ApprovalWorkflow()
        wf.add_callback(lambda r: cb_results.append(r))
        wf.request_approval("risk_forecast", "A", 0.5, 0.3)
        assert len(cb_results) == 1


class TestPolicyEvaluator:
    def test_evaluate_pass(self) -> None:
        pe = PolicyEvaluator()
        pe.add_policy("max_risk", lambda value, **kw: value < 0.8)
        results = pe.evaluate({"value": 0.5})
        assert results["max_risk"] is True

    def test_evaluate_fail(self) -> None:
        pe = PolicyEvaluator()
        pe.add_policy("max_risk", lambda value, **kw: value < 0.8)
        results = pe.evaluate({"value": 0.9})
        assert results["max_risk"] is False

    def test_all_pass(self) -> None:
        pe = PolicyEvaluator()
        pe.add_policy("p1", lambda value, **kw: value > 0)
        pe.add_policy("p2", lambda value, **kw: value < 1)
        assert pe.all_pass({"value": 0.5}) is True
        assert pe.all_pass({"value": 1.5}) is False

    def test_error_handling(self) -> None:
        pe = PolicyEvaluator()
        pe.add_policy("bad", lambda: (_ for _ in ()).throw(ValueError("fail")))
        results = pe.evaluate({})
        assert results["bad"] is False
