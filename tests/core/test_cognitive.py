from __future__ import annotations

# ===================================================================
# Reasoning Engine Tests
# ===================================================================


class TestReasoningEngine:
    def test_multi_hop_no_graph(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine

        engine = ReasoningEngine()
        paths = engine.multi_hop_reason("A", "B")
        assert paths == []

    def test_multi_hop_with_graph(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine

        engine = ReasoningEngine()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "adjacency": {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}, "D": set()},
                "forward_adjacency": {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}, "D": set()},
            },
        )()
        engine.set_graph(mock_graph)
        paths = engine.multi_hop_reason("A", "D", max_depth=5)
        assert len(paths) >= 1
        for p in paths:
            assert p.start_node == "A"
            assert p.end_node == "D"

    def test_causal_inference(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine

        engine = ReasoningEngine()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "adjacency": {"X": {"Y"}, "Y": {"Z"}, "Z": set()},
                "forward_adjacency": {"X": {"Y"}, "Y": {"Z"}, "Z": set()},
            },
        )()
        engine.set_graph(mock_graph)
        paths = engine.causal_inference("X", max_depth=3)
        assert len(paths) >= 1

    def test_temporal_reason(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine

        engine = ReasoningEngine()
        events = [
            {"entity": "A", "event_type": "login", "timestamp": "2024-01-01T00:00:00Z"},
            {"entity": "B", "event_type": "access", "timestamp": "2024-01-01T01:00:00Z"},
            {"entity": "C", "event_type": "exfiltrate", "timestamp": "2024-01-01T02:00:00Z"},
        ]
        paths = engine.temporal_reason(events)
        assert len(paths) == 2
        assert all(p.steps[0].step_type == "temporal" for p in paths)

    def test_probabilistic_reason(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine

        engine = ReasoningEngine()
        relations = [("B", "causes", 0.8), ("C", "leads_to", 0.6)]
        path = engine.probabilistic_reason("A", relations)
        assert path.start_node == "A"
        assert path.end_node == "C"
        assert len(path.steps) == 2
        assert 0 < path.total_confidence < 1

    def test_evidence_weighted_score(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine

        engine = ReasoningEngine()
        relations = [("B", "causes", 0.9)]
        path = engine.probabilistic_reason("A", relations)
        score = engine.evidence_weighted_score(path)
        assert 0 < score <= 1

    def test_get_traces(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine

        engine = ReasoningEngine()
        engine.probabilistic_reason("A", [("B", "rel", 0.5)])
        traces = engine.get_traces()
        assert len(traces) >= 1

    def test_get_trace_by_id(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine

        engine = ReasoningEngine()
        path = engine.probabilistic_reason("A", [("B", "rel", 0.5)])
        found = engine.get_trace(path.path_id)
        assert found is not None
        assert found.path_id == path.path_id

    def test_reasoning_step_uncertainty(self):
        from intelgraph.core.cognitive.reasoning import ReasoningStep

        step = ReasoningStep(
            step_id="s1",
            source_node="A",
            target_node="B",
            relation="connects",
            confidence=0.8,
            evidence=["test"],
            uncertainty=0.2,
            step_type="direct",
        )
        d = step.to_dict()
        assert d["confidence"] == 0.8
        assert d["uncertainty"] == 0.2


# ===================================================================
# Contradiction Detection Tests
# ===================================================================


class TestContradictionDetector:
    def test_detect_contradiction(self):
        from intelgraph.core.cognitive.contradiction import ContradictionDetector

        detector = ContradictionDetector({"contradiction_confidence_threshold": 0.3})
        facts = [
            {"entity": "IP_1", "attribute": "reputation", "value": 90, "confidence": 0.8},
            {"entity": "IP_1", "attribute": "reputation", "value": 10, "confidence": 0.8},
        ]
        contradictions = detector.detect(facts)
        assert len(contradictions) == 1
        assert contradictions[0].contradiction_type == "attribute_mismatch"

    def test_no_contradiction_matching_values(self):
        from intelgraph.core.cognitive.contradiction import ContradictionDetector

        detector = ContradictionDetector()
        facts = [
            {"entity": "IP_1", "attribute": "reputation", "value": 90, "confidence": 0.8},
            {"entity": "IP_1", "attribute": "reputation", "value": 90, "confidence": 0.8},
        ]
        contradictions = detector.detect(facts)
        assert len(contradictions) == 0

    def test_contradiction_rate(self):
        from intelgraph.core.cognitive.contradiction import ContradictionDetector

        detector = ContradictionDetector({"contradiction_confidence_threshold": 0.3})
        detector.detect(
            [
                {"entity": "E1", "attribute": "score", "value": 100, "confidence": 0.9},
                {"entity": "E1", "attribute": "score", "value": 0, "confidence": 0.9},
            ]
        )
        rate = detector.contradiction_rate()
        assert rate == 0.0

    def test_resolve_contradiction(self):
        from intelgraph.core.cognitive.contradiction import ContradictionDetector

        detector = ContradictionDetector({"contradiction_confidence_threshold": 0.3})
        detector.detect(
            [
                {"entity": "E1", "attribute": "score", "value": 100, "confidence": 0.9},
                {"entity": "E1", "attribute": "score", "value": 0, "confidence": 0.9},
            ]
        )
        cid = detector.get_all()[0].contradiction_id
        assert detector.resolve(cid, "accepted_first")
        assert detector.get_all()[0].resolution == "accepted_first"

    def test_different_entities_no_contradiction(self):
        from intelgraph.core.cognitive.contradiction import ContradictionDetector

        detector = ContradictionDetector({"contradiction_confidence_threshold": 0.3})
        facts = [
            {"entity": "E1", "attribute": "score", "value": 100, "confidence": 0.9},
            {"entity": "E2", "attribute": "score", "value": 0, "confidence": 0.9},
        ]
        contradictions = detector.detect(facts)
        assert len(contradictions) == 0

    def test_low_confidence_skipped(self):
        from intelgraph.core.cognitive.contradiction import ContradictionDetector

        detector = ContradictionDetector({"contradiction_confidence_threshold": 0.8})
        facts = [
            {"entity": "E1", "attribute": "score", "value": 100, "confidence": 0.5},
            {"entity": "E1", "attribute": "score", "value": 0, "confidence": 0.5},
        ]
        contradictions = detector.detect(facts)
        assert len(contradictions) == 0


# ===================================================================
# Hypothesis Generation Tests
# ===================================================================


class TestHypothesisGenerator:
    def test_generate_no_graph(self):
        from intelgraph.core.cognitive.hypothesis import HypothesisGenerator

        gen = HypothesisGenerator()
        hypotheses = gen.generate()
        assert hypotheses == []

    def test_generate_with_graph(self):
        from intelgraph.core.cognitive.hypothesis import HypothesisGenerator

        gen = HypothesisGenerator()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "nodes": {"A": {}, "B": {}, "C": {}},
                "edges": {"e1": {}},
                "adjacency": {"A": {"B"}, "B": {"C"}, "C": set()},
            },
        )()
        hypotheses = gen.generate(mock_graph)
        assert len(hypotheses) >= 1
        assert all(h.status == "active" for h in hypotheses)

    def test_hypothesis_score_ordering(self):
        from intelgraph.core.cognitive.hypothesis import HypothesisGenerator

        gen = HypothesisGenerator()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "nodes": {"A": {}, "B": {}, "C": {}, "D": {}, "E": {}},
                "edges": {"e1": {}, "e2": {}},
                "adjacency": {"A": {"B"}, "B": {"C"}, "C": {"D"}, "D": {"E"}, "E": set()},
            },
        )()
        hypotheses = gen.generate(mock_graph)
        if len(hypotheses) > 1:
            for i in range(len(hypotheses) - 1):
                assert hypotheses[i].score >= hypotheses[i + 1].score

    def test_get_active_hypotheses(self):
        from intelgraph.core.cognitive.hypothesis import HypothesisGenerator

        gen = HypothesisGenerator()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "nodes": {"A": {}, "B": {}},
                "edges": {"e1": {}},
                "adjacency": {"A": {"B"}, "B": set()},
            },
        )()
        gen.generate(mock_graph)
        active = gen.get_active()
        assert len(active) >= 1

    def test_validate_hypothesis(self):
        from intelgraph.core.cognitive.hypothesis import HypothesisGenerator

        gen = HypothesisGenerator()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "nodes": {"A": {}, "B": {}},
                "edges": {"e1": {}},
                "adjacency": {"A": {"B"}, "B": set()},
            },
        )()
        gen.generate(mock_graph)
        active = gen.get_active()
        if active:
            assert gen.validate(active[0].hypothesis_id, 0.9)
            assert gen.get(active[0].hypothesis_id).confidence == 0.9

    def test_alternative_interpretations(self):
        from intelgraph.core.cognitive.hypothesis import HypothesisGenerator

        gen = HypothesisGenerator()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "nodes": {"A": {}, "B": {}},
                "edges": {"e1": {}},
                "adjacency": {"A": {"B"}, "B": set()},
            },
        )()
        hypotheses = gen.generate(mock_graph)
        if hypotheses:
            assert len(hypotheses[0].alternative_interpretations) >= 1


