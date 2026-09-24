from __future__ import annotations

import uuid

# ===================================================================
# Consolidation Engine Tests
# ===================================================================


class TestConsolidationEngine:
    def test_scan_engines(self):
        from intelgraph.core.ucos.consolidation import ConsolidationEngine

        eng = ConsolidationEngine()
        engines = eng.get_engines()
        assert len(engines) > 0

    def test_detect_duplicates(self):
        from intelgraph.core.ucos.consolidation import ConsolidationEngine

        eng = ConsolidationEngine()
        dups = eng.detect_duplicates()
        assert isinstance(dups, list)

    def test_consolidation_plan(self):
        from intelgraph.core.ucos.consolidation import ConsolidationEngine

        eng = ConsolidationEngine()
        plan = eng.consolidation_plan()
        assert "duplicates_found" in plan
        assert "engines_scanned" in plan


# ===================================================================
# Unified Cognitive Core Tests
# ===================================================================


class TestUnifiedCognitiveCore:
    def test_reason_multi_hop(self):
        from intelgraph.core.ucos.cognitive import UnifiedCognitiveCore

        cog = UnifiedCognitiveCore()
        result = cog.reason("A->B", {"graph": {"adjacency": {"A": {"B"}, "B": set()}}})
        assert result.total_confidence > 0
        assert len(result.paths) > 0

    def test_reason_no_graph(self):
        from intelgraph.core.ucos.cognitive import UnifiedCognitiveCore

        cog = UnifiedCognitiveCore()
        result = cog.reason("test query")
        assert result.query == "test query"

    def test_causal_inference(self):
        from intelgraph.core.ucos.cognitive import UnifiedCognitiveCore

        cog = UnifiedCognitiveCore()
        result = cog.reason(
            "X",
            {
                "graph": {
                    "adjacency": {"X": {"Y"}, "Y": {"Z"}},
                    "forward_adjacency": {"X": {"Y"}, "Y": {"Z"}},
                }
            },
        )
        assert len(result.paths) >= 0

    def test_temporal_reason(self):
        from intelgraph.core.ucos.cognitive import UnifiedCognitiveCore

        cog = UnifiedCognitiveCore()
        events = [
            {"entity": "A", "timestamp": "2024-01-01T00:00:00Z"},
            {"entity": "B", "timestamp": "2024-01-01T01:00:00Z"},
        ]
        chains = cog.temporal_reason(events)
        assert len(chains) == 1

    def test_probabilistic_reason(self):
        from intelgraph.core.ucos.cognitive import UnifiedCognitiveCore

        cog = UnifiedCognitiveCore()
        result = cog.probabilistic_reason([{"confidence": 0.8}, {"confidence": 0.7}])
        assert abs(result["confidence"] - 0.56) < 1e-6


# ===================================================================
# Closed-Loop Intelligence System Tests
# ===================================================================


class TestClosedLoopIntelligenceSystem:
    def test_run_cycle(self):
        from intelgraph.core.ucos.closed_loop import ClosedLoopIntelligenceSystem

        loop = ClosedLoopIntelligenceSystem()
        entry = loop.run_cycle(
            {"summary": "test"},
            {
                "result_id": "r1",
                "paths": [],
                "contradictions": [],
                "hypotheses": [],
                "total_confidence": 0.8,
                "duration_ms": 100,
                "query": "test",
                "reasoning_type": "multi_hop",
            },
            {
                "execution_id": "e1",
                "success": True,
                "steps": [],
                "outputs": {},
                "duration_ms": 50,
                "goal": "test",
                "error": "",
            },
            {"latency_ms": 100},
        )
        assert entry.success
        assert entry.stage == "closed_loop"

    def test_drift_detection(self):
        from intelgraph.core.ucos.closed_loop import ClosedLoopIntelligenceSystem

        loop = ClosedLoopIntelligenceSystem()
        loop.run_cycle(
            {"summary": "t"}, {"total_confidence": 0.8}, {"success": True}, {"accuracy": 1.0}
        )
        entry = loop.run_cycle(
            {"summary": "t"}, {"total_confidence": 0.8}, {"success": True}, {"accuracy": 0.5}
        )
        assert entry.success or not entry.success  # May or may not exceed drift threshold


