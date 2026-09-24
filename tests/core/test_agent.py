from __future__ import annotations

import uuid

import pytest

# ===================================================================
# Agent Hierarchy Tests
# ===================================================================


class TestAgentOrchestrator:
    def test_create_agent(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator, AgentRole

        orch = AgentOrchestrator()
        agent = orch.spawn_agent(AgentRole.EXECUTOR, capabilities=["execute"])
        assert agent.role == AgentRole.EXECUTOR
        assert "execute" in agent.capabilities

    def test_spawn_and_terminate_agent(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator, AgentRole, AgentStatus

        orch = AgentOrchestrator()
        agent = orch.spawn_agent(AgentRole.PLANNER)
        assert orch.terminate_agent(agent.agent_id)
        assert orch.get_agent(agent.agent_id).status == AgentStatus.TERMINATED

    def test_cannot_terminate_master(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator, AgentRole

        orch = AgentOrchestrator()
        master = orch.list_agents(AgentRole.MASTER)[0]
        assert not orch.terminate_agent(master.agent_id)

    def test_decompose_task(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator

        orch = AgentOrchestrator()
        root = orch.decompose_task("analyze threat data", max_depth=2)
        assert root.description == "analyze threat data"
        assert len(root.sub_tasks) > 0

    def test_create_plan(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator

        orch = AgentOrchestrator()
        plan = orch.create_plan("investigate anomaly")
        assert plan.goal == "investigate anomaly"
        assert len(plan.agent_assignments) > 0
        assert plan.estimated_cost > 0

    def test_detect_no_deadlock(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator

        orch = AgentOrchestrator()
        orch.decompose_task("simple task", max_depth=1)
        deadlocks = orch.detect_deadlock()
        assert deadlocks == []

    def test_arbitrate_priority(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator

        orch = AgentOrchestrator()
        root = orch.decompose_task("test", max_depth=1)
        all_tids = [root.task_id] + [s.task_id for s in root.sub_tasks]
        sorted_tids = orch.arbitrate_priority(all_tids)
        assert len(sorted_tids) == len(all_tids)

    def test_get_plan(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator

        orch = AgentOrchestrator()
        plan = orch.create_plan("test goal")
        assert orch.get_plan(plan.plan_id) is plan

    def test_list_agents_by_role(self):
        from intelgraph.core.agent.hierarchy import AgentOrchestrator, AgentRole

        orch = AgentOrchestrator()
        planners = orch.list_agents(AgentRole.PLANNER)
        assert len(planners) >= 0


class TestDeadlockDetector:
    def test_no_cycle(self):
        from intelgraph.core.agent.hierarchy import DeadlockDetector, TaskNode

        dd = DeadlockDetector()
        tasks = [
            TaskNode(task_id="a", description="a"),
            TaskNode(task_id="b", description="b", dependencies=["a"]),
            TaskNode(task_id="c", description="c", dependencies=["b"]),
        ]
        assert dd.detect(tasks) == []

    def test_cycle_detected(self):
        from intelgraph.core.agent.hierarchy import DeadlockDetector, TaskNode

        dd = DeadlockDetector()
        tasks = [
            TaskNode(task_id="a", description="a", dependencies=["c"]),
            TaskNode(task_id="b", description="b", dependencies=["a"]),
            TaskNode(task_id="c", description="c", dependencies=["b"]),
        ]
        deadlocks = dd.detect(tasks)
        assert len(deadlocks) > 0


# ===================================================================
# Tool Execution Tests
# ===================================================================


class TestToolExecutor:
    def test_execute_rest(self):
        from intelgraph.core.agent.tools import ToolExecutor, ToolType

        executor = ToolExecutor()
        call = executor.execute(ToolType.REST, "get_data", {"url": "http://test.com"})
        assert call.success
        assert call.result is not None

    def test_execute_database(self):
        from intelgraph.core.agent.tools import ToolExecutor, ToolType

        executor = ToolExecutor()
        call = executor.execute(ToolType.DATABASE, "query", {"table": "users"})
        assert call.success
        assert "rows_affected" in call.result

    def test_execute_file(self):
        from intelgraph.core.agent.tools import ToolExecutor, ToolType

        executor = ToolExecutor()
        call = executor.execute(ToolType.FILE, "write", {"path": "/tmp/test.txt"})
        assert call.success

    def test_high_risk_needs_approval(self):
        from intelgraph.core.agent.tools import ToolExecutor, ToolType

        executor = ToolExecutor()
        call = executor.execute(ToolType.CLOUD, "delete_instance", {"instance": "i-123"})
        assert call.requires_approval

    def test_approve(self):
        from intelgraph.core.agent.tools import ToolExecutor, ToolType

        executor = ToolExecutor()
        call = executor.execute(ToolType.CLOUD, "delete_instance", {"instance": "i-123"})
        assert executor.approve(call.call_id)
        assert call.success

    def test_rollback(self):
        from intelgraph.core.agent.tools import ToolExecutor, ToolType

        executor = ToolExecutor()
        call = executor.execute(ToolType.FILE, "write", {"path": "/tmp/test.txt"})
        assert executor.rollback(call.call_id)
        assert not call.success

    def test_get_history(self):
        from intelgraph.core.agent.tools import ToolExecutor, ToolType

        executor = ToolExecutor()
        executor.execute(ToolType.INTERNAL, "ping", {})
        executor.execute(ToolType.INTERNAL, "pong", {})
        assert len(executor.get_history()) == 2

    def test_sandbox_path_traversal(self):
        from intelgraph.core.agent.tools import ToolExecutor, ToolType

        executor = ToolExecutor()
        call = executor.execute(
            ToolType.FILE, "read", {"path": "../../etc/passwd"}, sandbox="strict"
        )
        assert "../" not in str(call.params.get("path", ""))


# ===================================================================
# Reasoning Compiler Tests
# ===================================================================


class TestReasoningCompiler:
    def test_compile_hypothesis(self):
        from intelgraph.core.agent.compiler import ReasoningCompiler

        compiler = ReasoningCompiler()
        hypothesis = {
            "description": "C2 communication detected",
            "confidence": 0.7,
            "scenario_type": "command_and_control",
            "hypothesis_id": "h1",
        }
        actions = compiler.compile_hypothesis(hypothesis)
        assert len(actions) == 1
        assert actions[0].confidence == 0.7

    def test_low_confidence_skipped(self):
        from intelgraph.core.agent.compiler import ReasoningCompiler

        compiler = ReasoningCompiler({"min_execution_confidence": 0.5})
        hypothesis = {
            "description": "low confidence",
            "confidence": 0.2,
            "scenario_type": "unknown",
        }
        actions = compiler.compile_hypothesis(hypothesis)
        assert len(actions) == 0

    def test_select_best_action(self):
        from intelgraph.core.agent.compiler import CompiledAction, ReasoningCompiler

        compiler = ReasoningCompiler()
        actions = [
            CompiledAction(
                action_id="a1",
                description="high risk",
                source_hypothesis="",
                source_trace_id="",
                tool_type="rest",
                tool_action="delete",
                params={},
                risk_score=0.9,
                confidence=0.8,
                estimated_cost=1.0,
            ),
            CompiledAction(
                action_id="a2",
                description="low risk",
                source_hypothesis="",
                source_trace_id="",
                tool_type="rest",
                tool_action="read",
                params={},
                risk_score=0.2,
                confidence=0.7,
                estimated_cost=0.5,
            ),
        ]
        best = compiler.select_action(actions, "best")
        assert best.action_id == "a2"

    def test_select_safe_action(self):
        from intelgraph.core.agent.compiler import CompiledAction, ReasoningCompiler

        compiler = ReasoningCompiler()
        actions = [
            CompiledAction(
                action_id="a1",
                description="risky",
                source_hypothesis="",
                source_trace_id="",
                tool_type="rest",
                tool_action="delete",
                params={},
                risk_score=0.9,
                confidence=0.5,
                estimated_cost=1.0,
            ),
            CompiledAction(
                action_id="a2",
                description="safe",
                source_hypothesis="",
                source_trace_id="",
                tool_type="rest",
                tool_action="read",
                params={},
                risk_score=0.1,
                confidence=0.5,
                estimated_cost=0.5,
            ),
        ]
        safe = compiler.select_action(actions, "safe")
        assert safe.action_id == "a2"

    def test_generate_rollback(self):
        from intelgraph.core.agent.compiler import CompiledAction, ReasoningCompiler

        compiler = ReasoningCompiler()
        action = CompiledAction(
            action_id="act1",
            description="test",
            source_hypothesis="h1",
            source_trace_id="t1",
            tool_type="file",
            tool_action="write",
            params={"path": "/tmp/test"},
            risk_score=0.5,
            confidence=0.7,
            estimated_cost=1.0,
        )
        rollback = compiler.generate_rollback(action)
        assert rollback.action_id == action.rollback_action_id
        assert "undo" in rollback.tool_action


# ===================================================================
# Safety Governor Tests
# ===================================================================


class TestSafetyGovernor:
    def test_forbidden_action_denied(self):
        from intelgraph.core.agent.safety import SafetyGovernor

        safety = SafetyGovernor()
        result = safety.check_action("execute", "shutdown system", 0.5)
        assert not result.approved

    def test_low_risk_auto_approved(self):
        from intelgraph.core.agent.safety import SafetyGovernor

        safety = SafetyGovernor()
        result = safety.check_action("read", "get status", 0.2)
        assert result.approved

    def test_high_risk_escalates(self):
        from intelgraph.core.agent.safety import SafetyGovernor

        safety = SafetyGovernor()
        result = safety.check_action("execute", "delete database", 0.95)
        assert not result.approved

    def test_kill_switch_global(self):
        from intelgraph.core.agent.safety import SafetyGovernor

        safety = SafetyGovernor()
        safety.engage_kill_switch("global")
        result = safety.check_action("read", "anything", 0.1)
        assert not result.approved
        assert result.kill_switch_engaged

    def test_kill_switch_disengage(self):
        from intelgraph.core.agent.safety import SafetyGovernor

        safety = SafetyGovernor()
        safety.engage_kill_switch("global")
        safety.disengage_kill_switch("global")
        result = safety.check_action("read", "anything", 0.1)
        assert result.approved

    def test_kill_switch_agent(self):
        from intelgraph.core.agent.safety import SafetyGovernor

        safety = SafetyGovernor()
        safety.engage_kill_switch("agent", "agent_123")
        assert safety.is_killed(agent_id="agent_123")
        assert not safety.is_killed(agent_id="agent_456")

    def test_anomaly_detection(self):
        from intelgraph.core.agent.safety import SafetyGovernor

        safety = SafetyGovernor()
        safety.set_baseline("read", 0.2)
        safety.check_action("read", "unusual action", 0.8)
        anomalies = safety.get_anomalies()
        assert len(anomalies) >= 1

    def test_suggest_rollback(self):
        from intelgraph.core.agent.safety import SafetyGovernor

        safety = SafetyGovernor()
        entry = safety.suggest_rollback("act_123", "risk too high")
        assert entry["action_id"] == "act_123"
        assert len(safety.get_rollback_history()) == 1


# ===================================================================
# Execution Audit Tests
# ===================================================================


class TestExecutionAudit:
    def test_record(self):
        from intelgraph.core.agent.audit import ExecutionAudit

        audit = ExecutionAudit()
        entry = audit.record(
            "act_1", "agent_1", "task_1", "execute", "test action", "success", 0.5, 100.0
        )
        assert entry.action_id == "act_1"
        assert entry.immutable

    def test_get(self):
        from intelgraph.core.agent.audit import ExecutionAudit

        audit = ExecutionAudit()
        entry = audit.record("act_1", "agent_1", "task_1", "execute", "test", "success", 0.5, 100.0)
        assert audit.get(entry.entry_id).entry_id == entry.entry_id

    def test_query_by_action(self):
        from intelgraph.core.agent.audit import ExecutionAudit

        audit = ExecutionAudit()
        audit.record("act_1", "agent_1", "task_1", "execute", "test", "success", 0.5, 100.0)
        audit.record("act_2", "agent_2", "task_2", "read", "test2", "success", 0.2, 50.0)
        results = audit.query(action_id="act_1")
        assert len(results) == 1

    def test_reconstruct_execution_graph(self):
        from intelgraph.core.agent.audit import ExecutionAudit

        audit = ExecutionAudit()
        audit.record("act_1", "agent_1", "task_1", "execute", "step1", "success", 0.5, 100.0)
        audit.record("act_2", "agent_2", "task_1", "verify", "step2", "success", 0.3, 50.0)
        graph = audit.reconstruct_execution_graph("task_1")
        assert len(graph) == 2

    def test_failure_root_cause(self):
        from intelgraph.core.agent.audit import ExecutionAudit

        audit = ExecutionAudit()
        audit.record(
            "act_1", "agent_1", "task_1", "execute", "step1", "failed", 0.5, 100.0, error="timeout"
        )
        rc = audit.failure_root_cause("task_1")
        assert rc["root_cause"] == "timeout"


# ===================================================================
# Execution Feedback Loop Tests
# ===================================================================


class TestExecutionFeedbackLoop:
    def test_record_outcome(self):
        from intelgraph.core.agent.feedback import ExecutionFeedbackLoop

        fb = ExecutionFeedbackLoop()
        outcome = fb.record_outcome("task_1", True, 0.8, 100.0)
        assert outcome.success
        assert outcome.task_id == "task_1"

    def test_performance_score(self):
        from intelgraph.core.agent.feedback import ExecutionFeedbackLoop

        fb = ExecutionFeedbackLoop()
        fb.record_outcome("task_1", True, 0.8, 100.0)
        fb.record_outcome("task_1", False, 0.3, 200.0)
        fb.record_outcome("task_1", True, 0.9, 50.0)
        score = fb.execution_performance_score("task_1")
        assert 0.0 < score <= 1.0

    def test_overall_success_rate(self):
        from intelgraph.core.agent.feedback import ExecutionFeedbackLoop

        fb = ExecutionFeedbackLoop()
        fb.record_outcome("t1", True, 0.8, 100.0)
        fb.record_outcome("t2", True, 0.9, 50.0)
        fb.record_outcome("t3", False, 0.2, 200.0)
        rate = fb.overall_success_rate()
        assert rate == 2.0 / 3.0

    def test_adaptive_policy_tune(self):
        from intelgraph.core.agent.feedback import ExecutionFeedbackLoop

        fb = ExecutionFeedbackLoop()
        w = fb.adaptive_policy_tune("risk_weight", 0.8)
        assert 0.5 < w < 0.6

    def test_weak_signals(self):
        from intelgraph.core.agent.feedback import ExecutionFeedbackLoop

        fb = ExecutionFeedbackLoop()
        fb.record_outcome("t1", False, 0.5, 100.0, error="timeout")
        fb.record_outcome("t2", False, 0.6, 150.0, error="timeout")
        signals = fb.get_weak_signals(min_frequency=2)
        assert len(signals) >= 1


# ===================================================================
# Simulation Engine Tests
# ===================================================================


class TestSimulationEngine:
    def test_simulate(self):
        from intelgraph.core.agent.simulation import SimulationEngine

        sim = SimulationEngine()
        result = sim.simulate("test goal", {"sub_tasks": [{"risk": 0.3}, {"risk": 0.5}]})
        assert result.status.value == "completed"
        assert 0.0 <= result.success_probability <= 1.0

    def test_what_if_scenarios(self):
        from intelgraph.core.agent.simulation import SimulationEngine

        sim = SimulationEngine()
        what_if = [{"perturbation": "network_delay"}, {"perturbation": "node_failure"}]
        result = sim.simulate("test", {"sub_tasks": []}, what_if)
        assert len(result.what_if_results) == 2

    def test_chaos_resilience(self):
        from intelgraph.core.agent.simulation import SimulationEngine

        sim = SimulationEngine()
        result = sim.simulate("test", {"sub_tasks": []})
        assert 0.0 <= result.chaos_resilience <= 1.0


class TestChaosInjector:
    def test_inject_failure(self):
        from intelgraph.core.agent.simulation import ChaosInjector

        injector = ChaosInjector({"chaos_enabled": True, "failure_rates": {"network": 1.0}})
        result = injector.inject_failure()
        assert result["injected"]


# ===================================================================
# Distributed Execution Tests
# ===================================================================


class TestSharedWorkQueue:
    def test_push_and_pop(self):
        from intelgraph.core.agent.distributed import SharedWorkQueue

        q = SharedWorkQueue()
        q.push("task_1", priority=5)
        q.push("task_2", priority=1)
        task = q.pop()
        assert task.task_id == "task_1"
        task2 = q.pop()
        assert task2.task_id == "task_2"

    def test_complete(self):
        from intelgraph.core.agent.distributed import SharedWorkQueue

        q = SharedWorkQueue()
        q.push("task_1")
        q.pop()
        q.complete("task_1", True)
        assert q.stats()["completed"] == 1

    def test_requeue(self):
        from intelgraph.core.agent.distributed import SharedWorkQueue

        q = SharedWorkQueue()
        q.push("task_1")
        q.pop()
        assert q.requeue("task_1")
        assert q.stats()["pending"] >= 1

    def test_peek(self):
        from intelgraph.core.agent.distributed import SharedWorkQueue

        q = SharedWorkQueue()
        q.push("a", 1)
        q.push("b", 2)
        q.push("c", 3)
        pending = q.peek(2)
        assert len(pending) >= 1


class TestMultiNodeOrchestrator:
    def test_register_node(self):
        from intelgraph.core.agent.distributed import MultiNodeOrchestrator

        orch = MultiNodeOrchestrator()
        node = orch.register_node("localhost", 8080)
        assert node.host == "localhost"
        assert node.healthy

    def test_heartbeat(self):
        from intelgraph.core.agent.distributed import MultiNodeOrchestrator

        orch = MultiNodeOrchestrator()
        node = orch.register_node("localhost", 8080)
        assert orch.heartbeat(node.node_id)

    def test_route_task(self):
        from intelgraph.core.agent.distributed import MultiNodeOrchestrator

        orch = MultiNodeOrchestrator()
        orch.register_node("host1", 8080)
        orch.register_node("host2", 8081)
        node_id = orch.route_task("task_1")
        assert node_id is not None


class TestRetryWithBackoff:
    def test_success(self):
        from intelgraph.core.agent.distributed import RetryWithBackoff

        rb = RetryWithBackoff(max_attempts=3)
        result = rb.execute(lambda x: x + 1, 5)
        assert result == 6

    def test_retry_on_failure(self):
        from intelgraph.core.agent.distributed import RetryWithBackoff

        rb = RetryWithBackoff(max_attempts=3, base_delay=0.01)
        call_count = [0]

        def flaky(x):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("transient")
            return x

        result = rb.execute(flaky, 42)
        assert result == 42
        assert call_count[0] == 3

    def test_exhaust_retries(self):
        from intelgraph.core.agent.distributed import RetryWithBackoff

        rb = RetryWithBackoff(max_attempts=2, base_delay=0.01)

        def always_fail():
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError):
            rb.execute(always_fail)


class TestLoadBalancer:
    def test_round_robin(self):
        from intelgraph.core.agent.distributed import LoadBalancer

        lb = LoadBalancer()
        nodes = ["a", "b", "c"]
        assert lb.select_node(nodes, "round_robin") == "a"
        assert lb.select_node(nodes, "round_robin") == "b"
        assert lb.select_node(nodes, "round_robin") == "c"

    def test_least_loaded(self):
        from intelgraph.core.agent.distributed import LoadBalancer

        lb = LoadBalancer()

        class FakeNode:
            def __init__(self, name, load):
                self.name = name
                self.load = load

        nodes = [FakeNode("a", 0.8), FakeNode("b", 0.2), FakeNode("c", 0.5)]
        selected = lb.select_node(nodes, "least_loaded")
        assert selected.name == "b"

    def test_empty_nodes(self):
        from intelgraph.core.agent.distributed import LoadBalancer

        lb = LoadBalancer()
        assert lb.select_node([], "round_robin") is None


# ===================================================================
# Execution Memory Tests
# ===================================================================


class TestExecutionMemory:
    def test_store_and_recall(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory()
        mem.store("entity_1", "ip", "192.168.1.1", "suspicious")
        records = mem.recall("entity_1", "ip")
        assert len(records) == 1
        assert records[0].value == "192.168.1.1"

    def test_forget(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory()
        mem.store("e1", "key1", "val1", "ok")
        mem.store("e1", "key2", "val2", "ok")
        assert mem.forget("e1", "key1") == 1
        assert len(mem.recall("e1")) == 1

    def test_forget_all(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory()
        mem.store("e1", "k1", "v1", "ok")
        mem.store("e1", "k2", "v2", "ok")
        assert mem.forget("e1") == 2

    def test_ttl_expiry(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory({"memory_ttl": -1})
        mem.store("e1", "k1", "v1", "ok")
        assert len(mem.recall("e1")) == 0

    def test_record_behavior(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory()
        rec = mem.record_behavior("agent_1", "execute", "success", 100.0)
        assert rec.agent_id == "agent_1"
        assert len(mem.get_behaviors()) == 1

    def test_knowledge(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory()
        mem.know("success_rate", 0.85)
        assert mem.know("success_rate") == 0.85

    def test_learn_pattern(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory()
        mem.learn_pattern(["discover", "analyze", "report"], 0.9)
        assert mem.know("discover->analyze->report") == 0.9

    def test_best_params(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory()
        mem.store_best_params("scan", {"depth": 5, "timeout": 30})
        params = mem.get_best_params("scan")
        assert params["depth"] == 5

    def test_replay_failures(self):
        from intelgraph.core.agent.memory import ExecutionMemory

        mem = ExecutionMemory()
        mem.record_behavior("agent_1", "scan", "success", 50.0)
        mem.record_behavior("agent_1", "execute", "failure", 200.0)
        failures = mem.replay_failures()
        assert len(failures) == 1


# ===================================================================
# CLI Agent Tests
# ===================================================================


class TestCLIAgentCommands:
    def test_command_names(self):
        from intelgraph.cli.agent import agent_group

        assert agent_group.name == "agent"
        commands = [cmd.name for cmd in agent_group.commands.values()]
        expected = [
            "plan",
            "execute",
            "rollback",
            "submit",
            "status",
            "validate",
            "simulate",
            "replay",
            "kill-switch",
            "config",
            "audit",
            "memory",
        ]
        for cmd in expected:
            assert cmd in commands, f"Missing command: {cmd}"

    def test_plan_command_invoke(self):
        from click.testing import CliRunner

        from intelgraph.cli.agent import plan

        runner = CliRunner()
        result = runner.invoke(plan, ["investigate anomaly"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "plan_id" in data
        assert data["goal"] == "investigate anomaly"

    def test_execute_command_invoke(self):
        from click.testing import CliRunner

        from intelgraph.cli.agent import execute

        runner = CliRunner()
        result = runner.invoke(execute, ["investigate", "--sandbox", "medium"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "plan_id" in data

    def test_simulate_command(self):
        from click.testing import CliRunner

        from intelgraph.cli.agent import simulate

        runner = CliRunner()
        result = runner.invoke(simulate, ["test goal"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "simulation_id" in data

    def test_kill_switch_command(self):
        from click.testing import CliRunner

        from intelgraph.cli.agent import kill_switch

        runner = CliRunner()
        result = runner.invoke(kill_switch, ["--scope", "global", "--disengage"])
        assert result.exit_code == 0


# ===================================================================
# API Agent Tests
# ===================================================================


class TestAPIAgentEndpoints:
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
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_create_plan(self):
        headers = self._auth_headers()
        resp = self.client.post("/agent/plan", json={"goal": "investigate"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "plan_id" in data
        assert data["goal"] == "investigate"

    def test_execute_goal(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/agent/execute", json={"goal": "run analysis", "sandbox": "light"}, headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "plan_id" in data

    def test_submit_task(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/agent/task/submit", json={"goal": "scan", "priority": 3}, headers=headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "task_id" in data

    def test_simulate(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/agent/simulate", json={"goal": "investigate", "chaos": False}, headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "simulation_id" in data

    def test_validate_empty(self):
        headers = self._auth_headers()
        resp = self.client.post("/agent/validate/execution", json={}, headers=headers)
        assert resp.status_code == 200

    def test_kill_switch_admin(self):
        headers = self._auth_headers("admin")
        resp = self.client.post("/agent/kill-switch", json={"scope": "global"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "kill_switch_engaged"

    def test_kill_switch_disengage(self):
        headers = self._auth_headers("admin")
        resp = self.client.post(
            "/agent/kill-switch", json={"scope": "global", "disengage": True}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "kill_switch_disengaged"

    def test_kill_switch_unauthorized(self):
        headers = self._auth_headers("user")
        resp = self.client.post("/agent/kill-switch", json={"scope": "global"}, headers=headers)
        assert resp.status_code == 403

    def test_config(self):
        headers = self._auth_headers()
        resp = self.client.get("/agent/config", headers=headers)
        assert resp.status_code == 200
        assert "forbidden_actions" in resp.json()

    def test_audit(self):
        headers = self._auth_headers()
        resp = self.client.get("/agent/audit", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data

    def test_feedback(self):
        headers = self._auth_headers()
        resp = self.client.post(
            "/agent/feedback",
            json={
                "task_id": "task_1",
                "success": True,
                "confidence": 0.9,
                "duration_ms": 100,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_memory(self):
        headers = self._auth_headers()
        resp = self.client.get("/agent/memory/entity_1", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "records" in data

    def test_plan_empty_goal(self):
        headers = self._auth_headers()
        resp = self.client.post("/agent/plan", json={"goal": ""}, headers=headers)
        assert resp.status_code == 422

    def test_execute_missing_goal(self):
        headers = self._auth_headers()
        resp = self.client.post("/agent/execute", json={}, headers=headers)
        assert resp.status_code == 422

    def test_replay_nonexistent(self):
        headers = self._auth_headers()
        resp = self.client.post("/agent/replay", json={"trace_id": "nonexistent"}, headers=headers)
        assert resp.status_code == 404

    def test_task_status_nonexistent(self):
        headers = self._auth_headers()
        resp = self.client.get("/agent/task/status/nonexistent", headers=headers)
        assert resp.status_code == 404