# ===================================================================
# Self-Learning Loop Tests
# ===================================================================


class TestSelfLearningLoop:
    def test_ingest_feedback(self):
        from intelgraph.core.cognitive.learning import SelfLearningLoop

        loop = SelfLearningLoop()
        entry = loop.ingest_feedback(
            "q1", "analyst_1", "correction", 0.8, {"fix": "x"}, {"original": "y"}
        )
        assert entry.feedback_type == "correction"
        assert entry.applied

    def test_reinforcement_score(self):
        from intelgraph.core.cognitive.learning import SelfLearningLoop

        loop = SelfLearningLoop()
        score = loop.reinforcement_score(8, 10)
        assert score > 0

    def test_improvement_rate(self):
        from intelgraph.core.cognitive.learning import SelfLearningLoop

        loop = SelfLearningLoop()
        loop.reinforcement_score(8, 10)
        loop.reinforcement_score(9, 10)
        loop.reinforcement_score(10, 10)
        rate = loop.improvement_rate()
        assert isinstance(rate, float)

    def test_mean_improvement(self):
        from intelgraph.core.cognitive.learning import SelfLearningLoop

        loop = SelfLearningLoop()
        loop.reinforcement_score(5, 10)
        loop.reinforcement_score(8, 10)
        mean = loop.mean_improvement()
        assert mean > 0

    def test_adaptive_model_select(self):
        from intelgraph.core.cognitive.learning import SelfLearningLoop

        loop = SelfLearningLoop()
        loop.record_model_performance("model_a", "ner", 0.9, 0.85, 0.88)
        loop.record_model_performance("model_b", "ner", 0.7, 0.65, 0.7)
        models = [{"model_id": "model_a", "task": "ner"}, {"model_id": "model_b", "task": "ner"}]
        selected = loop.adaptive_model_select("ner", models)
        assert selected == "model_a"

    def test_weak_signal_learning(self):
        from intelgraph.core.cognitive.learning import SelfLearningLoop

        loop = SelfLearningLoop()
        loop.learn_weak_signal({"pattern": "unusual_login", "frequency": 3})
        signals = loop.get_weak_signals()
        assert len(signals) == 1


