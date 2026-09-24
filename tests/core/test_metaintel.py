from __future__ import annotations

import uuid

# ===================================================================
# Global Governance Engine Tests
# ===================================================================


class TestGlobalGovernanceEngine:
    def test_initial_health(self):
        from intelgraph.core.metaintel.governance import GlobalGovernanceEngine

        gov = GlobalGovernanceEngine()
        health = gov.get_system_health()
        assert health["overall_health_score"] > 0
        assert len(health["layers"]) == 5

    def test_record_layer_health(self):
        from intelgraph.core.metaintel.governance import GlobalGovernanceEngine, SystemHealth

        gov = GlobalGovernanceEngine()
        gov.record_layer_health("nlp", SystemHealth.DEGRADED, 0.4, [{"type": "test"}])
        health = gov.get_system_health()
        assert health["layers"]["nlp"]["health"] == "degraded"

    def test_detect_system_anomalies(self):
        from intelgraph.core.metaintel.governance import GlobalGovernanceEngine, SystemHealth

        gov = GlobalGovernanceEngine()
        gov.record_layer_health("nlp", SystemHealth.CRITICAL, 0.2)
        anomalies = gov.detect_system_anomalies()
        assert len(anomalies) >= 1

    def test_enforce_global_policy_allows(self):
        from intelgraph.core.metaintel.governance import GlobalGovernanceEngine

        gov = GlobalGovernanceEngine()
        result = gov.enforce_global_policy({"type": "read", "risk": 0.3, "layers": ["nlp"]})
        assert result["allowed"]

    def test_enforce_global_policy_blocks_high_risk(self):
        from intelgraph.core.metaintel.governance import GlobalGovernanceEngine

        gov = GlobalGovernanceEngine()
        result = gov.enforce_global_policy({"type": "delete", "risk": 0.9, "layers": ["execution"]})
        assert not result["allowed"]

    def test_set_and_get_global_state(self):
        from intelgraph.core.metaintel.governance import GlobalGovernanceEngine

        gov = GlobalGovernanceEngine()
        gov.set_global_state("mode", "active")
        assert gov.get_global_state("mode") == "active"

    def test_resolve_conflict(self):
        from intelgraph.core.metaintel.governance import GlobalGovernanceEngine

        gov = GlobalGovernanceEngine()
        # Add a conflict directly
        gov._conflicts.append({"conflict_id": "c1", "type": "test"})
        assert gov.resolve_conflict("c1", "override")


# ===================================================================
# System Diagnostics Tests
# ===================================================================


class TestSystemDiagnostics:
    def test_run_diagnostics(self):
        from intelgraph.core.metaintel.diagnostics import SystemDiagnostics

        diag = SystemDiagnostics()
        report = diag.run_diagnostics("nlp", {"latency_ms": 500, "error_rate": 0.05})
        assert report.pipeline_stage == "nlp"
        assert 0.0 <= report.health_score <= 1.0

    def test_drift_detection(self):
        from intelgraph.core.metaintel.diagnostics import SystemDiagnostics

        diag = SystemDiagnostics()
        diag.run_diagnostics("test", {"value": 1.0})
        diag.run_diagnostics("test", {"value": 5.0})
        report = diag.run_diagnostics("test", {"value": 5.0})
        assert report.drift_scores.get("value", 0) > 0

    def test_bottleneck_detection(self):
        from intelgraph.core.metaintel.diagnostics import SystemDiagnostics

        diag = SystemDiagnostics()
        report = diag.run_diagnostics("test", {"latency_ms": 2000, "error_rate": 0.2})
        assert len(report.bottlenecks) > 0

    def test_regression_detection(self):
        from intelgraph.core.metaintel.diagnostics import SystemDiagnostics

        diag = SystemDiagnostics()
        diag.run_diagnostics("test", {"accuracy": 0.9})
        report = diag.run_diagnostics("test", {"accuracy": 0.5})
        assert len(report.regression_flags) > 0

    def test_cross_phase_correlate(self):
        from intelgraph.core.metaintel.diagnostics import SystemDiagnostics

        diag = SystemDiagnostics()
        result = diag.cross_phase_correlate([{"event": "e1"}, {"event": "e2"}])
        assert len(result) == 2


