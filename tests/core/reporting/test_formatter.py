from intelgraph.core.reporting.formatter import format_output


class TestJsonFormat:
    def test_json_entity_report(self):
        data = {
            "entity_id": "abc123",
            "entity_type": "person",
            "attributes": {"name": "Alice"},
            "verification_status": "confirmed",
            "confidence": 95.0,
            "evidence_count": 3,
        }
        result = format_output("Entity", data, "json")
        assert "Alice" in result
        assert "confirmed" in result

    def test_json_evidence_report(self):
        data = {
            "entity_id": "abc123",
            "chain_id": "chain1",
            "confidence": 80.0,
            "contradiction_score": 10.0,
            "status": "verified",
            "evidence_count": 2,
            "evidence": [{"evidence_id": "e1", "claim": "test claim", "confidence": 90.0}],
        }
        result = format_output("Evidence", data, "json")
        assert "test claim" in result
        assert "verified" in result

    def test_json_verification_report(self):
        data = {
            "entity_id": "abc123",
            "verification_state": "confirmed",
            "operational_state": "active",
            "confidence": 95.0,
            "consensus": 90.0,
            "contradiction": 5.0,
            "source_count": 3,
            "reasoning": "All criteria met",
        }
        result = format_output("Verification", data, "json")
        assert "confirmed" in result
        assert "All criteria met" in result

    def test_json_source_report(self):
        data = {
            "id": "src1",
            "source_url": "https://example.com",
            "source_name": "Example",
            "source_tier": 1,
            "trust_score": 85,
            "reliability_score": 90,
            "classification": "news",
            "validation_count": 5,
        }
        result = format_output("Source", data, "json")
        assert "https://example.com" in result
        assert "85" in result

    def test_json_full_report(self):
        data = {
            "generated_at": "2026-01-01T00:00:00",
            "entity_count": 1,
            "edge_count": 0,
            "entities": [{"entity_id": "abc", "entity_type": "person"}],
            "evidence": [],
            "verifications": [],
        }
        result = format_output("Full", data, "json")
        assert "entity_count" in result

    def test_json_fallback(self):
        result = format_output("Unknown", {"key": "val"}, "json")
        assert "val" in result


class TestMarkdownFormat:
    def test_markdown_entity(self):
        data = {
            "entity_id": "abc",
            "entity_type": "person",
            "attributes": {"name": "Alice"},
            "verification_status": "confirmed",
            "confidence": 95.0,
            "evidence_count": 3,
        }
        result = format_output("Entity", data, "markdown")
        assert "# Entity Report" in result
        assert "Alice" in result
        assert "confirmed" in result

    def test_markdown_evidence(self):
        data = {
            "entity_id": "abc",
            "chain_id": "ch1",
            "confidence": 80.0,
            "contradiction_score": 10.0,
            "status": "verified",
            "evidence_count": 1,
            "evidence": [
                {
                    "evidence_id": "e1",
                    "source_id": "src1",
                    "claim": "test",
                    "support_type": "supports",
                    "confidence": 90.0,
                }
            ],
        }
        result = format_output("Evidence", data, "markdown")
        assert "# Evidence Report" in result
        assert "### Evidence Items" in result
        assert "test" in result

    def test_markdown_verification(self):
        data = {"entity_id": "abc", "verification_state": "confirmed", "confidence": 95.0}
        result = format_output("Verification", data, "markdown")
        assert "# Verification Report" in result

    def test_markdown_source(self):
        data = {"id": "src1", "source_url": "https://x.com", "trust_score": 80}
        result = format_output("Source", data, "markdown")
        assert "# Source Report" in result

    def test_markdown_full(self):
        data = {
            "generated_at": "2026-01-01T00:00:00",
            "entity_count": 2,
            "edge_count": 1,
            "entities": [{"entity_id": "abc", "entity_type": "person"}],
            "evidence": [
                {
                    "entity_id": "abc",
                    "confidence": 80.0,
                    "contradiction_score": 5.0,
                    "status": "verified",
                    "evidence_count": 2,
                }
            ],
            "verifications": [{"entity_id": "abc", "state": "confirmed", "confidence": 95.0}],
            "sources": [],
        }
        result = format_output("Full", data, "markdown")
        assert "# Full Report" in result
        assert "## Overview" in result
        assert "2" in result


class TestHtmlFormat:
    def test_html_entity(self):
        data = {"entity_id": "abc", "entity_type": "person", "verification_status": "confirmed"}
        result = format_output("Entity", data, "html")
        assert "<!DOCTYPE html>" in result
        assert "Entity Report" in result
        assert "confirmed" in result

    def test_html_full(self):
        data = {
            "generated_at": "now",
            "entity_count": 0,
            "edge_count": 0,
            "entities": [],
            "evidence": [],
            "verifications": [],
            "sources": [],
        }
        result = format_output("Full", data, "html")
        assert "<html" in result
        assert "</html>" in result

    def test_html_escaping(self):
        data = {"entity_id": "<script>alert('xss')</script>"}
        result = format_output("Entity", data, "html")
        assert "&lt;script&gt;" in result
        assert "<script>" not in result
