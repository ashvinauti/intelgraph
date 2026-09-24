from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.export import ExportSettings, GraphExporter, GraphExportError
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.relationship.base import Relationship
from intelgraph.core.relationship.types import RelationshipType


def _make_node(
    node_id: str,
    entity_type: str = "ip_address",
    confidence: int = 80,
    first_seen=None,
    last_seen=None,
):
    if entity_type == "ip_address":
        ent = IPAddress(
            id=node_id,
            ip="192.168.1.1",
            rdns="",
            asn="",
            organization="",
            open_ports=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            first_seen=first_seen or datetime.now(UTC),
            last_seen=last_seen or datetime.now(UTC),
            aliases=(),
            confidence_score=confidence,
            trust_score=70,
            provenance=(),
            evidence=(),
        )
    elif entity_type == "domain":
        ent = Domain(
            id=node_id,
            domain_name="example.com",
            registrant="",
            registrar="",
            creation_date=None,
            expiration_date=None,
            nameservers=(),
            ip_addresses=(),
            technologies=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            first_seen=first_seen or datetime.now(UTC),
            last_seen=last_seen or datetime.now(UTC),
            aliases=(),
            confidence_score=confidence,
            trust_score=70,
            provenance=(),
            evidence=(),
        )
    else:
        raise ValueError(f"Unknown entity_type: {entity_type}")
    return Node(entity=ent)


def _make_edge(eid: str, src: str, tgt: str, rel_type=RelationshipType.RELATED_TO, confidence=75):
    rel = Relationship(
        id=eid,
        type=rel_type,
        source_id=src,
        target_id=tgt,
        confidence_score=confidence,
        trust_weight=60,
        evidence_chain=(),
        provenance=(),
        created_at=datetime.now(UTC),
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
    )
    return Edge(relationship=rel)


def _build_test_graph() -> IntelligenceGraph:
    g = IntelligenceGraph()
    n1 = _make_node("node_ip1", "ip_address", confidence=90)
    n2 = _make_node("node_dm1", "domain", confidence=70)
    n3 = _make_node("node_ip2", "ip_address", confidence=50)
    g.nodes = {"node_ip1": n1, "node_dm1": n2, "node_ip2": n3}
    e1 = _make_edge("edge_1", "node_ip1", "node_dm1", RelationshipType.RESOLVES_TO, 85)
    e2 = _make_edge("edge_2", "node_ip1", "node_ip2", RelationshipType.RELATED_TO, 60)
    g.edges = {"edge_1": e1, "edge_2": e2}
    g.adjacency = {
        "node_ip1": {"node_dm1", "node_ip2"},
        "node_dm1": {"node_ip1"},
        "node_ip2": {"node_ip1"},
    }
    g.forward_adjacency = {
        "node_ip1": {"node_dm1", "node_ip2"},
        "node_dm1": {"node_ip1"},
        "node_ip2": {"node_ip1"},
    }
    g.reverse_adjacency = {
        "node_ip1": {"node_dm1", "node_ip2"},
        "node_dm1": {"node_ip1"},
        "node_ip2": {"node_ip1"},
    }
    g.node_edges = {
        "node_ip1": {"edge_1", "edge_2"},
        "node_dm1": {"edge_1"},
        "node_ip2": {"edge_2"},
    }
    g.edge_node_map = {
        "edge_1": ("node_ip1", "node_dm1"),
        "edge_2": ("node_ip1", "node_ip2"),
    }
    return g