# ===================================================================
# Policy Evolution Engine Tests
# ===================================================================


class TestPolicyEvolutionEngine:
    def test_generate_policy(self):
        from intelgraph.core.metaintel.policy import PolicyEvolutionEngine

        engine = PolicyEvolutionEngine()
        record = engine.generate_policy(
            "test_policy", "test", [{"action": "block", "condition": "risk > 0.7"}]
        )
        assert record.name == "test_policy"
        assert record.status == "active"

    def test_version_increment(self):
        from intelgraph.core.metaintel.policy import PolicyEvolutionEngine

        engine = PolicyEvolutionEngine()
        p1 = engine.generate_policy("vtest", "v1", [])
        p2 = engine.generate_policy("vtest", "v2", [])
        assert p2.version == p1.version + 1

    def test_refine_from_failures(self):
        from intelgraph.core.metaintel.policy import PolicyEvolutionEngine

        engine = PolicyEvolutionEngine()
        base = engine.generate_policy("base", "base", [])
        engine.record_failure("timeout", {})
        engine.record_failure("timeout", {})
        engine.record_failure("timeout", {})
        engine.record_failure("timeout", {})
        engine.record_failure("timeout", {})
        engine.record_failure("timeout", {})
        refined = engine.refine_from_failures(base.policy_id)
        assert refined is not None
        assert len(refined.rules) > 0

    def test_enforce_allows(self):
        from intelgraph.core.metaintel.policy import PolicyEvolutionEngine

        engine = PolicyEvolutionEngine()
        engine.generate_policy("default", "", [])
        result = engine.enforce({"type": "read", "risk": 0.3})
        assert result["allowed"]

    def test_simulate_policy(self):
        from intelgraph.core.metaintel.policy import PolicyEvolutionEngine

        engine = PolicyEvolutionEngine()
        record = engine.generate_policy(
            "sim_test", "", [{"action": "block", "condition": "risk > 0.7"}]
        )
        result = engine.simulate_policy(record.policy_id, [{"risk": 0.8}, {"risk": 0.3}])
        assert result["blocked"] == 1
        assert result["allowed"] == 1

    def test_a_b_test(self):
        from intelgraph.core.metaintel.policy import PolicyEvolutionEngine

        engine = PolicyEvolutionEngine()
        a = engine.generate_policy("A", "", [])
        b = engine.generate_policy("B", "", [])
        result = engine.a_b_test(a.policy_id, b.policy_id, [{"risk": 0.5}])
        assert "test_id" in result

    def test_deprecate_policy(self):
        from intelgraph.core.metaintel.policy import PolicyEvolutionEngine

        engine = PolicyEvolutionEngine()
        record = engine.generate_policy("dep_test", "", [])
        assert engine.deprecate_policy(record.policy_id)
        assert record.status == "deprecated"


# ===================================================================
# Meta-Reasoning Engine Tests
# ===================================================================


class TestMetaReasoningEngine:
    def test_evaluate_reasoning_quality(self):
        from intelgraph.core.metaintel.metareasoning import MetaReasoningEngine

        meta = MetaReasoningEngine()
        score = meta.evaluate_reasoning_quality([{"confidence": 0.8}, {"confidence": 0.6}])
        assert score == 0.7

    def test_evaluate_empty(self):
        from intelgraph.core.metaintel.metareasoning import MetaReasoningEngine

        meta = MetaReasoningEngine()
        assert meta.evaluate_reasoning_quality([]) == 0.5

    def test_detect_inefficiencies(self):
        from intelgraph.core.metaintel.metareasoning import MetaReasoningEngine

        meta = MetaReasoningEngine()
        layers = {"nlp": {"latency_ms": 3000, "error_rate": 0.2, "consistency": 0.5}}
        result = meta.detect_inefficiencies(layers)
        assert len(result) > 0

    def test_generate_system_hypothesis(self):
        from intelgraph.core.metaintel.metareasoning import MetaReasoningEngine

        meta = MetaReasoningEngine()
        h = meta.generate_system_hypothesis("Performance degrading in NLP", "nlp")
        assert h.target_layer == "nlp"
        assert h.priority == 5

    def test_reflect(self):
        from intelgraph.core.metaintel.metareasoning import MetaReasoningEngine

        meta = MetaReasoningEngine()
        reflection = meta.reflect({"layers": {"nlp": {"score": 0.2}}})
        assert "reflection_id" in reflection


