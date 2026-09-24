import gzip
import json

import pytest

from intelgraph.core.entity import Company, Domain, Person
from intelgraph.core.graph.export import ExportSettings, GraphExporter, GraphExportError
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.relationship import Relationship
from intelgraph.core.relationship.types import RelationshipType


def _make_graph() -> IntelligenceGraph:
    g = IntelligenceGraph()
    alice = Person(name="Alice")
    bob = Person(name="Bob")
    carol = Person(name="Carol")
    acme = Company(name="Acme Corp")
    example = Domain(domain_name="example.com")
    g.add_entity(alice)
    g.add_entity(bob)
    g.add_entity(carol)
    g.add_entity(acme)
    g.add_entity(example)
    r1 = Relationship(
        source_id=alice.id,
        target_id=bob.id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    r2 = Relationship(
        source_id=bob.id,
        target_id=carol.id,
        type=RelationshipType.RELATED_TO,
        confidence_score=90,
        trust_weight=80,
    )
    r3 = Relationship(
        source_id=alice.id,
        target_id=acme.id,
        type=RelationshipType.WORKS_FOR,
        confidence_score=95,
        trust_weight=90,
    )
    r4 = Relationship(
        source_id=acme.id,
        target_id=example.id,
        type=RelationshipType.OWNS,
        confidence_score=70,
        trust_weight=60,
    )
    g.add_relationship(r1)
    g.add_relationship(r2)
    g.add_relationship(r3)
    g.add_relationship(r4)
    return g


def _two_node_graph() -> IntelligenceGraph:
    g = IntelligenceGraph()
    a = Person(name="Alice")
    b = Person(name="Bob")
    g.add_entity(a)
    g.add_entity(b)
    r = Relationship(
        source_id=a.id,
        target_id=b.id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    g.add_relationship(r)
    return g


class TestGraphExporterInit:
    def test_supported_formats(self):
        assert "graphml" in GraphExporter.SUPPORTED_FORMATS
        assert "dot" in GraphExporter.SUPPORTED_FORMATS
        assert "json" in GraphExporter.SUPPORTED_FORMATS

    def test_default_settings(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        assert exp._settings.include_metadata is True
        assert exp._settings.pretty is False
        assert exp._settings.compressed is False

    def test_unsupported_format_raises(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        with pytest.raises(GraphExportError, match="Unsupported format"):
            exp.export("pdf")

    def test_unsupported_format_iter_raises(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        with pytest.raises(GraphExportError, match="Unsupported format"):
            next(exp.export_iter("pdf"))

    def test_subgraph_extraction(self):
        g = _make_graph()
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        settings = ExportSettings(subgraph_node_id=alice_id, subgraph_depth=1)
        exp = GraphExporter(g, settings)
        result = exp.export("json")
        data = json.loads(result)
        names = {n.get("label") for n in data["graph"]["nodes"]}
        assert "Alice" in names
        assert "Bob" in names or "Acme Corp" in names
        assert "Carol" not in names
        assert "example.com" not in names


class TestGraphMLExport:
    def test_valid_xml_structure(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        xml = exp.export("graphml")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert "<graphml" in xml
        assert "<graph " in xml
        assert "</graphml>" in xml
        assert 'edgedefault="undirected"' in xml

    def test_contains_node_and_edge_count(self):
        g = _make_graph()
        exp = GraphExporter(g)
        xml = exp.export("graphml")
        assert xml.count("<node ") == 5
        assert xml.count("<edge ") == 4

    def test_node_attributes(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        xml = exp.export("graphml")
        assert 'key="label"' in xml
        assert 'key="entity_type"' in xml
        assert 'key="confidence_score"' in xml

    def test_empty_graph(self):
        g = IntelligenceGraph()
        exp = GraphExporter(g)
        xml = exp.export("graphml")
        assert "<graph " in xml
        assert "</graph>" in xml
        assert xml.count("<node ") == 0
        assert xml.count("<edge ") == 0

    def test_metadata_section(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        xml = exp.export("graphml")
        assert "exported_at" in xml
        assert "node_count" in xml


class TestDOTExport:
    def test_valid_dot_structure(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        dot = exp.export("dot")
        assert dot.startswith("graph G {")
        assert dot.endswith("}\n")
        assert " -- " in dot

    def test_contains_nodes_and_edges(self):
        g = _make_graph()
        exp = GraphExporter(g)
        dot = exp.export("dot")
        node_count = dot.count("label=")
        assert node_count >= 5
        assert dot.count(" -- ") == 4

    def test_node_attributes_in_dot(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        dot = exp.export("dot")
        assert "label=" in dot
        assert "entity_type=" in dot

    def test_empty_graph(self):
        g = IntelligenceGraph()
        exp = GraphExporter(g)
        dot = exp.export("dot")
        assert dot.startswith("graph G {")
        assert " -- " not in dot
        assert "}" in dot


class TestJSONExport:
    def test_valid_json_structure(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        data = json.loads(exp.export("json"))
        assert "graph" in data
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        assert data["graph"]["directed"] is False

    def test_node_list(self):
        g = _make_graph()
        exp = GraphExporter(g)
        data = json.loads(exp.export("json"))
        assert len(data["graph"]["nodes"]) == 5
        assert len(data["graph"]["edges"]) == 4

    def test_node_labels(self):
        g = _make_graph()
        exp = GraphExporter(g)
        data = json.loads(exp.export("json"))
        labels = {n.get("label") for n in data["graph"]["nodes"]}
        assert "Alice" in labels
        assert "Bob" in labels
        assert "Acme Corp" in labels

    def test_edge_attributes(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        data = json.loads(exp.export("json"))
        edge = data["graph"]["edges"][0]
        assert "source" in edge
        assert "target" in edge
        assert "label" in edge
        assert "confidence_score" in edge

    def test_empty_graph(self):
        g = IntelligenceGraph()
        exp = GraphExporter(g)
        data = json.loads(exp.export("json"))
        assert data["graph"]["nodes"] == []
        assert data["graph"]["edges"] == []

    def test_pretty_json(self):
        g = _two_node_graph()
        settings = ExportSettings(pretty=True)
        exp = GraphExporter(g, settings)
        output = exp.export("json")
        assert "\n" in output
        assert "  " in output

    def test_compact_json(self):
        g = _two_node_graph()
        settings = ExportSettings(pretty=False)
        exp = GraphExporter(g, settings)
        output = exp.export("json")
        assert "\n  " not in output

    def test_metadata_in_json(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        data = json.loads(exp.export("json"))
        assert "metadata" in data
        assert data["metadata"]["graph"]["node_count"] == 2
        assert data["metadata"]["graph"]["edge_count"] == 1

    def test_metadata_suppressed(self):
        g = _two_node_graph()
        settings = ExportSettings(include_metadata=False)
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        assert "metadata" not in data


class TestExportFiltering:
    def test_include_entity_type(self):
        g = _make_graph()
        settings = ExportSettings(include_entity_types={"person"})
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        types = {n.get("entity_type") for n in data["graph"]["nodes"]}
        assert types == {"person"}
        assert len(data["graph"]["nodes"]) == 3

    def test_exclude_entity_type(self):
        g = _make_graph()
        settings = ExportSettings(exclude_entity_types={"domain"})
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        types = {n.get("entity_type") for n in data["graph"]["nodes"]}
        assert "domain" not in types
        assert len(data["graph"]["nodes"]) == 4

    def test_include_relationship_type(self):
        g = _make_graph()
        settings = ExportSettings(include_relationship_types={"works_for"})
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        labels = {e.get("label") for e in data["graph"]["edges"]}
        assert labels == {"works_for"}
        assert len(data["graph"]["edges"]) == 1

    def test_exclude_relationship_type(self):
        g = _make_graph()
        settings = ExportSettings(exclude_relationship_types={"owns"})
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        labels = {e.get("label") for e in data["graph"]["edges"]}
        assert "owns" not in labels
        assert len(data["graph"]["edges"]) == 3

    def test_min_confidence(self):
        g = _make_graph()
        settings = ExportSettings(min_confidence=90)
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        for e in data["graph"]["edges"]:
            assert e["confidence_score"] >= 90

    def test_min_trust_weight(self):
        g = _make_graph()
        settings = ExportSettings(min_trust_weight=80)
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        for e in data["graph"]["edges"]:
            assert e["trust_weight"] >= 80

    def test_multiple_filters(self):
        g = _make_graph()
        settings = ExportSettings(
            include_entity_types={"person", "company"},
            min_confidence=80,
            include_relationship_types={"works_for", "related_to"},
        )
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        assert len(data["graph"]["nodes"]) >= 3
        assert len(data["graph"]["edges"]) >= 1


class TestExportCompression:
    def test_gzip_compression(self):
        g = _two_node_graph()
        settings = ExportSettings(compressed=True)
        exp = GraphExporter(g, settings)
        result = exp.export("json")
        assert isinstance(result, bytes)
        decompressed = gzip.decompress(result).decode("utf-8")
        data = json.loads(decompressed)
        assert len(data["graph"]["nodes"]) == 2

    def test_gzip_graphml(self):
        g = _two_node_graph()
        settings = ExportSettings(compressed=True)
        exp = GraphExporter(g, settings)
        result = exp.export("graphml")
        assert isinstance(result, bytes)
        decompressed = gzip.decompress(result).decode("utf-8")
        assert "<graphml" in decompressed

    def test_gzip_dot(self):
        g = _two_node_graph()
        settings = ExportSettings(compressed=True)
        exp = GraphExporter(g, settings)
        result = exp.export("dot")
        assert isinstance(result, bytes)
        decompressed = gzip.decompress(result).decode("utf-8")
        assert decompressed.startswith("graph G {")


class TestExportCommunityAnnotations:
    def test_community_in_graphml(self):
        g = _two_node_graph()
        communities = {"c1": list(g.nodes.keys())[:1], "c2": list(g.nodes.keys())[1:]}
        settings = ExportSettings(communities=communities)
        exp = GraphExporter(g, settings)
        xml = exp.export("graphml")
        list(g.nodes.keys())[0]
        assert "community_id" in xml

    def test_community_in_json(self):
        g = _two_node_graph()
        ids = list(g.nodes.keys())
        communities = {"com_a": [ids[0]], "com_b": [ids[1]]}
        settings = ExportSettings(communities=communities)
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        for node in data["graph"]["nodes"]:
            assert "community_id" in node
            assert node["community_id"] in ("com_a", "com_b")

    def test_community_in_dot(self):
        g = _two_node_graph()
        ids = list(g.nodes.keys())
        communities = {"grp1": ids}
        settings = ExportSettings(communities=communities)
        exp = GraphExporter(g, settings)
        dot = exp.export("dot")
        assert "community_id" in dot


class TestExportCentralityAnnotations:
    def test_centrality_in_json(self):
        g = _two_node_graph()
        ids = list(g.nodes.keys())
        centrality = {
            ids[0]: {"degree": 0.5, "pagerank": 0.6},
            ids[1]: {"degree": 0.5, "pagerank": 0.4},
        }
        settings = ExportSettings(centrality=centrality)
        exp = GraphExporter(g, settings)
        data = json.loads(exp.export("json"))
        for node in data["graph"]["nodes"]:
            assert any(k.startswith("centrality_") for k in node)

    def test_centrality_in_graphml(self):
        g = _two_node_graph()
        ids = list(g.nodes.keys())
        centrality = {ids[0]: {"pagerank": 0.75}}
        settings = ExportSettings(centrality=centrality)
        exp = GraphExporter(g, settings)
        xml = exp.export("graphml")
        assert "centrality" in xml
        assert "pagerank" in xml

    def test_centrality_in_dot(self):
        g = _two_node_graph()
        ids = list(g.nodes.keys())
        centrality = {ids[0]: {"degree": 1.0}}
        settings = ExportSettings(centrality=centrality)
        exp = GraphExporter(g, settings)
        dot = exp.export("dot")
        assert "centrality_degree" in dot


class TestExportProgressCallback:
    def test_callback_invoked(self):
        g = _make_graph()
        calls: list[int] = []
        total_calls: list[int] = []

        def cb(done: int, total: int) -> None:
            calls.append(done)
            total_calls.append(total)

        settings = ExportSettings(progress_callback=cb)
        exp = GraphExporter(g, settings)
        exp.export("json")
        assert len(calls) > 0
        assert total_calls[-1] == len(g.nodes) + len(g.edges)

    def test_callback_all_formats(self):
        g = _two_node_graph()
        for fmt in ("graphml", "dot", "json"):
            track: list[int] = []
            settings = ExportSettings(progress_callback=lambda d, t, _t=track: _t.append(d))
            exp = GraphExporter(g, settings)
            exp.export(fmt)
            assert len(track) == len(g.nodes) + len(g.edges), f"Failed for {fmt}"


class TestExportIter:
    def test_iter_graphml(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        chunks = list(exp.export_iter("graphml"))
        assert len(chunks) > 1
        full = "".join(chunks)
        assert "<graphml" in full
        assert "</graphml>" in full

    def test_iter_dot(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        chunks = list(exp.export_iter("dot"))
        assert len(chunks) > 1
        full = "".join(chunks)
        assert full.startswith("graph G {")

    def test_iter_json(self):
        g = _two_node_graph()
        exp = GraphExporter(g)
        chunks = list(exp.export_iter("json"))
        assert len(chunks) > 1
        full = "".join(chunks)
        data = json.loads(full)
        assert len(data["graph"]["nodes"]) == 2


class TestExportEdgeCases:
    def test_single_node_no_edges(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        exp = GraphExporter(g)
        for fmt in ("graphml", "dot", "json"):
            data = exp.export(fmt)
            assert len(data) > 0

    def test_deterministic_output(self):
        g = _make_graph()
        exp1 = GraphExporter(g)
        exp2 = GraphExporter(g)
        assert exp1.export("json") == exp2.export("json")

    def test_special_characters(self):
        g = IntelligenceGraph()
        p = Person(name="Alice & Bob <test>")
        g.add_entity(p)
        r = Relationship(
            source_id=p.id,
            target_id=p.id,
            type=RelationshipType.RELATED_TO,
            confidence_score=80,
            trust_weight=70,
        )
        g.add_relationship(r)
        exp = GraphExporter(g)
        xml = exp.export("graphml")
        assert "&amp;" in xml
        assert "&lt;" in xml
        data = json.loads(exp.export("json"))
        assert "Alice & Bob <test>" in json.dumps(data)