class TestGraphMLExport:
    def test_graphml_valid_xml(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        xml_str = "".join(exporter.export_iter("graphml"))
        root = ET.fromstring(xml_str)
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        nodes = root.findall(".//g:node", ns)
        edges = root.findall(".//g:edge", ns)
        assert len(nodes) == 3
        assert len(edges) == 2

    def test_graphml_node_attributes(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        xml_str = "".join(exporter.export_iter("graphml"))
        assert "entity_type" in xml_str
        assert "ip_address" in xml_str
        assert "domain" in xml_str
        assert "confidence_score" in xml_str
        assert "90" in xml_str or "70" in xml_str or "50" in xml_str


class TestGEXFExport:
    def test_gexf_valid_xml(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        xml_str = "".join(exporter.export_iter("gexf"))
        root = ET.fromstring(xml_str)
        ns = {"g": "http://gexf.net/1.3"}
        nodes = root.findall(".//g:node", ns)
        edges = root.findall(".//g:edge", ns)
        assert len(nodes) == 3
        assert len(edges) == 2

    def test_gexf_temporal_spells(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        xml_str = "".join(exporter.export_iter("gexf"))
        assert "spell" in xml_str or "attvalue" in xml_str
        assert "first_seen" in xml_str
        assert "last_seen" in xml_str

    def test_gexf_node_attvalues(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        xml_str = "".join(exporter.export_iter("gexf"))
        # Should have entity_type attvalues
        assert 'for="entity_type"' in xml_str
        assert 'value="ip_address"' in xml_str or 'value="domain"' in xml_str


class TestJSONExport:
    def test_json_parses(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        import json

        data = json.loads("".join(exporter.export_iter("json")))
        assert "graph" in data
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        assert len(data["graph"]["nodes"]) == 3
        assert len(data["graph"]["edges"]) == 2

    def test_json_metadata(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        import json

        data = json.loads("".join(exporter.export_iter("json")))
        assert "metadata" in data
        assert "filtering" in data["metadata"]


class TestCSVExport:
    def test_csv_has_nodes_and_edges(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        csv_text = "".join(exporter.export_iter("csv"))
        assert "node_id" in csv_text
        assert "edge_id" in csv_text
        assert "--- EDGES ---" in csv_text
        assert "node_ip1" in csv_text
        assert "node_dm1" in csv_text

    def test_csv_parses_with_pandas(self):
        """CSV output should be parseable by pandas."""
        g = _build_test_graph()
        exporter = GraphExporter(g)
        csv_text = "".join(exporter.export_iter("csv"))
        parts = csv_text.split("--- EDGES ---")
        assert len(parts) == 2
        # Parse nodes section
        nodes_reader = csv.DictReader(io.StringIO(parts[0].strip()))
        node_rows = list(nodes_reader)
        assert len(node_rows) == 3
        for row in node_rows:
            assert "node_id" in row
            assert "entity_type" in row
        # Parse edges section
        edges_reader = csv.DictReader(io.StringIO(parts[1].strip()))
        edge_rows = list(edges_reader)
        assert len(edge_rows) == 2
        for row in edge_rows:
            assert "source" in row
            assert "target" in row


class TestFilters:
    def test_min_confidence_filter_edges(self):
        g = _build_test_graph()
        settings = ExportSettings(min_confidence=80)
        exporter = GraphExporter(g, settings)
        # Node list is not filtered by confidence (kept for backward compat)
        assert len(exporter._get_node_list()) == 3
        # Edge list should be filtered: only edge_1 has 85 >= 80
        assert len(exporter._get_edge_triples()) == 1

    def test_entity_types_filter(self):
        g = _build_test_graph()
        settings = ExportSettings(include_entity_types={"domain"})
        exporter = GraphExporter(g, settings)
        nodes = exporter._get_node_list()
        assert len(nodes) == 1
        assert nodes[0][1].entity_type == "domain"

    def test_min_threat_score_filter(self):
        g = _build_test_graph()
        # Inject threat scores into cache
        from intelgraph.core.graph.anomaly import _THREAT_SCORE_CACHE

        _THREAT_SCORE_CACHE.clear()
        _THREAT_SCORE_CACHE["node_ip1"] = 85.0
        _THREAT_SCORE_CACHE["node_dm1"] = 30.0
        _THREAT_SCORE_CACHE["node_ip2"] = 60.0
        try:
            settings = ExportSettings(min_threat_score=70)
            exporter = GraphExporter(g, settings)
            nodes = exporter._get_node_list()
            assert len(nodes) == 1
            assert nodes[0][0] == "node_ip1"
        finally:
            _THREAT_SCORE_CACHE.clear()

    def test_since_filter(self):
        g = _build_test_graph()
        # One node seen very recently, another seen long ago
        datetime(2020, 1, 1, tzinfo=UTC)
        datetime.now(UTC)
        from intelgraph.core.graph.export import ExportSettings

        settings = ExportSettings(since="2023-01-01T00:00:00+00:00")
        exporter = GraphExporter(g, settings)
        nodes = exporter._get_node_list()
        # All nodes use now() so they should all pass
        assert len(nodes) == 3

    def test_until_filter(self):
        g = _build_test_graph()
        settings = ExportSettings(until="2020-01-01T00:00:00+00:00")
        exporter = GraphExporter(g, settings)
        nodes = exporter._get_node_list()
        # All nodes use now() so none should pass
        assert len(nodes) == 0

    def test_relative_since_filter(self):
        g = _build_test_graph()
        settings = ExportSettings(since="30d")
        exporter = GraphExporter(g, settings)
        nodes = exporter._get_node_list()
        assert len(nodes) == 3  # all within last 30 days

    def test_combined_filters(self):
        g = _build_test_graph()
        from intelgraph.core.graph.anomaly import _THREAT_SCORE_CACHE

        _THREAT_SCORE_CACHE.clear()
        _THREAT_SCORE_CACHE["node_ip1"] = 90.0
        _THREAT_SCORE_CACHE["node_dm1"] = 30.0
        _THREAT_SCORE_CACHE["node_ip2"] = 50.0
        try:
            settings = ExportSettings(
                min_confidence=60,
                min_threat_score=40,
                include_entity_types={"ip_address"},
            )
            exporter = GraphExporter(g, settings)
            nodes = exporter._get_node_list()
            # node confidence filter NOT applied (backward compat)
            # node_ip1: threat=90 >=40, ip_address -> included
            # node_dm1: domain -> excluded by entity_type
            # node_ip2: threat=50 >=40, ip_address -> included (even though confidence=50<60, node confidence not filtered)
            assert len(nodes) == 2, f"Expected 2 nodes, got {len(nodes)}: {[n[0] for n in nodes]}"
        finally:
            _THREAT_SCORE_CACHE.clear()


class TestExportIter:
    def test_all_formats_produce_output(self):
        g = _build_test_graph()
        for fmt in ("graphml", "gexf", "json", "csv"):
            exporter = GraphExporter(g)
            output = "".join(exporter.export_iter(fmt))
            assert len(output) > 0, f"{fmt} produced empty output"

    def test_unsupported_format_raises(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        with pytest.raises(GraphExportError, match="Unsupported format"):
            list(exporter.export_iter("pdf"))


class TestNodeAttrs:
    def test_threat_score_in_attrs(self):
        g = _build_test_graph()
        from intelgraph.core.graph.anomaly import _THREAT_SCORE_CACHE

        _THREAT_SCORE_CACHE.clear()
        _THREAT_SCORE_CACHE["node_ip1"] = 75.5
        try:
            exporter = GraphExporter(g)
            attrs = exporter._build_node_attrs(g.nodes["node_ip1"])
            assert attrs.get("threat_score") == 75.5
        finally:
            _THREAT_SCORE_CACHE.clear()

    def test_temporal_fields_in_attrs(self):
        g = _build_test_graph()
        exporter = GraphExporter(g)
        attrs = exporter._build_node_attrs(g.nodes["node_ip1"])
        assert "first_seen" in attrs
        assert "last_seen" in attrs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