# ===================================================================
# Trace System Tests
# ===================================================================


class TestTraceSystem:
    def test_record_and_get(self):
        from intelgraph.core.cognitive.trace import TraceSystem

        ts = TraceSystem()
        entry = ts.record("A -> B", [{"step": 1, "confidence": 0.8}], [], ["evidence"], 0.8)
        assert ts.get(entry.trace_id) is not None

    def test_list_traces(self):
        from intelgraph.core.cognitive.trace import TraceSystem

        ts = TraceSystem()
        ts.record("Q1", [{"step": 1}], [], ["ev"], 0.5)
        ts.record("Q2", [{"step": 1}], [], ["ev"], 0.7)
        traces = ts.list()
        assert len(traces) == 2

    def test_trace_not_found(self):
        from intelgraph.core.cognitive.trace import TraceSystem

        ts = TraceSystem()
        assert ts.get("nonexistent") is None

    def test_query_traces(self):
        from intelgraph.core.cognitive.trace import TraceSystem

        ts = TraceSystem()
        ts.record("attack path analysis", [{"step": 1}], [], ["ev"], 0.5)
        ts.record("normal query", [{"step": 1}], [], ["ev"], 0.5)
        results = ts.query_traces("attack", 10)
        assert len(results) == 1
        assert "attack" in results[0].query