# ===================================================================
# Self-Improvement Controller Tests
# ===================================================================


class TestSelfImprovementController:
    def test_propose_optimization(self):
        from intelgraph.core.metaintel.self_improvement import SelfImprovementController

        ctrl = SelfImprovementController()
        prop = ctrl.propose_optimization("nlp", "Upgrade model", 0.3, 0.2)
        assert prop.target == "nlp"
        assert prop.status == "pending"

    def test_approve_optimization(self):
        from intelgraph.core.metaintel.self_improvement import SelfImprovementController

        ctrl = SelfImprovementController()
        prop = ctrl.propose_optimization("test", "test", 0.1, 0.1)
        assert ctrl.approve_optimization(prop.proposal_id)
        assert prop.status == "approved"

    def test_reject_optimization(self):
        from intelgraph.core.metaintel.self_improvement import SelfImprovementController

        ctrl = SelfImprovementController()
        prop = ctrl.propose_optimization("test", "test", 0.1, 0.1)
        assert ctrl.reject_optimization(prop.proposal_id)

    def test_optimize_resource_allocation(self):
        from intelgraph.core.metaintel.self_improvement import SelfImprovementController

        ctrl = SelfImprovementController()
        result = ctrl.optimize_resource_allocation(
            {"nlp": 0.5, "reasoning": 0.5}, {"nlp": 0.3, "reasoning": 0.9}
        )
        assert abs(sum(result.values()) - 1.0) < 0.01

    def test_tune_learning_rate(self):
        from intelgraph.core.metaintel.self_improvement import SelfImprovementController

        ctrl = SelfImprovementController()
        lr = ctrl.tune_learning_rate("test_layer", 0.2)
        assert lr < 0.1

    def test_optimization_velocity(self):
        from intelgraph.core.metaintel.self_improvement import SelfImprovementController

        ctrl = SelfImprovementController()
        p1 = ctrl.propose_optimization("t1", "test", 0.1, 0.1)
        ctrl.approve_optimization(p1.proposal_id)
        p2 = ctrl.propose_optimization("t2", "test", 0.1, 0.1)
        ctrl.approve_optimization(p2.proposal_id)
        assert ctrl.get_optimization_velocity() > 0


# ===================================================================
# Architecture Evolution Engine Tests
# ===================================================================


class TestArchitectureEvolutionEngine:
    def test_default_modules(self):
        from intelgraph.core.metaintel.architecture import ArchitectureEvolutionEngine

        arch = ArchitectureEvolutionEngine()
        modules = arch.get_modules()
        assert len(modules) >= 5

    def test_propose_architecture_change(self):
        from intelgraph.core.metaintel.architecture import ArchitectureEvolutionEngine

        arch = ArchitectureEvolutionEngine()
        prop = arch.propose_architecture_change("Add new module", "add_module", "new_module")
        assert prop.action == "add_module"
        assert prop.status == "pending"

    def test_apply_add_module(self):
        from intelgraph.core.metaintel.architecture import ArchitectureEvolutionEngine

        arch = ArchitectureEvolutionEngine()
        prop = arch.propose_architecture_change("Add analytics", "add_module", "analytics")
        assert arch.apply_change(prop.proposal_id)
        modules = {m.module_id for m in arch.get_modules()}
        assert "analytics" in modules

    def test_apply_remove_module(self):
        from intelgraph.core.metaintel.architecture import ArchitectureEvolutionEngine

        arch = ArchitectureEvolutionEngine()
        prop = arch.propose_architecture_change("Remove NLP", "remove_module", "nlp")
        assert arch.apply_change(prop.proposal_id)
        modules = {m.module_id for m in arch.get_modules()}
        assert "nlp" not in modules

    def test_detect_no_cycles(self):
        from intelgraph.core.metaintel.architecture import ArchitectureEvolutionEngine

        arch = ArchitectureEvolutionEngine()
        assert arch.detect_cycles() == []

    def test_get_topology(self):
        from intelgraph.core.metaintel.architecture import ArchitectureEvolutionEngine

        arch = ArchitectureEvolutionEngine()
        topo = arch.get_topology()
        assert isinstance(topo, dict)