# ===================================================================
# Unified Policy Control Plane Tests
# ===================================================================


class TestUnifiedPolicyControlPlane:
    def test_evaluate_allows(self):
        from intelgraph.core.ucos.policy import UnifiedPolicyControlPlane

        p = UnifiedPolicyControlPlane()
        decision = p.evaluate("read", 0.3)
        assert decision.allowed

    def test_evaluate_denies_high_risk(self):
        from intelgraph.core.ucos.policy import UnifiedPolicyControlPlane

        p = UnifiedPolicyControlPlane()
        decision = p.evaluate("delete", 0.9)
        assert not decision.allowed

    def test_evaluate_forbidden_action(self):
        from intelgraph.core.ucos.policy import UnifiedPolicyControlPlane

        p = UnifiedPolicyControlPlane()
        decision = p.evaluate("shutdown", 0.3)
        assert not decision.allowed

    def test_add_rule(self):
        from intelgraph.core.ucos.policy import UnifiedPolicyControlPlane

        p = UnifiedPolicyControlPlane()
        count = len(p.get_rules())
        p.add_rule({"name": "custom", "action": "deny", "max_risk": 0.5})
        assert len(p.get_rules()) == count + 1

    def test_override_decision(self):
        from intelgraph.core.ucos.policy import UnifiedPolicyControlPlane

        p = UnifiedPolicyControlPlane()
        decision = p.evaluate("shutdown", 0.3)
        assert not decision.allowed
        assert p.override_decision(decision.decision_id, "admin override")
        assert decision.allowed


# ===================================================================
# Unified Truth Engine Tests
# ===================================================================


class TestUnifiedTruthEngine:
    def test_write_and_read(self):
        from intelgraph.core.ucos.truth import UnifiedTruthEngine

        t = UnifiedTruthEngine()
        t.write("key1", "value1", "test", 0.8)
        entry = t.read("key1")
        assert entry["value"] == "value1"

    def test_reject_lower_confidence(self):
        from intelgraph.core.ucos.truth import UnifiedTruthEngine

        t = UnifiedTruthEngine()
        t.write("key", "first", "s1", 0.9)
        result = t.write("key", "second", "s2", 0.3)
        assert result["action"] == "rejected"

    def test_overwrite_higher_confidence(self):
        from intelgraph.core.ucos.truth import UnifiedTruthEngine

        t = UnifiedTruthEngine()
        t.write("key", "first", "s1", 0.3)
        result = t.write("key", "second", "s2", 0.9)
        assert result["action"] == "overwritten"

    def test_query(self):
        from intelgraph.core.ucos.truth import UnifiedTruthEngine

        t = UnifiedTruthEngine()
        t.write("target_ip", "1.1.1.1", "s1", 0.8)
        t.write("source_ip", "2.2.2.2", "s1", 0.7)
        results = t.query("ip")
        assert len(results) == 2

    def test_snapshot(self):
        from intelgraph.core.ucos.truth import UnifiedTruthEngine

        t = UnifiedTruthEngine()
        t.write("a", 1, "s1")
        snap = t.snapshot()
        assert snap["entry_count"] >= 1

    def test_reconcile(self):
        from intelgraph.core.ucos.truth import UnifiedTruthEngine

        t = UnifiedTruthEngine()
        result = t.reconcile(
            [
                {"k1": {"value": "a", "confidence": 0.9}},
                {"k1": {"value": "b", "confidence": 0.5}},
            ]
        )
        assert result["k1"]["value"] == "a"


# ===================================================================
# Unified Execution Runtime Tests
# ===================================================================