# ===================================================================
# Continuous Optimizer Tests
# ===================================================================


class TestContinuousOptimizer:
    def test_update_accuracy(self):
        from intelgraph.core.cognitive.optimization import ContinuousOptimizer

        opt = ContinuousOptimizer()
        acc = opt.update_accuracy(9, 10)
        assert acc == 0.9

    def test_optimize_routing(self):
        from intelgraph.core.cognitive.optimization import ContinuousOptimizer

        opt = ContinuousOptimizer()
        opt.record_optimization(
            type(
                "OM",
                (),
                {
                    "extraction_accuracy": 0.8,
                    "model_routing_efficiency": 0.7,
                    "reasoning_cost": 0.5,
                    "throughput": 100,
                    "drift_score": 0.05,
                    "threshold_sensitivity": 0.5,
                },
            )()
        )
        routing = opt.optimize_routing(
            [
                {"model_id": "m1", "task": "ner", "accuracy": 0.9, "cost": 0.5},
            ]
        )
        assert "ner" in routing

    def test_detect_drift(self):
        from intelgraph.core.cognitive.optimization import ContinuousOptimizer, OptimizationMetrics

        opt = ContinuousOptimizer()
        for i in range(15):
            opt.record_optimization(
                OptimizationMetrics(
                    extraction_accuracy=0.8 + (i % 5) * 0.05,
                    model_routing_efficiency=0.7,
                    reasoning_cost=0.5,
                    throughput=100,
                    drift_score=0.05,
                    threshold_sensitivity=0.5,
                )
            )
        drift = opt.detect_drift()
        assert drift >= 0

    def test_auto_tune_threshold(self):
        from intelgraph.core.cognitive.optimization import ContinuousOptimizer

        opt = ContinuousOptimizer()
        tuned = opt.auto_tune_threshold("anomaly_zscore", 2.5)
        assert tuned is not None

    def test_get_drift_report(self):
        from intelgraph.core.cognitive.optimization import ContinuousOptimizer

        opt = ContinuousOptimizer()
        report = opt.get_drift_report()
        assert "drift_score" in report
        assert "thresholds" in report


# ===================================================================
# Full Pipeline Integration Tests
# ===================================================================