# ===================================================================
# Truth Consistency Governor Tests
# ===================================================================


class TestTruthConsistencyGovernor:
    def test_resolve_contradiction(self):
        from intelgraph.core.metaintel.truth import TruthConsistencyGovernor

        t = TruthConsistencyGovernor()
        result = t.resolve_contradiction(
            {"value": "A", "confidence": 0.9}, {"value": "B", "confidence": 0.5}
        )
        assert result["value"] == "A"

    def test_reconcile(self):
        from intelgraph.core.metaintel.truth import TruthConsistencyGovernor

        t = TruthConsistencyGovernor()
        unified = t.reconcile(
            {"key1": "kA", "key1_confidence": 0.9},
            {"key1": "kB", "key1_confidence": 0.5},
            {"key2": "eA", "key2_confidence": 0.8},
        )
        assert "key1" in unified
        assert "key2" in unified

    def test_snapshot(self):
        from intelgraph.core.metaintel.truth import TruthConsistencyGovernor

        t = TruthConsistencyGovernor()
        snap = t.snapshot({"key": "value"})
        assert snap.hash is not None
        assert snap.immutable

    def test_get_snapshot(self):
        from intelgraph.core.metaintel.truth import TruthConsistencyGovernor

        t = TruthConsistencyGovernor()
        snap = t.snapshot({"key": "value"})
        assert t.get_snapshot(snap.snapshot_id) is snap

    def test_arbitrate_multi_source(self):
        from intelgraph.core.metaintel.truth import TruthConsistencyGovernor

        t = TruthConsistencyGovernor()
        claims = [
            {"value": "A", "confidence": 0.8, "evidence": [{"source": "s1"}]},
            {"value": "B", "confidence": 0.9, "evidence": [{"source": "s2"}, {"source": "s3"}]},
        ]
        best = t.arbitrate_multi_source(claims)
        assert best["value"] == "B"

    def test_arbitrate_single(self):
        from intelgraph.core.metaintel.truth import TruthConsistencyGovernor

        t = TruthConsistencyGovernor()
        assert t.arbitrate_multi_source([{"value": "X", "confidence": 0.7}])["value"] == "X"

    def test_arbitrate_empty(self):
        from intelgraph.core.metaintel.truth import TruthConsistencyGovernor

        t = TruthConsistencyGovernor()
        assert t.arbitrate_multi_source([]) == {}


# ===================================================================
# Identity Consistency Layer Tests
# ===================================================================


