from typing import Any

from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.reporting.reports import ReportBuilder


class TestReportBuilder:
    def test_entity_report_no_lookups(self):
        rb = ReportBuilder()
        result = rb.entity_report("abc123")
        assert "abc123" in result

    def test_entity_report_with_lookups(self):
        vrecs: dict[str, dict[str, Any]] = {
            "abc": {"verification_state": "confirmed", "confidence": 95.0},
        }
        chains: dict[str, dict[str, Any]] = {
            "abc": {"evidence": [{"confidence": 80.0}]},
        }
        g = IntelligenceGraph()

        rb = ReportBuilder(
            verification_lookup=lambda eid: vrecs.get(eid),
            chain_lookup=lambda eid: chains.get(eid),
            graph=g,
        )
        result = rb.entity_report("abc")
        assert "confirmed" in result

    def test_entity_report_with_graph(self):
        from intelgraph.core.entity import Person

        g = IntelligenceGraph()
        p = Person(name="Alice")
        g.add_entity(p)
        vrecs: dict[str, dict[str, Any]] = {
            p.id: {"verification_state": "confirmed", "confidence": 95.0}
        }
        chains: dict[str, dict[str, Any]] = {p.id: {"evidence": [{"confidence": 85.0}]}}
        rb = ReportBuilder(
            verification_lookup=lambda eid: vrecs.get(eid),
            chain_lookup=lambda eid: chains.get(eid),
            graph=g,
        )
        result = rb.entity_report(p.id)
        assert "Alice" in result
        assert "person" in result

    def test_evidence_report_found(self):
        chains: dict[str, dict[str, Any]] = {
            "abc": {
                "entity_id": "abc",
                "chain_id": "ch1",
                "confidence": 80.0,
                "contradiction_score": 10.0,
                "status": "verified",
                "evidence": [{"evidence_id": "e1", "claim": "test claim"}],
            },
        }
        rb = ReportBuilder(chain_lookup=lambda eid: chains.get(eid))
        result = rb.evidence_report("abc")
        assert "test claim" in result

    def test_evidence_report_not_found(self):
        rb = ReportBuilder(chain_lookup=lambda eid: None)
        result = rb.evidence_report("missing")
        assert "error" in result.lower()

    def test_verification_report_found(self):
        vrecs: dict[str, dict[str, Any]] = {
            "abc": {
                "entity_id": "abc",
                "verification_state": "confirmed",
                "operational_state": "active",
                "confidence": 95.0,
            }
        }
        rb = ReportBuilder(verification_lookup=lambda eid: vrecs.get(eid))
        result = rb.verification_report("abc")
        assert "confirmed" in result

    def test_verification_report_not_found(self):
        rb = ReportBuilder(verification_lookup=lambda eid: None)
        result = rb.verification_report("missing")
        assert "error" in result.lower()

    def test_source_report_found(self):
        sources: dict[str, dict[str, Any]] = {
            "src1": {"id": "src1", "source_url": "https://example.com", "trust_score": 85}
        }
        rb = ReportBuilder(source_lookup=lambda sid: sources.get(sid))
        result = rb.source_report("src1")
        assert "https://example.com" in result

    def test_source_report_not_found(self):
        rb = ReportBuilder(source_lookup=lambda sid: None)
        result = rb.source_report("missing")
        assert "error" in result.lower()

    def test_full_report_with_graph(self):
        from intelgraph.core.entity import Person

        g = IntelligenceGraph()
        p = Person(name="Alice")
        g.add_entity(p)
        vrecs: dict[str, dict[str, Any]] = {
            p.id: {"verification_state": "confirmed", "confidence": 95.0}
        }
        rb = ReportBuilder(verification_lookup=lambda eid: vrecs.get(eid), graph=g)
        result = rb.full_report()
        assert "entity_count" in result
        assert "1" in result

    def test_full_report_empty(self):
        rb = ReportBuilder()
        result = rb.full_report()
        assert "entity_count" in result
        assert "edge_count" in result

    def test_markdown_format(self):
        rb = ReportBuilder()
        result = rb.entity_report("abc", fmt="markdown")
        assert "# Entity Report" in result

    def test_html_format(self):
        rb = ReportBuilder()
        result = rb.entity_report("abc", fmt="html")
        assert "<!DOCTYPE html>" in result