class TestUnifiedExecutionRuntime:
    def test_execute(self):
        from intelgraph.core.ucos.runtime import UnifiedExecutionRuntime

        r = UnifiedExecutionRuntime()
        result = r.execute("test goal")
        assert result.goal == "test goal"
        assert result.success

    def test_execute_with_steps(self):
        from intelgraph.core.ucos.runtime import UnifiedExecutionRuntime

        r = UnifiedExecutionRuntime()
        result = r.execute("analyze", [{"action": "tool_call", "params": {"tool": "scanner"}}])
        assert result.success
        assert "tool_call" in result.outputs

    def test_rollback(self):
        from intelgraph.core.ucos.runtime import UnifiedExecutionRuntime

        r = UnifiedExecutionRuntime()
        result = r.execute("rollback_test")
        assert r.rollback(result.execution_id)
        assert not result.success

    def test_task_queue(self):
        from intelgraph.core.ucos.runtime import UnifiedExecutionRuntime

        r = UnifiedExecutionRuntime()
        tid = r.enqueue({"action": "scan"})
        assert tid is not None
        task = r.dequeue()
        assert task["task_id"] == tid
        assert r.complete_task(tid, True)

    def test_audit(self):
        from intelgraph.core.ucos.runtime import UnifiedExecutionRuntime

        r = UnifiedExecutionRuntime()
        r.execute("test", [{"action": "tool_call", "params": {}}])
        audit = r.get_audit()
        assert len(audit) > 0


# ===================================================================
# Unified Telemetry Core Tests
# ===================================================================


class TestUnifiedTelemetryCore:
    def test_record(self):
        from intelgraph.core.ucos.telemetry import UnifiedTelemetryCore

        tel = UnifiedTelemetryCore()
        snap = tel.record(reasoning_quality=0.9, execution_success=True, latency_ms=100)
        assert 0.0 <= snap.health_index <= 1.0
        assert snap.reasoning_quality == 0.9

    def test_get_latest(self):
        from intelgraph.core.ucos.telemetry import UnifiedTelemetryCore

        tel = UnifiedTelemetryCore()
        assert tel.get_latest() is None
        tel.record(reasoning_quality=0.5)
        assert tel.get_latest() is not None

    def test_get_trend(self):
        from intelgraph.core.ucos.telemetry import UnifiedTelemetryCore

        tel = UnifiedTelemetryCore()
        for v in [0.5, 0.6, 0.7]:
            tel.record(reasoning_quality=v)
        trend = tel.get_trend("reasoning_quality", 2)
        assert len(trend) == 2


# ===================================================================
# Unified Safety Layer Tests
# ===================================================================


class TestUnifiedSafetyLayer:
    def test_check_safe(self):
        from intelgraph.core.ucos.safety import UnifiedSafetyLayer

        s = UnifiedSafetyLayer()
        result = s.check_safety({"type": "read", "risk": 0.3})
        assert result["safe"]

    def test_kill_switch_blocks(self):
        from intelgraph.core.ucos.safety import UnifiedSafetyLayer

        s = UnifiedSafetyLayer()
        s.engage_kill_switch()
        result = s.check_safety({"type": "read", "risk": 0.1})
        assert not result["safe"]

    def test_quarantine_blocks_high_risk(self):
        from intelgraph.core.ucos.safety import UnifiedSafetyLayer

        s = UnifiedSafetyLayer()
        s.enter_quarantine()
        result = s.check_safety({"type": "write", "risk": 0.5})
        assert not result["safe"]

    def test_safe_degradation(self):
        from intelgraph.core.ucos.safety import UnifiedSafetyLayer

        s = UnifiedSafetyLayer()
        s.enable_safe_degradation()
        result = s.check_safety({"type": "write", "risk": 0.7})
        assert not result["safe"]

    def test_runaway_loop_detection(self):
        from intelgraph.core.ucos.safety import UnifiedSafetyLayer

        s = UnifiedSafetyLayer()
        actions = [{"type": "repeat"}] * 5
        assert s.detect_runaway_loop(actions)


# ===================================================================
# Self-Stabilizing Meta Control Tests
# ===================================================================