class TestIdentityConsistencyLayer:
    def test_register_agent(self):
        from intelgraph.core.metaintel.identity import IdentityConsistencyLayer

        idl = IdentityConsistencyLayer()
        rec = idl.register_agent("agent_1", "analyst", ["execute", "read"])
        assert rec.agent_id == "agent_1"
        assert rec.role == "analyst"

    def test_detect_role_conflicts(self):
        from intelgraph.core.metaintel.identity import IdentityConsistencyLayer

        idl = IdentityConsistencyLayer()
        for i in range(5):
            idl.register_agent(f"agent_{i}", "user", ["read"])
        conflicts = idl.detect_role_conflicts()
        assert len(conflicts) > 0

    def test_detect_intent_conflicts(self):
        from intelgraph.core.metaintel.identity import IdentityConsistencyLayer

        idl = IdentityConsistencyLayer()
        actions = [
            {"agent": "a1", "target": "server_1"},
            {"agent": "a2", "target": "server_1"},
        ]
        conflicts = idl.detect_intent_conflicts(actions)
        assert len(conflicts) > 0

    def test_verify_authority(self):
        from intelgraph.core.metaintel.identity import IdentityConsistencyLayer

        idl = IdentityConsistencyLayer()
        idl.register_agent("admin_1", "admin", ["all"])
        assert idl.verify_authority("admin_1", "admin")
        assert not idl.verify_authority("admin_1", "superadmin")

    def test_get_identity(self):
        from intelgraph.core.metaintel.identity import IdentityConsistencyLayer

        idl = IdentityConsistencyLayer()
        idl.register_agent("a1", "user", ["read"])
        assert idl.get_identity("a1") is not None
        assert idl.get_identity("nonexistent") is None


# ===================================================================
# Real-World Alignment Layer Tests
# ===================================================================


class TestRealWorldAlignmentLayer:
    def test_compare_output_vs_reality(self):
        from intelgraph.core.metaintel.alignment import RealWorldAlignmentLayer

        al = RealWorldAlignmentLayer()
        scores = al.compare_output_vs_reality({"temp": 25.0}, {"temp": 24.5})
        assert len(scores) == 1
        assert scores[0].aligned

    def test_detect_drift(self):
        from intelgraph.core.metaintel.alignment import AlignmentScore, RealWorldAlignmentLayer

        al = RealWorldAlignmentLayer()
        scores = [
            AlignmentScore(
                score_id="s1", metric="temp", value=0.5, threshold=0.2, aligned=False, source="test"
            ),
        ]
        drifts = al.detect_reality_drift(scores)
        assert len(drifts) == 1

    def test_reconcile_belief_vs_truth(self):
        from intelgraph.core.metaintel.alignment import RealWorldAlignmentLayer

        al = RealWorldAlignmentLayer()
        result = al.reconcile_belief_vs_truth({"ip": "1.1.1.1"}, {"ip": "2.2.2.2"})
        assert result["ip"]["corrected"]

    def test_integrate_external_signal(self):
        from intelgraph.core.metaintel.alignment import RealWorldAlignmentLayer

        al = RealWorldAlignmentLayer()
        al.integrate_external_signal({"type": "alert", "source": "siem"})
        assert len(al._external_signals) == 1


# ===================================================================
# Safety Meta-Control Layer Tests
# ===================================================================


class TestSafetyMetaControlLayer:
    def test_monitor_layer(self):
        from intelgraph.core.metaintel.safety_meta import SafetyMetaControlLayer

        sm = SafetyMetaControlLayer()
        incidents = sm.monitor_layer("nlp", {"error_rate": 0.4, "anomaly_count": 15})
        assert len(incidents) >= 1

    def test_engage_kill_switch(self):
        from intelgraph.core.metaintel.safety_meta import SafetyMetaControlLayer

        sm = SafetyMetaControlLayer()
        assert sm.engage_global_kill_switch()
        assert not sm.is_system_safe()

    def test_disengage_kill_switch(self):
        from intelgraph.core.metaintel.safety_meta import SafetyMetaControlLayer

        sm = SafetyMetaControlLayer()
        sm.engage_global_kill_switch()
        sm.disengage_global_kill_switch()
        assert sm.is_system_safe()

    def test_quarantine(self):
        from intelgraph.core.metaintel.safety_meta import SafetyMetaControlLayer

        sm = SafetyMetaControlLayer()
        assert sm.enter_quarantine()
        assert sm.exit_quarantine()

    def test_resolve_incident(self):
        from intelgraph.core.metaintel.safety_meta import SafetyMetaControlLayer

        sm = SafetyMetaControlLayer()
        incidents = sm.monitor_layer("test", {"error_rate": 0.5, "anomaly_count": 0})
        assert len(incidents) > 0
        assert sm.resolve_incident(incidents[0].incident_id)
        assert incidents[0].resolved

    def test_get_active_threats(self):
        from intelgraph.core.metaintel.safety_meta import SafetyMetaControlLayer

        sm = SafetyMetaControlLayer()
        sm.monitor_layer("nlp", {"error_rate": 0.5, "anomaly_count": 0})
        threats = sm.get_active_threats()
        assert len(threats) >= 1


