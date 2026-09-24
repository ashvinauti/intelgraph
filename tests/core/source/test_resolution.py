import pytest

from intelgraph.core.source.resolution import EntityMatcher, MergeEngine


class TestEntityMatcher:
    def test_exact_match_by_email(self):
        matcher = EntityMatcher()
        a = {"name": "Alice", "email": "alice@example.com"}
        b = {"name": "Alice Smith", "email": "alice@example.com"}
        assert matcher.match(a, b) == 1.0

    def test_exact_match_by_id(self):
        matcher = EntityMatcher()
        a = {"id": "abc123", "name": "Alice"}
        b = {"id": "abc123", "name": "Bob"}
        assert matcher.match(a, b) == 1.0

    def test_name_similarity_exact(self):
        matcher = EntityMatcher()
        a = {"name": "Alice Smith"}
        b = {"name": "Alice Smith"}
        assert matcher.match(a, b) == 1.0

    def test_name_similarity_substring(self):
        matcher = EntityMatcher()
        a = {"name": "Alice"}
        b = {"name": "Alice Smith"}
        score = matcher.match(a, b)
        assert 0.5 <= score <= 1.0

    def test_no_match(self):
        matcher = EntityMatcher(match_threshold=0.8)
        a = {"name": "Alice"}
        b = {"name": "Bob"}
        assert matcher.match(a, b) == 0.0

    def test_find_duplicates(self):
        matcher = EntityMatcher()
        entries = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Alice Dup", "email": "alice@example.com"},
            {"name": "Bob"},
        ]
        dups = matcher.find_duplicates(entries)
        assert len(dups) >= 1

    def test_empty_input(self):
        matcher = EntityMatcher()
        assert matcher.find_duplicates([]) == []


class TestMergeEngine:
    def test_merge_keep_source(self):
        engine = MergeEngine()
        merged = engine.merge(
            {"name": "Alice", "age": 30},
            {"name": "Alice Smith", "location": "NYC"},
            strategy="keep_source",
        )
        assert merged == {"name": "Alice", "age": 30}

    def test_merge_keep_target(self):
        engine = MergeEngine()
        merged = engine.merge(
            {"name": "Alice", "age": 30},
            {"name": "Alice Smith", "location": "NYC"},
            strategy="keep_target",
        )
        assert merged == {"name": "Alice Smith", "location": "NYC"}

    def test_merge_priority_source(self):
        engine = MergeEngine()
        merged = engine.merge(
            {"name": "Alice", "location": "NYC"},
            {"name": "Alice Smith", "age": 30},
            strategy="priority",
            priority_fields={"name": "other"},
        )
        assert merged["name"] == "Alice"
        assert merged.get("location") == "NYC"
        assert merged.get("age") == 30

    def test_merge_priority_target(self):
        engine = MergeEngine()
        merged = engine.merge(
            {"name": "Alice", "location": "NYC"},
            {"name": "Alice Smith", "age": 30},
            strategy="priority",
        )
        assert merged["name"] == "Alice Smith"

    def test_merge_most_confident(self):
        engine = MergeEngine()
        merged = engine.merge(
            {"name": "Alice", "confidence_score": 90},
            {"name": "Alice Smith", "confidence_score": 70},
            strategy="most_confident",
        )
        assert merged["name"] == "Alice"
        assert merged["confidence_score"] == 90

    def test_merge_newest(self):
        engine = MergeEngine()
        merged = engine.merge(
            {"name": "Alice", "created_at": "2024-01-01"},
            {"name": "Alice Smith", "created_at": "2025-01-01"},
            strategy="newest",
        )
        assert merged["name"] == "Alice Smith"

    def test_merge_fills_empty(self):
        engine = MergeEngine()
        merged = engine.merge(
            {"name": "Alice", "phone": "555-0100"},
            {"name": "Alice Smith", "phone": None, "email": "alice@example.com"},
            strategy="priority",
        )
        assert merged["phone"] == "555-0100"
        assert merged["email"] == "alice@example.com"

    def test_merge_takes_max_confidence(self):
        engine = MergeEngine()
        merged = engine.merge(
            {"name": "Alice", "confidence_score": 50},
            {"name": "Alice Smith", "confidence_score": 80},
            strategy="priority",
        )
        assert merged["confidence_score"] == 80

    def test_merge_audit_recorded(self):
        engine = MergeEngine()
        src_id = "src:1"
        tgt_id = "tgt:1"
        engine.merge(
            {"id": src_id, "name": "Alice"},
            {"id": tgt_id, "name": "Alice Smith"},
        )
        history = engine.audit.get_history()
        assert len(history) >= 1
        assert history[-1]["source_entity_id"] == src_id

    def test_invalid_strategy(self):

        with pytest.raises(ValueError):
            MergeEngine(default_strategy="invalid")