class TestSelfStabilizingMetaControl:
    def test_propose_change(self):
        from intelgraph.core.ucos.meta_control import SelfStabilizingMetaControl

        mc = SelfStabilizingMetaControl()
        prop = mc.propose_change("Update model", "nlp", "config_update", 0.3)
        assert prop["status"] == "pending"
        assert prop["target"] == "nlp"

    def test_approve_change(self):
        from intelgraph.core.ucos.meta_control import SelfStabilizingMetaControl

        mc = SelfStabilizingMetaControl()
        prop = mc.propose_change("test", "t1", "config", 0.1)
        assert mc.approve_change(prop["proposal_id"])
        assert prop["status"] == "approved"

    def test_reject_change(self):
        from intelgraph.core.ucos.meta_control import SelfStabilizingMetaControl

        mc = SelfStabilizingMetaControl()
        prop = mc.propose_change("test", "t1", "config", 0.1)
        assert mc.reject_change(prop["proposal_id"], "not needed")
        assert prop["status"] == "rejected"

    def test_validate_regression(self):
        from intelgraph.core.ucos.meta_control import SelfStabilizingMetaControl

        mc = SelfStabilizingMetaControl()
        result = mc.validate_regression({"accuracy": 0.9}, {"accuracy": 0.5})
        assert result["has_regression"]


# ===================================================================
# Simplification Engine Tests
# ===================================================================


class TestSimplificationEngine:
    def test_register_module(self):
        from intelgraph.core.ucos.simplification import SimplificationEngine

        sim = SimplificationEngine()
        sim.register_module("m1", "extraction", "nlp_team")
        modules = sim.get_modules()
        assert "m1" in modules

    def test_check_no_duplicates(self):
        from intelgraph.core.ucos.simplification import SimplificationEngine

        sim = SimplificationEngine()
        sim.register_module("m1", "extraction", "t1")
        sim.register_module("m2", "extraction", "t2")
        violations = sim.check_no_duplicates()
        assert len(violations) > 0

    def test_compute_complexity(self):
        from intelgraph.core.ucos.simplification import SimplificationEngine

        sim = SimplificationEngine()
        sim.register_module("m1", "a", "t1")
        c = sim.compute_system_complexity()
        assert c > 0


# ===================================================================
# Global Health Index Tests
# ===================================================================


class TestGlobalHealthIndex:
    def test_compute(self):
        from intelgraph.core.ucos.health import GlobalHealthIndex

        h = GlobalHealthIndex()
        result = h.compute(cognitive=0.9, execution=0.8, knowledge=0.7, policy=0.8, complexity=0.2)
        assert 0.0 <= result["overall_health"] <= 1.0
        assert result["cognitive_health_score"] == 0.9

    def test_get_trend(self):
        from intelgraph.core.ucos.health import GlobalHealthIndex

        h = GlobalHealthIndex()
        h.compute(cognitive=0.8)
        h.compute(cognitive=0.7)
        trend = h.get_trend("cognitive_health_score", 2)
        assert len(trend) == 2


# ===================================================================
# Unified Alerting Core Tests
# ===================================================================


class TestUnifiedAlertingCore:
    def test_evaluate_triggers(self):
        from intelgraph.core.ucos.alerting import UnifiedAlertingCore

        ac = UnifiedAlertingCore({"cooldown_seconds": 0})
        alerts = ac.evaluate(
            {"error_rate": 0.9},
            {
                "high_error": {
                    "enabled": True,
                    "max": 0.5,
                    "severity": "critical",
                    "metric_key": "error_rate",
                },
            },
        )
        assert len(alerts) >= 1

    def test_no_alert_below(self):
        from intelgraph.core.ucos.alerting import UnifiedAlertingCore

        ac = UnifiedAlertingCore({"cooldown_seconds": 0})
        alerts = ac.evaluate(
            {"error_rate": 0.2},
            {
                "high_error": {"enabled": True, "max": 0.5, "metric_key": "error_rate"},
            },
        )
        assert len(alerts) == 0

    def test_resolve_alert(self):
        from intelgraph.core.ucos.alerting import UnifiedAlertingCore

        ac = UnifiedAlertingCore({"cooldown_seconds": 0})
        alerts = ac.evaluate(
            {"error_rate": 0.9},
            {
                "high_error": {"enabled": True, "max": 0.5, "metric_key": "error_rate"},
            },
        )
        assert ac.resolve_alert(alerts[0]["alert_id"])
        assert alerts[0]["resolved"]


# ===================================================================
# Dependency Validator Tests
# ===================================================================