# ===================================================================
# Global Observability Dashboard Tests
# ===================================================================


class TestGlobalObservabilityDashboard:
    def test_record_snapshot(self):
        from intelgraph.core.metaintel.observability import GlobalObservabilityDashboard

        obs = GlobalObservabilityDashboard()
        snap = obs.record_snapshot(
            {
                "reasoning_quality": 0.9,
                "execution_reliability": 0.8,
                "knowledge_consistency": 0.7,
                "system_drift": 0.1,
                "cross_phase_alignment": 0.8,
                "stability_index": 0.9,
                "governance_conflict_rate": 0.0,
                "improvement_velocity": 0.3,
                "architecture_mutation_rate": 0.0,
            }
        )
        assert snap.reasoning_quality == 0.9

    def test_get_latest(self):
        from intelgraph.core.metaintel.observability import GlobalObservabilityDashboard

        obs = GlobalObservabilityDashboard()
        assert obs.get_latest() is None
        obs.record_snapshot({"reasoning_quality": 0.8})
        assert obs.get_latest() is not None

    def test_get_trend(self):
        from intelgraph.core.metaintel.observability import GlobalObservabilityDashboard

        obs = GlobalObservabilityDashboard()
        for v in [0.5, 0.6, 0.7]:
            obs.record_snapshot({"reasoning_quality": v})
        trend = obs.get_trend("reasoning_quality", 2)
        assert len(trend) == 2

    def test_global_health_index(self):
        from intelgraph.core.metaintel.observability import GlobalObservabilityDashboard

        obs = GlobalObservabilityDashboard()
        obs.record_snapshot(
            {
                "reasoning_quality": 0.9,
                "execution_reliability": 0.8,
                "knowledge_consistency": 0.7,
                "system_drift": 0.1,
                "cross_phase_alignment": 0.8,
                "stability_index": 0.9,
                "governance_conflict_rate": 0.0,
                "improvement_velocity": 0.3,
                "architecture_mutation_rate": 0.0,
            }
        )
        index = obs.compute_global_health_index()
        assert 0.0 <= index <= 1.0


# ===================================================================
# Incident Control Center Tests
# ===================================================================


class TestIncidentControlCenter:
    def _make_icc(self):
        from intelgraph.core.metaintel.alerting import IncidentControlCenter

        return IncidentControlCenter({"cooldown_seconds": 0})

    def test_evaluate_triggers_when_exceeds_max(self):
        icc = self._make_icc()
        alerts = icc.evaluate(
            {"error_rate": 0.8},
            {
                "high_error_rate": {
                    "enabled": True,
                    "max": 0.5,
                    "severity": "critical",
                    "metric_key": "error_rate",
                },
            },
        )
        assert len(alerts) >= 1

    def test_no_alert_below_threshold(self):
        icc = self._make_icc()
        alerts = icc.evaluate(
            {"error_rate": 0.2},
            {
                "high_error_rate": {
                    "enabled": True,
                    "max": 0.5,
                    "severity": "critical",
                    "metric_key": "error_rate",
                },
            },
        )
        assert len(alerts) == 0

    def test_resolve_alert(self):
        icc = self._make_icc()
        alerts = icc.evaluate(
            {"error_rate": 0.9},
            {
                "high_error_rate": {
                    "enabled": True,
                    "max": 0.5,
                    "severity": "critical",
                    "metric_key": "error_rate",
                },
            },
        )
        assert len(alerts) > 0
        assert icc.resolve_alert(alerts[0].alert_id)
        assert alerts[0].resolved