class TestCognitiveIntegration:
    def test_reasoning_to_trace_pipeline(self):
        from intelgraph.core.cognitive.reasoning import ReasoningEngine
        from intelgraph.core.cognitive.trace import TraceSystem

        engine = ReasoningEngine()
        trace = TraceSystem()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "adjacency": {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}, "D": set()},
                "forward_adjacency": {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}, "D": set()},
            },
        )()
        engine.set_graph(mock_graph)
        paths = engine.multi_hop_reason("A", "D")
        for p in paths:
            trace.record(
                f"{p.start_node} -> {p.end_node}",
                [s.to_dict() for s in p.steps],
                [[alt.to_dict()] for alt in p.alternatives],
                p.evidence_chain,
                p.score,
            )
        assert len(trace.list()) > 0

    def test_hypothesis_and_validation(self):
        from intelgraph.core.cognitive.hypothesis import HypothesisGenerator

        gen = HypothesisGenerator()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "nodes": {"X": {}, "Y": {}},
                "edges": {"e1": {}},
                "adjacency": {"X": {"Y"}, "Y": set()},
            },
        )()
        hypotheses = gen.generate(mock_graph)
        if hypotheses:
            h = hypotheses[0]
            assert gen.validate(h.hypothesis_id, 0.95)
            validated = gen.get(h.hypothesis_id)
            assert validated.confidence == 0.95

    def test_contradiction_and_resolution(self):
        from intelgraph.core.cognitive.contradiction import ContradictionDetector

        detector = ContradictionDetector({"contradiction_confidence_threshold": 0.3})
        facts = [
            {"entity": "IP_X", "attribute": "trust", "value": 100, "confidence": 0.9},
            {"entity": "IP_X", "attribute": "trust", "value": 0, "confidence": 0.9},
        ]
        contradictions = detector.detect(facts)
        assert len(contradictions) == 1
        assert detector.resolve(contradictions[0].contradiction_id, "resolved")
        assert detector.get_all()[0].resolution == "resolved"

    def test_learning_with_feedback(self):
        from intelgraph.core.cognitive.learning import SelfLearningLoop

        loop = SelfLearningLoop()
        loop.ingest_feedback(
            "q1", "analyst", "correction", 0.9, {"correct": "val"}, {"original": "wrong"}
        )
        loop.ingest_feedback(
            "q2", "analyst", "correction", 0.7, {"correct": "val"}, {"original": "wrong"}
        )
        im = loop.improvement_rate()
        assert isinstance(im, float)

    def test_full_cognitive_pipeline(self):
        from intelgraph.core.cognitive.contradiction import ContradictionDetector
        from intelgraph.core.cognitive.hypothesis import HypothesisGenerator
        from intelgraph.core.cognitive.learning import SelfLearningLoop
        from intelgraph.core.cognitive.optimization import ContinuousOptimizer
        from intelgraph.core.cognitive.reasoning import ReasoningEngine
        from intelgraph.core.cognitive.trace import TraceSystem

        engine = ReasoningEngine()
        detector = ContradictionDetector()
        gen = HypothesisGenerator()
        loop = SelfLearningLoop()
        trace = TraceSystem()
        opt = ContinuousOptimizer()
        mock_graph = type(
            "MockGraph",
            (),
            {
                "nodes": {"A": {}, "B": {}, "C": {}},
                "edges": {"e1": {}, "e2": {}},
                "adjacency": {"A": {"B"}, "B": {"C"}, "C": set()},
                "forward_adjacency": {"A": {"B"}, "B": {"C"}, "C": set()},
            },
        )()
        engine.set_graph(mock_graph)
        paths = engine.multi_hop_reason("A", "C")
        assert len(paths) >= 1
        for p in paths:
            trace.record(
                f"{p.start_node} -> {p.end_node}",
                [s.to_dict() for s in p.steps],
                [],
                p.evidence_chain,
                p.score,
            )
        hypotheses = gen.generate(mock_graph)
        assert len(hypotheses) >= 1
        loop.ingest_feedback("test", "analyst", "correction", 0.85, {}, {})
        opt.update_accuracy(8, 10)
        contradictions = detector.detect(
            [
                {"entity": "E", "attribute": "val", "value": 10, "confidence": 0.9},
                {"entity": "E", "attribute": "val", "value": 20, "confidence": 0.9},
            ]
        )
        assert len(trace.list()) >= 1
        assert len(contradictions) >= 1
        assert loop.mean_improvement() > 0