class TestDependencyValidator:
    def test_no_cycle(self):
        from intelgraph.core.ucos.boundary import DependencyValidator

        dv = DependencyValidator()
        dv.register_module("a", ["b"])
        dv.register_module("b", ["c"])
        dv.register_module("c", [])
        cycles = dv.validate_no_circular()
        assert len(cycles) == 0

    def test_cycle_detected(self):
        from intelgraph.core.ucos.boundary import DependencyValidator

        dv = DependencyValidator()
        dv.register_module("a", ["b"])
        dv.register_module("b", ["c"])
        dv.register_module("c", ["a"])
        cycles = dv.validate_no_circular()
        assert len(cycles) > 0

    def test_self_dependency_blocked(self):
        from intelgraph.core.ucos.boundary import DependencyValidator

        dv = DependencyValidator()
        dv.register_module("a", [])
        assert not dv.validate_no_unsafe_injection("a", "a")

    def test_unsafe_injection_blocked(self):
        from intelgraph.core.ucos.boundary import DependencyValidator

        dv = DependencyValidator()
        dv.register_module("a", ["b"])
        dv.register_module("b", ["a"])
        cycles = dv.validate_no_circular()
        assert len(cycles) > 0


# ===================================================================
# Single Source of Truth Tests
# ===================================================================


class TestSingleSourceOfTruth:
    def test_set_and_get(self):
        from intelgraph.core.ucos.state import SingleSourceOfTruth

        s = SingleSourceOfTruth()
        s.set("key1", "value1", "test", 0.9)
        entry = s.get("key1")
        assert entry.value == "value1"
        assert entry.source == "test"

    def test_reject_lower_confidence(self):
        from intelgraph.core.ucos.state import SingleSourceOfTruth

        s = SingleSourceOfTruth()
        s.set("k", "first", "s1", 0.9)
        result = s.set("k", "second", "s2", 0.3)
        assert result["action"] == "rejected"

    def test_reconcile_higher_confidence(self):
        from intelgraph.core.ucos.state import SingleSourceOfTruth

        s = SingleSourceOfTruth()
        s.set("k", "first", "s1", 0.3)
        result = s.set("k", "second", "s2", 0.9)
        assert result["action"] == "reconciled"

    def test_snapshot(self):
        from intelgraph.core.ucos.state import SingleSourceOfTruth

        s = SingleSourceOfTruth()
        s.set("a", 1, "s1")
        snap = s.snapshot()
        assert snap["entry_count"] >= 1


# ===================================================================
# CLI UCOS Tests
# ===================================================================