# ===================================================================
# Versioned System State Tests
# ===================================================================


class TestVersionedSystemState:
    def test_snapshot(self):
        from intelgraph.core.metaintel.state import VersionedSystemState

        vs = VersionedSystemState()
        snap = vs.snapshot({"nlp": "active", "reasoning": "active"})
        assert snap.version == 1
        assert snap.hash is not None

    def test_version_increment(self):
        from intelgraph.core.metaintel.state import VersionedSystemState

        vs = VersionedSystemState()
        vs.snapshot({"a": 1})
        vs.snapshot({"b": 2})
        assert vs._snapshots[-1].version == 2

    def test_restore(self):
        from intelgraph.core.metaintel.state import VersionedSystemState

        vs = VersionedSystemState()
        snap = vs.snapshot({"mode": "active"})
        vs.snapshot({"mode": "inactive"})
        assert vs.restore(snap.snapshot_id)
        assert vs.get_current_state()["mode"] == "active"

    def test_restore_nonexistent(self):
        from intelgraph.core.metaintel.state import VersionedSystemState

        vs = VersionedSystemState()
        assert not vs.restore("nonexistent")

    def test_verify_integrity(self):
        from intelgraph.core.metaintel.state import VersionedSystemState

        vs = VersionedSystemState()
        vs.snapshot({"a": 1})
        vs.snapshot({"b": 2})
        assert vs.verify_integrity()

    def test_tampered_integrity(self):
        from intelgraph.core.metaintel.state import VersionedSystemState

        vs = VersionedSystemState()
        snap = vs.snapshot({"a": 1})
        snap.hash = "tampered"
        assert not vs.verify_integrity()

    def test_get_timeline(self):
        from intelgraph.core.metaintel.state import VersionedSystemState

        vs = VersionedSystemState()
        vs.snapshot({"a": 1})
        timeline = vs.get_timeline()
        assert len(timeline) == 1
        assert "snapshot_id" in timeline[0]


# ===================================================================
# CLI Metaintel Tests
# ===================================================================


