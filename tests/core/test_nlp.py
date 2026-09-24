from __future__ import annotations

import time

from intelgraph.core.nlp.sanitizer import InputSanitizer, OutputSanitizer

# ===================================================================
# NER Engine Tests
# ===================================================================


class TestNEREngine:
    def test_ip_extraction(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = "The attacker IP 192.168.1.1 was observed communicating with 10.0.0.5."
        entities = ner.extract(text)
        ips = [e.to_dict() for e in entities if e.label == "IP"]
        assert len(ips) >= 2
        assert ips[0]["text"] == "192.168.1.1"
        assert ips[1]["text"] == "10.0.0.5"

    def test_domain_extraction(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = "C2 traffic directed to malicious.example.com and evil.org."
        entities = ner.extract(text)
        domains = [e.to_dict() for e in entities if e.label == "DOMAIN"]
        assert len(domains) >= 2
        assert "malicious.example.com" in [d["text"] for d in domains]

    def test_cve_extraction(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = "The vulnerability CVE-2024-1234 was exploited. Also CVE-2023-98765."
        entities = ner.extract(text)
        cves = [e.to_dict() for e in entities if e.label == "CVE"]
        assert len(cves) == 2
        assert cves[0]["text"] == "CVE-2024-1234"

    def test_malware_extraction(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = "The ransomware attack used a new trojan variant. A backdoor was also deployed."
        entities = ner.extract(text)
        malwares = [e.to_dict() for e in entities if e.label == "MALWARE"]
        labels = [m["text"].lower() for m in malwares]
        assert "ransomware" in labels
        assert "trojan" in labels
        assert "backdoor" in labels

    def test_entity_confidence(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = "CVE-2024-5678 is critical."
        entities = ner.extract(text)
        assert len(entities) == 1
        assert entities[0].confidence >= 0.9

    def test_empty_text(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        assert ner.extract("") == []

    def test_multiple_entity_types(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = "Attacker at 10.0.0.1 used CVE-2024-1234 to deploy ransomware on target.com."
        entities = ner.extract(text)
        labels = {e.label for e in entities}
        assert "IP" in labels
        assert "CVE" in labels
        assert "MALWARE" in labels
        assert "DOMAIN" in labels

    def test_email_extraction(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = "Contact threat@intel.com for reporting."
        entities = ner.extract(text)
        emails = [e for e in entities if e.label == "EMAIL"]
        assert len(emails) == 1
        assert emails[0].text == "threat@intel.com"


# ===================================================================
# Relationship Extraction Tests
# ===================================================================


class TestRelationshipExtractor:
    def test_basic_relationship(self):
        from intelgraph.core.nlp.extractor import NEREngine, RelationshipExtractor

        ner = NEREngine()
        rel_extractor = RelationshipExtractor()
        text = "192.168.1.1 connected to malicious.example.com."
        entities = ner.extract(text)
        relationships = rel_extractor.extract(text, entities)
        assert len(relationships) >= 1
        assert relationships[0].relation == "connects_to"

    def test_ownership_relationship(self):
        from intelgraph.core.nlp.extractor import NEREngine, RelationshipExtractor

        ner = NEREngine()
        rel_extractor = RelationshipExtractor()
        text = "evil.org owns c2.example.com."
        entities = ner.extract(text)
        relationships = rel_extractor.extract(text, entities)
        assert len(relationships) >= 1

    def test_no_entities_no_relationships(self):
        from intelgraph.core.nlp.extractor import RelationshipExtractor

        rel_extractor = RelationshipExtractor()
        text = "The system was impacted."
        relationships = rel_extractor.extract(text)
        assert relationships == []

    def test_relationship_confidence(self):
        from intelgraph.core.nlp.extractor import NEREngine, RelationshipExtractor

        ner = NEREngine()
        rel_extractor = RelationshipExtractor()
        text = "IP 10.0.0.1 targets example.com."
        entities = ner.extract(text)
        relationships = rel_extractor.extract(text, entities)
        if relationships:
            assert 0 <= relationships[0].confidence <= 1

    def test_contains_relationship(self):
        from intelgraph.core.nlp.extractor import NEREngine, RelationshipExtractor

        ner = NEREngine()
        rel_extractor = RelationshipExtractor()
        text = "The malware ransomware contains a backdoor component."
        entities = ner.extract(text)
        relationships = rel_extractor.extract(text, entities)
        if relationships:
            assert relationships[0].relation == "contains"


# ===================================================================
# Event Extraction Tests
# ===================================================================


class TestEventExtractor:
    def test_breach_event(self):
        from intelgraph.core.nlp.extractor import EventExtractor, NEREngine

        ner = NEREngine()
        event_extractor = EventExtractor()
        text = "The organization suffered a data breach exposing customer data."
        entities = ner.extract(text)
        events = event_extractor.extract(text, entities)
        types = [e.event_type for e in events]
        assert "breach" in types

    def test_infection_event(self):
        from intelgraph.core.nlp.extractor import EventExtractor, NEREngine

        ner = NEREngine()
        event_extractor = EventExtractor()
        text = "Systems infected with ransomware trojan variant."
        entities = ner.extract(text)
        events = event_extractor.extract(text, entities)
        types = [e.event_type for e in events]
        assert "infection" in types

    def test_phishing_event(self):
        from intelgraph.core.nlp.extractor import EventExtractor, NEREngine

        ner = NEREngine()
        event_extractor = EventExtractor()
        text = "A sophisticated phishing campaign targeted executives."
        entities = ner.extract(text)
        events = event_extractor.extract(text, entities)
        types = [e.event_type for e in events]
        assert "phishing" in types

    def test_event_confidence(self):
        from intelgraph.core.nlp.extractor import EventExtractor

        event_extractor = EventExtractor()
        text = "The breach was detected."
        events = event_extractor.extract(text)
        if events:
            assert 0 <= events[0].confidence <= 1

    def test_multiple_events(self):
        from intelgraph.core.nlp.extractor import EventExtractor

        event_extractor = EventExtractor()
        text = "The breach occurred after phishing. Then malware infected systems."
        events = event_extractor.extract(text)
        assert len(events) >= 2


# ===================================================================
# Text Classification Tests
# ===================================================================


class TestTextClassifier:
    def test_malware_classification(self):
        from intelgraph.core.nlp.extractor import TextClassifier

        classifier = TextClassifier()
        text = "A new ransomware trojan was discovered deploying backdoors."
        result = classifier.classify(text)
        assert result.top_type == "malware"
        assert result.severity in ("critical", "high", "medium", "low", "unknown")

    def test_vulnerability_classification(self):
        from intelgraph.core.nlp.extractor import TextClassifier

        classifier = TextClassifier()
        text = "CVE-2024-1234 is a critical zero-day vulnerability."
        result = classifier.classify(text)
        assert result.top_type == "vulnerability"

    def test_phishing_classification(self):
        from intelgraph.core.nlp.extractor import TextClassifier

        classifier = TextClassifier()
        text = "Phishing emails are targeting users with social engineering."
        result = classifier.classify(text)
        assert result.top_type == "phishing"

    def test_unknown_classification(self):
        from intelgraph.core.nlp.extractor import TextClassifier

        classifier = TextClassifier()
        text = "The weather is nice today."
        result = classifier.classify(text)
        assert result.top_type == "unknown"

    def test_confidence_range(self):
        from intelgraph.core.nlp.extractor import TextClassifier

        classifier = TextClassifier()
        text = "CVE-2024-1234 ransomware breach."
        result = classifier.classify(text)
        assert 0 <= result.confidence <= 1

    def test_severity_detection(self):
        from intelgraph.core.nlp.extractor import TextClassifier

        classifier = TextClassifier()
        text = "CRITICAL: emergency response required for severe breach."
        result = classifier.classify(text)
        assert result.severity in ("critical", "high")


# ===================================================================
# Document Summarizer Tests
# ===================================================================


class TestDocumentSummarizer:
    def test_summary_generation(self):
        from intelgraph.core.nlp.extractor import DocumentSummarizer

        summarizer = DocumentSummarizer()
        text = "A critical vulnerability CVE-2024-1234 was discovered. It affects all versions. Ransomware campaigns are using this. The patch is available now. Organizations should update immediately. Attackers are exploiting this in the wild."
        result = summarizer.summarize(text, max_sentences=3)
        assert "summary" in result
        assert len(result["summary"]) > 0
        assert "key_findings" in result
        assert len(result["key_findings"]) >= 1

    def test_short_text(self):
        from intelgraph.core.nlp.extractor import DocumentSummarizer

        summarizer = DocumentSummarizer()
        text = "Short text."
        result = summarizer.summarize(text)
        assert result["sentence_count"] == 0

    def test_key_findings_from_summary(self):
        from intelgraph.core.nlp.extractor import DocumentSummarizer

        summarizer = DocumentSummarizer()
        text = "The IP 192.168.1.1 was involved in a breach using CVE-2024-1234 on domain evil.com."
        result = summarizer.summarize(text)
        entity_texts = [f["entity"] for f in result["key_findings"]]
        assert len(entity_texts) >= 1


# ===================================================================
# Entity Linker Tests
# ===================================================================


class TestEntityLinker:
    def test_link_no_graph(self):
        from intelgraph.core.nlp.linker import EntityLinker

        linker = EntityLinker()
        result = linker.link("test", [{"text": "192.168.1.1", "label": "IP"}])
        assert result["total_mentions"] == 1
        assert result["matched_count"] == 0
        assert result["link_accuracy"] == 0.0

    def test_link_with_graph(self):
        from intelgraph.core.nlp.linker import EntityLinker

        linker = EntityLinker()
        mock_graph = type("MockGraph", (), {"nodes": {}})()
        mock_graph.nodes["node1"] = {"name": "192.168.1.1", "properties": {"ip": "192.168.1.1"}}
        linker.set_graph(mock_graph)
        result = linker.link(
            "192.168.1.1 is bad",
            [{"text": "192.168.1.1", "label": "IP", "normalized": "192.168.1.1"}],
        )
        assert result["matched_count"] == 1
        assert result["link_accuracy"] == 1.0

    def test_link_accuracy_stats(self):
        from intelgraph.core.nlp.linker import EntityLinker

        linker = EntityLinker()
        linker.link("test", [{"text": "a", "label": "IP"}])
        linker.link("test", [{"text": "b", "label": "IP"}])
        stats = linker.link_accuracy_stats()
        assert stats["total_mentions"] == 2
        assert stats["total_matched"] == 0

    def test_partial_match(self):
        from intelgraph.core.nlp.linker import EntityLinker

        linker = EntityLinker()
        mock_graph = type("MockGraph", (), {"nodes": {}})()
        mock_graph.nodes["n1"] = {"name": "known-host", "properties": {"ip": "10.0.0.1"}}
        mock_graph.nodes["n2"] = {"name": "other-host", "properties": {"ip": "10.0.0.2"}}
        linker.set_graph(mock_graph)
        entities = [
            {"text": "10.0.0.1", "label": "IP", "normalized": "10.0.0.1"},
            {"text": "10.0.0.99", "label": "IP", "normalized": "10.0.0.99"},
        ]
        result = linker.link("scan", entities)
        assert result["matched_count"] == 1
        assert result["total_mentions"] == 2
        assert result["link_accuracy"] == 0.5


# ===================================================================
# NLP Model Registry Tests
# ===================================================================


class TestNLPModelRegistry:
    def test_register_model(self):
        from intelgraph.core.nlp.models import ModelTask, NLPModelRegistry

        registry = NLPModelRegistry()
        record = registry.register("spacy-ner", "3.0", ModelTask.NER)
        assert record.name == "spacy-ner"
        assert record.version == "3.0"
        assert record.task == ModelTask.NER
        assert record.status == "registered"

    def test_deploy_model(self):
        from intelgraph.core.nlp.models import ModelTask, NLPModelRegistry

        registry = NLPModelRegistry()
        r1 = registry.register("model-a", "1.0", ModelTask.NER)
        registry.register("model-b", "2.0", ModelTask.NER)
        assert registry.deploy(r1.model_id)
        active = registry.get_active(ModelTask.NER)
        assert active is not None
        assert active.model_id == r1.model_id

    def test_hot_swap_model(self):
        from intelgraph.core.nlp.models import ModelTask, NLPModelRegistry

        registry = NLPModelRegistry()
        r1 = registry.register("model-a", "1.0", ModelTask.NER)
        r2 = registry.register("model-b", "2.0", ModelTask.NER)
        registry.hot_swap(r1.model_id)
        registry.hot_swap(r2.model_id)
        active = registry.get_active(ModelTask.NER)
        assert active.model_id == r2.model_id

    def test_list_models(self):
        from intelgraph.core.nlp.models import ModelTask, NLPModelRegistry

        registry = NLPModelRegistry()
        registry.register("a", "1", ModelTask.NER)
        registry.register("b", "1", ModelTask.CLASSIFICATION)
        models = registry.list()
        assert len(models) == 2
        ner_models = registry.list(ModelTask.NER)
        assert len(ner_models) == 1

    def test_deprecate_model(self):
        from intelgraph.core.nlp.models import ModelTask, NLPModelRegistry

        registry = NLPModelRegistry()
        r = registry.register("m", "1", ModelTask.NER)
        assert registry.deprecate(r.model_id)
        assert registry.get(r.model_id).status == "deprecated"

    def test_deploy_invalid_model(self):
        from intelgraph.core.nlp.models import NLPModelRegistry

        registry = NLPModelRegistry()
        assert not registry.deploy("nonexistent")

    def test_on_swap_callback(self):
        from intelgraph.core.nlp.models import ModelTask, NLPModelRegistry

        registry = NLPModelRegistry()
        calls = []
        registry.on_swap(lambda mid, action: calls.append((mid, action)))
        r = registry.register("m", "1", ModelTask.NER)
        registry.deploy(r.model_id)
        assert len(calls) == 1
        assert calls[0] == (r.model_id, "deploy")


# ===================================================================
# NLPAnalytics Tests
# ===================================================================


class TestNLPAnalytics:
    def test_entity_frequency(self):
        from intelgraph.core.nlp.models import NLPAnalytics

        analytics = NLPAnalytics()
        analytics.record_entities(
            "doc1", [{"label": "IP", "text": "1.1.1.1"}, {"label": "IP", "text": "1.1.1.1"}]
        )
        analytics.record_entities("doc2", [{"label": "IP", "text": "2.2.2.2"}])
        freq = analytics.entity_frequency("IP")
        assert freq["IP"]["1.1.1.1"] == 2
        assert freq["IP"]["2.2.2.2"] == 1

    def test_relationship_distribution(self):
        from intelgraph.core.nlp.models import NLPAnalytics

        analytics = NLPAnalytics()
        analytics.record_relationships(
            [{"relation": "connects_to"}, {"relation": "connects_to"}, {"relation": "owns"}]
        )
        dist = analytics.relationship_distribution()
        assert dist["connects_to"] == 2
        assert dist["owns"] == 1

    def test_event_timeline(self):
        from intelgraph.core.nlp.models import NLPAnalytics

        analytics = NLPAnalytics()
        analytics.record_event({"event_type": "breach", "actors": ["hacker"]})
        analytics.record_event({"event_type": "phishing", "actors": ["phisher"]})
        events = analytics.event_timeline()
        assert len(events) == 2

    def test_event_timeline_filter(self):
        from intelgraph.core.nlp.models import NLPAnalytics

        analytics = NLPAnalytics()
        analytics.record_event({"event_type": "breach"})
        analytics.record_event({"event_type": "phishing"})
        events = analytics.event_timeline(event_type="breach")
        assert len(events) == 1
        assert events[0]["event_type"] == "breach"

    def test_cooccurrence_matrix(self):
        from intelgraph.core.nlp.models import NLPAnalytics

        analytics = NLPAnalytics()
        analytics.record_cooccurrence("IP_A", "DOMAIN_B")
        analytics.record_cooccurrence("IP_A", "DOMAIN_B")
        analytics.record_cooccurrence("IP_A", "CVE_C")
        matrix = analytics.cooccurrence_matrix("IP_A")
        assert matrix["DOMAIN_B"] == 2
        assert matrix["CVE_C"] == 1

    def test_threat_patterns(self):
        from intelgraph.core.nlp.models import NLPAnalytics

        analytics = NLPAnalytics()
        for _ in range(3):
            analytics.record_event(
                {"event_type": "breach", "actors": ["threat_group"], "targets": ["bank"]}
            )
        patterns = analytics.threat_patterns(min_frequency=3)
        assert len(patterns) >= 1
        assert patterns[0]["event_type"] == "breach"


# ===================================================================
# Economic Governor Tests
# ===================================================================


class TestEconomicGovernor:
    def test_approve_high_roi(self):
        from intelgraph.core.nlp.economics import EconomicGovernor

        gov = EconomicGovernor({"budget_limit": 100, "min_roi": 0.5})
        roi = gov.compute_roi("q1", value=10, cost=1)
        assert roi.decision == "approve"
        assert roi.roi == 10.0

    def test_reject_low_roi(self):
        from intelgraph.core.nlp.economics import EconomicGovernor

        gov = EconomicGovernor({"budget_limit": 100, "min_roi": 5.0})
        roi = gov.compute_roi("q2", value=10, cost=10)
        assert roi.decision == "reject_insufficient_roi"

    def test_reject_budget_exhausted(self):
        from intelgraph.core.nlp.economics import EconomicGovernor

        gov = EconomicGovernor({"budget_limit": 10, "min_roi": 0})
        gov.compute_roi("q1", value=5, cost=9)
        roi = gov.compute_roi("q2", value=5, cost=2)
        assert roi.decision == "reject_budget_exhausted"

    def test_budget_status(self):
        from intelgraph.core.nlp.economics import EconomicGovernor

        gov = EconomicGovernor({"budget_limit": 100, "min_roi": 0})
        gov.compute_roi("q1", value=20, cost=30)
        status = gov.get_budget_status()
        assert status["budget_used"] == 30
        assert status["budget_remaining"] == 70

    def test_predict_budget_exhaustion(self):
        from intelgraph.core.nlp.economics import EconomicGovernor

        gov = EconomicGovernor({"budget_limit": 100, "min_roi": 0})
        gov.compute_roi("q1", value=10, cost=25)
        remaining_queries = gov.predict_budget_exhaustion(25)
        assert remaining_queries == 3.0


# ===================================================================
# Chaos Simulator Tests
# ===================================================================


class TestChaosSimulator:
    def test_chaos_disabled(self):
        from intelgraph.core.nlp.simulation import ChaosSimulator

        sim = ChaosSimulator(enabled=False)
        assert sim.should_fail() is None
        assert not sim.simulate_api_outage(1.0)

    def test_scenario_lifecycle(self):
        from intelgraph.core.nlp.simulation import ChaosSimulator, FailureMode, SimulationScenario

        sim = ChaosSimulator(enabled=True)
        sid = sim.add_scenario(
            SimulationScenario(
                name="test-failure",
                failure_mode=FailureMode.API_DOWN,
                failure_probability=1.0,
                duration_seconds=60,
            )
        )
        assert sim.activate_scenario(sid)
        assert sim.deactivate_scenario(sid)

    def test_adversarial_input(self):
        from intelgraph.core.nlp.simulation import ChaosSimulator

        sim = ChaosSimulator(enabled=True)
        original = "Normal text with CVE-2024-1234."
        modified = sim.get_adversarial_input(original)
        assert isinstance(modified, str)

    def test_adversarial_input_disabled(self):
        from intelgraph.core.nlp.simulation import ChaosSimulator

        sim = ChaosSimulator(enabled=False)
        original = "Normal text."
        assert sim.get_adversarial_input(original) == original

    def test_cascade(self):
        from intelgraph.core.nlp.simulation import ChaosSimulator

        sim = ChaosSimulator(enabled=True)
        affected = sim.simulate_cascade(depth=2)
        assert len(affected) <= 3

    def test_digital_twin(self):
        from intelgraph.core.nlp.simulation import ChaosSimulator

        sim = ChaosSimulator(enabled=False)

        def dummy_pipeline(text: str):
            return text.upper()

        score = sim.run_digital_twin(dummy_pipeline, ["hello", "world"])
        assert score.success_rate == 1.0
        assert score.grade == "A"
        assert score.total_attempts == 2


# ===================================================================
# Sanitizer Tests
# ===================================================================


class TestInputSanitizer:
    def test_sanitize_text(self):
        sanitized = InputSanitizer.sanitize_text("<script>alert('xss')</script>")
        assert "<script>" not in sanitized
        assert "&lt;script&gt;" in sanitized

    def test_sanitize_strip_html(self):
        result = InputSanitizer.strip_html("<p>Hello <b>World</b></p>")
        assert "<" not in result
        assert "Hello World" in result

    def test_validate_text(self):
        assert InputSanitizer.validate_text("hello")
        assert not InputSanitizer.validate_text("", min_length=1)
        assert not InputSanitizer.validate_text(123)

    def test_max_length(self):
        long = "a" * 2_000_000
        sanitized = InputSanitizer.sanitize_text(long)
        assert len(sanitized) == InputSanitizer.MAX_TEXT_LENGTH

    def test_null_bytes_removed(self):
        sanitized = InputSanitizer.sanitize_text("bad\x00text")
        assert "\x00" not in sanitized


class TestOutputSanitizer:
    def test_sanitize_entity_output(self):
        entities = [{"text": "<script>alert(1)</script>", "label": "MALWARE", "confidence": 0.9}]
        safe = OutputSanitizer.sanitize_entity_output(entities)
        assert "<script>" not in safe[0]["text"]
        assert "&lt;script&gt;" in safe[0]["text"]

    def test_sanitize_string(self):
        assert OutputSanitizer.sanitize_string("<b>test</b>") == "&lt;b&gt;test&lt;/b&gt;"


# ===================================================================
# Batch Performance Tests
# ===================================================================


class TestBatchPerformance:
    def test_large_text_batch_entities(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = " ".join(
            [
                f"CVE-2024-{i} is a vulnerability at {i}.{i}.{i}.1 on domain{i}.com"
                for i in range(100)
            ]
        )
        start = time.perf_counter()
        entities = ner.extract(text)
        elapsed = time.perf_counter() - start
        assert len(entities) >= 100
        assert elapsed < 5.0

    def test_large_text_classification(self):
        from intelgraph.core.nlp.extractor import TextClassifier

        classifier = TextClassifier()
        text = " ".join(["ransomware trojan backdoor CVE-2024-1234 breach"] * 500)
        start = time.perf_counter()
        result = classifier.classify(text)
        elapsed = time.perf_counter() - start
        assert result.top_type in ("malware", "vulnerability")
        assert elapsed < 2.0


# ===================================================================
# Model Hot-Swapping Test
# ===================================================================


class TestModelHotSwapping:
    def test_hot_swap_chain(self):
        from intelgraph.core.nlp.models import ModelTask, NLPModelRegistry

        registry = NLPModelRegistry()
        models = []
        for i in range(5):
            r = registry.register(f"model-v{i}", f"{i}.0", ModelTask.NER)
            models.append(r)
            assert registry.hot_swap(r.model_id)
            active = registry.get_active(ModelTask.NER)
            assert active.model_id == r.model_id
        final = registry.get_active(ModelTask.NER)
        assert final.model_id == models[-1].model_id

    def test_hot_swap_different_tasks(self):
        from intelgraph.core.nlp.models import ModelTask, NLPModelRegistry

        registry = NLPModelRegistry()
        ner = registry.register("ner-model", "1.0", ModelTask.NER)
        cls = registry.register("cls-model", "1.0", ModelTask.CLASSIFICATION)
        registry.hot_swap(ner.model_id)
        registry.hot_swap(cls.model_id)
        active_ner = registry.get_active(ModelTask.NER)
        active_cls = registry.get_active(ModelTask.CLASSIFICATION)
        assert active_ner.model_id == ner.model_id
        assert active_cls.model_id == cls.model_id


# ===================================================================
# Integration with Graph: Text-to-Graph Flow
# ===================================================================


class TestTextToGraphIntegration:
    def test_extract_and_classify_and_summarize(self):
        from intelgraph.core.nlp.extractor import DocumentSummarizer, NEREngine, TextClassifier

        ner = NEREngine()
        classifier = TextClassifier()
        summarizer = DocumentSummarizer()
        text = "CVE-2024-5678 is a critical vulnerability exploited by ransomware at 192.168.50.1 on evilcorp.com."
        entities = ner.extract(text)
        classification = classifier.classify(text)
        summary = summarizer.summarize(text)
        assert len(entities) >= 3
        assert classification.top_type in ("vulnerability", "malware")
        assert len(summary["key_findings"]) >= 1

    def test_full_extraction_pipeline(self):
        from intelgraph.core.nlp.extractor import EventExtractor, NEREngine, RelationshipExtractor

        ner = NEREngine()
        rel_extractor = RelationshipExtractor()
        event_extractor = EventExtractor()
        text = "The threat actor APT29 used CVE-2024-1234 to breach the network at 10.0.0.1. The ransomware was deployed on target.com."
        entities = ner.extract(text)
        relationships = rel_extractor.extract(text, entities)
        events = event_extractor.extract(text, entities)
        assert len(entities) >= 4
        assert len(relationships) >= 0
        assert len(events) >= 1

    def test_text_to_graph_confidence(self):
        from intelgraph.core.nlp.extractor import NEREngine

        ner = NEREngine()
        text = "CVE-2024-1234 at 192.168.1.1."
        entities = ner.extract(text)
        confidences = [e.confidence for e in entities]
        assert all(0 <= c <= 1 for c in confidences)
        assert all(c >= 0.65 for c in confidences)