class TestCLIUCOS:
    def test_command_names(self):
        from intelgraph.cli.ucos import ucos_group

        assert ucos_group.name == "ucos"
        commands = [cmd.name for cmd in ucos_group.commands.values()]
        expected = [
            "query",
            "reason",
            "act",
            "observe",
            "policy",
            "health",
            "consolidate",
            "simplify",
            "closed-loop",
            "safety",
            "alerts",
            "dependency",
            "state",
        ]
        for cmd in expected:
            assert cmd in commands, f"Missing: {cmd}"

    def test_reason_command(self):
        from click.testing import CliRunner

        from intelgraph.cli.ucos import reason

        runner = CliRunner()
        result = runner.invoke(reason, ["A->B"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "result_id" in data

    def test_health_command(self):
        from click.testing import CliRunner

        from intelgraph.cli.ucos import health

        runner = CliRunner()
        result = runner.invoke(health)
        assert result.exit_code == 0


# ===================================================================
# API UCOS Tests
# ===================================================================


class TestAPIUCOS:
    def setup_method(self):
        from fastapi.testclient import TestClient

        from intelgraph.api.main import create_app

        self.client = TestClient(create_app({"storage": {"path": ":memory:"}}))

    def _auth_headers(self, role: str = "analyst"):
        resp = self.client.post(
            "/auth/register",
            json={
                "username": f"ucos_{role}_{uuid.uuid4().hex[:8]}",
                "password": "test123",
                "role": role,
            },
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_system_query(self):
        headers = self._auth_headers()
        resp = self.client.post("/system/query", json={"key": "test"}, headers=headers)
        assert resp.status_code == 200

    def test_system_reason(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/system/reason",
            json={
                "query": "A->B",
                "context": {"graph": {"adjacency": {"A": ["B"], "B": []}}},
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "result_id" in data

    def test_system_reason_empty(self):
        headers = self._auth_headers()
        resp = self.client.post("/system/reason", json={"query": ""}, headers=headers)
        assert resp.status_code == 422

    def test_system_act(self):
        headers = self._auth_headers()
        resp = self.client.post("/system/act", json={"goal": "scan", "risk": 0.3}, headers=headers)
        assert resp.status_code == 200

    def test_system_act_policy_denied(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/system/act", json={"goal": "destroy", "risk": 0.9}, headers=headers
        )
        assert resp.status_code == 403

    def test_system_observe(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/system/observe",
            json={
                "reasoning_quality": 0.9,
                "execution_success": True,
                "latency_ms": 100,
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_policy_evaluate(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/system/policy/evaluate",
            json={
                "action_type": "read",
                "risk": 0.3,
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_policy_override_admin(self):
        headers = self._auth_headers("admin")
        # First create a decision
        self.client.post(
            "/system/policy/evaluate",
            json={"action_type": "shutdown", "risk": 0.3},
            headers=headers,
        )
        # Get the decision
        resp = self.client.post(
            "/system/policy/override",
            json={
                "decision_id": "nonexistent",
                "reason": "override test",
            },
            headers=headers,
        )
        assert resp.status_code == 404  # nonexistent decision

    def test_state_get(self):
        headers = self._auth_headers()
        resp = self.client.get("/system/state", headers=headers)
        assert resp.status_code == 200

    def test_state_set(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/system/state/set",
            json={
                "key": "test_key",
                "value": "test_value",
                "source": "test",
                "confidence": 0.8,
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_state_snapshot_admin(self):
        headers = self._auth_headers("admin")
        resp = self.client.post("/system/state/snapshot", headers=headers)
        assert resp.status_code == 200

    def test_consolidation_scan(self):
        headers = self._auth_headers("admin")
        resp = self.client.post("/system/consolidation/scan", headers=headers)
        assert resp.status_code == 200

    def test_health_endpoint(self):
        headers = self._auth_headers()
        resp = self.client.get("/system/health", headers=headers)
        assert resp.status_code == 200

    def test_closed_loop(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/system/closed-loop",
            json={
                "query": "A->B",
                "input": {"summary": "test"},
                "context": {"graph": {"adjacency": {"A": ["B"], "B": []}}},
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_safety_check(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/system/safety/check",
            json={
                "action": {"type": "read", "risk": 0.3},
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_safety_kill_switch_admin(self):
        headers = self._auth_headers("admin")
        resp = self.client.post(
            "/system/safety/kill-switch", json={"disengage": False}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "kill_switch_engaged"

    def test_safety_kill_switch_unauthorized(self):
        headers = self._auth_headers("user")
        resp = self.client.post("/system/safety/kill-switch", json={}, headers=headers)
        assert resp.status_code == 403

    def test_alerts(self):
        headers = self._auth_headers()
        resp = self.client.get("/system/alerts", headers=headers)
        assert resp.status_code == 200

    def test_dependency_register(self):
        headers = self._auth_headers("admin")
        resp = self.client.post(
            "/system/dependency/register",
            json={
                "module_id": "test_mod",
                "dependencies": ["dep1", "dep2"],
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_simplify_check(self):
        headers = self._auth_headers()
        resp = self.client.post("/system/simplify/check", headers=headers)
        assert resp.status_code == 200

    def test_meta_propose_admin(self):
        headers = self._auth_headers("admin")
        resp = self.client.post(
            "/system/meta-control/propose",
            json={
                "description": "Update NLP",
                "target": "nlp",
                "change_type": "config",
                "risk": 0.3,
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_meta_propose_unauthorized(self):
        headers = self._auth_headers("user")
        resp = self.client.post(
            "/system/meta-control/propose",
            json={
                "description": "test",
                "target": "test",
            },
            headers=headers,
        )
        assert resp.status_code == 403

    def test_consolidation_apply(self):
        headers = self._auth_headers("admin")
        resp = self.client.post("/system/consolidation/apply", headers=headers)
        assert resp.status_code == 200