class TestCLIMetaintel:
    def test_command_names(self):
        from intelgraph.cli.metaintel import metaintel_group

        assert metaintel_group.name == "metaintel"
        commands = [cmd.name for cmd in metaintel_group.commands.values()]
        expected = [
            "health",
            "diagnose",
            "policy",
            "hypothesis",
            "optimize",
            "architecture",
            "truth",
            "identity",
            "alignment",
            "safety",
            "dashboard",
            "snapshot",
            "alerts",
            "state",
        ]
        for cmd in expected:
            assert cmd in commands, f"Missing command: {cmd}"

    def test_health_command(self):
        from click.testing import CliRunner

        from intelgraph.cli.metaintel import health

        runner = CliRunner()
        result = runner.invoke(health)
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "overall_health_score" in data

    def test_hypothesis_command(self):
        from click.testing import CliRunner

        from intelgraph.cli.metaintel import hypothesis

        runner = CliRunner()
        result = runner.invoke(hypothesis, ["Performance degrading", "--target-layer", "nlp"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data["target_layer"] == "nlp"


# ===================================================================
# API Metaintel Tests
# ===================================================================


class TestAPIMetaintel:
    def setup_method(self):
        from fastapi.testclient import TestClient

        from intelgraph.api.main import create_app

        self.client = TestClient(create_app({"storage": {"path": ":memory:"}}))

    def _auth_headers(self, role: str = "analyst"):
        resp = self.client.post(
            "/auth/register",
            json={
                "username": f"{role}_{uuid.uuid4().hex[:8]}",
                "password": "test123",
                "role": role,
            },
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_health_endpoint(self):
        headers = self._auth_headers()
        resp = self.client.get("/metaintel/health", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_health_score" in data

    def test_diagnostics_run(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/metaintel/diagnostics/run",
            json={
                "pipeline_stage": "nlp",
                "metrics": {"latency_ms": 500, "error_rate": 0.05},
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pipeline_stage"] == "nlp"

    def test_policy_generate(self):
        headers = self._auth_headers("admin")
        resp = self.client.post(
            "/metaintel/policy/generate",
            json={
                "name": "test_policy",
                "description": "test",
                "rules": [{"action": "block"}],
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_hypothesis_generate(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/metaintel/hypothesis/generate",
            json={
                "observation": "System degrading",
                "target_layer": "reasoning",
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_optimization_propose(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/metaintel/optimization/propose",
            json={
                "target": "nlp",
                "description": "Upgrade model",
                "expected_gain": 0.3,
                "risk": 0.2,
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_architecture_propose(self):
        headers = self._auth_headers("admin")
        resp = self.client.post(
            "/metaintel/architecture/propose",
            json={
                "description": "Add module",
                "action": "add_module",
                "target_module": "analytics",
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_truth_reconcile(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/metaintel/truth/reconcile",
            json={
                "knowledge_state": {"ip": "1.1.1.1", "ip_confidence": 0.9},
                "reasoning_state": {"ip": "2.2.2.2", "ip_confidence": 0.5},
                "execution_state": {},
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "unified_state" in data

    def test_identity_register(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/metaintel/identity/register",
            json={
                "agent_id": "agent_1",
                "role": "analyst",
                "capabilities": ["execute"],
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_alignment_check(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/metaintel/alignment/check",
            json={
                "system_output": {"temp": 25.0},
                "real_world_data": {"temp": 24.8},
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_safety_monitor(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/metaintel/safety/monitor",
            json={
                "layer_id": "nlp",
                "metrics": {"error_rate": 0.4, "anomaly_count": 15},
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_safety_kill_switch_admin(self):
        headers = self._auth_headers("admin")
        resp = self.client.post(
            "/metaintel/safety/kill-switch", json={"disengage": False}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "kill_switch_engaged"

    def test_safety_kill_switch_unauthorized(self):
        headers = self._auth_headers("user")
        resp = self.client.post("/metaintel/safety/kill-switch", json={}, headers=headers)
        assert resp.status_code == 403

    def test_observability_snapshot(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/metaintel/observability/snapshot",
            json={
                "metrics": {"reasoning_quality": 0.9, "execution_reliability": 0.8},
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_observability_dashboard(self):
        headers = self._auth_headers()
        # First record a snapshot
        self.client.post(
            "/metaintel/observability/snapshot",
            json={
                "metrics": {
                    "reasoning_quality": 0.9,
                    "execution_reliability": 0.8,
                    "knowledge_consistency": 0.7,
                    "system_drift": 0.1,
                    "cross_phase_alignment": 0.8,
                    "stability_index": 0.9,
                    "governance_conflict_rate": 0.0,
                    "improvement_velocity": 0.3,
                    "architecture_mutation_rate": 0.0,
                },
            },
            headers=headers,
        )
        resp = self.client.get("/metaintel/observability/dashboard", headers=headers)
        assert resp.status_code == 200

    def test_alerts_endpoint(self):
        headers = self._auth_headers()
        resp = self.client.get("/metaintel/alerts", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data

    def test_state_snapshot_admin(self):
        headers = self._auth_headers("admin")
        resp = self.client.post(
            "/metaintel/state/snapshot",
            json={
                "layers": {"nlp": "active", "reasoning": "active"},
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 1

    def test_state_integrity(self):
        headers = self._auth_headers()
        resp = self.client.get("/metaintel/state/integrity", headers=headers)
        assert resp.status_code == 200

    def test_unauthorized_admin_action(self):
        headers = self._auth_headers("user")
        resp = self.client.post(
            "/metaintel/policy/generate", json={"name": "test"}, headers=headers
        )
        assert resp.status_code == 403

    def test_diagnostics_missing_stage(self):
        headers = self._auth_headers()
        resp = self.client.post("/metaintel/diagnostics/run", json={"metrics": {}}, headers=headers)
        assert resp.status_code == 422
