from intelgraph.core.source.feed import DeduplicationEngine, FeedSchema, FeedValidator


class TestFeedSchema:
    def test_defaults(self):
        s = FeedSchema()
        assert s.required_fields == []
        assert s.version == 1

    def test_required_fields_validation(self):
        s = FeedSchema({"required_fields": ["name", "type"]})
        entry = {"name": "Alice", "type": "person"}
        assert s.validate_entry(entry) == []
        entry2 = {"name": "Bob"}
        errors = s.validate_entry(entry2)
        assert len(errors) == 1
        assert "type" in errors[0]

    def test_field_types(self):
        s = FeedSchema({"field_types": {"age": "integer", "score": "number"}})
        assert s.validate_entry({"age": "30", "score": 95.5}) != []
        assert s.validate_entry({"age": 30, "score": 95.5}) == []

    def test_apply_defaults(self):
        s = FeedSchema({"field_defaults": {"country": "US", "active": True}})
        entry = {"name": "Alice"}
        result = s.apply_defaults(entry)
        assert result["country"] == "US"
        assert result["active"] is True
        assert result["name"] == "Alice"

    def test_to_dict(self):
        schema = {"required_fields": ["name"]}
        s = FeedSchema(schema)
        assert s.to_dict() == schema


class TestFeedValidator:
    def test_validates_all_entries(self):
        schema = FeedSchema({"required_fields": ["name"]})
        validator = FeedValidator(schema)
        valid = validator.validate(
            [
                {"name": "Alice", "type": "person"},
                {"name": "Bob"},
                {"type": "person"},
            ]
        )
        assert len(valid) == 2
        assert valid[0]["name"] == "Alice"
        assert valid[1]["name"] == "Bob"

    def test_validate_with_errors(self):
        schema = FeedSchema({"required_fields": ["name"]})
        validator = FeedValidator(schema)
        results = validator.validate_with_errors(
            [
                {"name": "Alice"},
                {"type": "person"},
            ]
        )
        assert len(results) == 2
        assert len(results[0][1]) == 0
        assert len(results[1][1]) == 1

    def test_applies_defaults(self):
        schema = FeedSchema(
            {
                "required_fields": ["name"],
                "field_defaults": {"active": True},
            }
        )
        validator = FeedValidator(schema)
        valid = validator.validate([{"name": "Alice"}])
        assert valid[0]["active"] is True

    def test_no_schema_validates_all(self):
        validator = FeedValidator()
        valid = validator.validate([{"anything": "goes"}, {}])
        assert len(valid) == 2


class TestDeduplicationEngine:
    def test_deduplicates_by_id(self):
        engine = DeduplicationEngine(key_fields=["id"])
        entries = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
            {"id": "1", "name": "Alice Dup"},
        ]
        unique, removed = engine.deduplicate(entries)
        assert len(unique) == 2
        assert removed == 1

    def test_deduplicates_by_name(self):
        engine = DeduplicationEngine(key_fields=["name"])
        entries = [
            {"name": "Alice"},
            {"name": "Bob"},
            {"name": "Alice"},
        ]
        unique, removed = engine.deduplicate(entries)
        assert len(unique) == 2
        assert removed == 1

    def test_deduplicates_with_existing(self):
        engine = DeduplicationEngine(key_fields=["id"])
        existing = engine.compute_fingerprints([{"id": "1", "name": "Alice"}])
        entries = [{"id": "1", "name": "Alice Again"}, {"id": "2", "name": "Bob"}]
        unique, removed = engine.deduplicate(entries, existing_fingerprints=existing)
        assert len(unique) == 1
        assert removed == 1
        assert unique[0]["id"] == "2"

    def test_no_duplicates(self):
        engine = DeduplicationEngine()
        entries = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        unique, removed = engine.deduplicate(entries)
        assert len(unique) == 3
        assert removed == 0

    def test_empty_input(self):
        engine = DeduplicationEngine()
        unique, removed = engine.deduplicate([])
        assert len(unique) == 0
        assert removed == 0

    def test_fingerprint_consistency(self):
        engine = DeduplicationEngine(key_fields=["id"])
        fp1 = engine.compute_fingerprints([{"id": "1", "name": "Alice"}])
        fp2 = engine.compute_fingerprints([{"id": "1", "name": "Bob"}])
        assert fp1 == fp2
