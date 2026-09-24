from __future__ import annotations

import csv
import gzip
import io
import json
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

from intelgraph import __version__
from intelgraph.core.graph.graph import IntelligenceGraph


class GraphExportError(Exception):
    pass


class ExportSettings:
    def __init__(
        self,
        *,
        include_entity_types: set[str] | None = None,
        exclude_entity_types: set[str] | None = None,
        include_relationship_types: set[str] | None = None,
        exclude_relationship_types: set[str] | None = None,
        min_confidence: int = 0,
        min_trust_weight: int = 0,
        min_threat_score: float = 0.0,
        since: str | None = None,
        until: str | None = None,
        subgraph_node_id: str | None = None,
        subgraph_depth: int = 1,
        communities: dict[str, list[str]] | None = None,
        centrality: dict[str, dict[str, float]] | None = None,
        include_metadata: bool = True,
        pretty: bool = False,
        compressed: bool = False,
        stream_chunk_size: int = 8192,
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        self.include_entity_types = include_entity_types
        self.exclude_entity_types = exclude_entity_types
        self.include_relationship_types = include_relationship_types
        self.exclude_relationship_types = exclude_relationship_types
        self.min_confidence = min_confidence
        self.min_trust_weight = min_trust_weight
        self.min_threat_score = min_threat_score
        self.since = since
        self.until = until
        self.subgraph_node_id = subgraph_node_id
        self.subgraph_depth = subgraph_depth
        self.communities = communities
        self.centrality = centrality
        self.include_metadata = include_metadata
        self.pretty = pretty
        self.compressed = compressed
        self.stream_chunk_size = stream_chunk_size
        self.progress_callback = progress_callback


class GraphExporter:
    SUPPORTED_FORMATS = frozenset({"graphml", "dot", "json", "gexf", "csv"})

    def __init__(self, graph: IntelligenceGraph, settings: ExportSettings | None = None) -> None:
        self._graph = graph
        self._settings = settings or ExportSettings()
        g = graph
        if self._settings.subgraph_node_id:
            if self._settings.subgraph_node_id in g.nodes:
                g = g.extract_subgraph(
                    self._settings.subgraph_node_id,
                    self._settings.subgraph_depth,
                )
        self._working_graph = g

    def _parse_time_filter(self, val: str | None) -> float | None:
        if val is None:
            return None
        try:
            dt = datetime.fromisoformat(val)
            return dt.timestamp()
        except ValueError:
            pass
        try:
            # relative: 7d, 30d etc
            if val.endswith("d"):
                days = int(val[:-1])
                return time.time() - days * 86400
            if val.endswith("h"):
                hours = int(val[:-1])
                return time.time() - hours * 3600
        except ValueError:
            pass
        return None

    def _get_node_list(self) -> list[tuple[str, Any]]:
        nodes: list[tuple[str, Any]] = []
        since_ts = self._parse_time_filter(self._settings.since)
        until_ts = self._parse_time_filter(self._settings.until)
        for nid, node in self._working_graph.nodes.items():
            et = node.entity_type
            if (
                self._settings.include_entity_types is not None
                and et not in self._settings.include_entity_types
            ):
                continue
            if (
                self._settings.exclude_entity_types is not None
                and et in self._settings.exclude_entity_types
            ):
                continue
            entity = node.entity
            # threat_score filter
            if self._settings.min_threat_score > 0:
                from intelgraph.core.graph.anomaly import _THREAT_SCORE_CACHE

                ts = _THREAT_SCORE_CACHE.get(str(nid), 0.0)
                if ts < self._settings.min_threat_score:
                    continue
            # temporal filter
            if since_ts is not None or until_ts is not None:
                try:
                    last_seen = (
                        entity.last_seen.timestamp()
                        if hasattr(entity, "last_seen") and entity.last_seen
                        else 0
                    )
                    first_seen = (
                        entity.first_seen.timestamp()
                        if hasattr(entity, "first_seen") and entity.first_seen
                        else 0
                    )
                except (AttributeError, ValueError):
                    last_seen = 0
                    first_seen = 0
                if since_ts is not None and last_seen < since_ts:
                    continue
                if until_ts is not None and first_seen > until_ts:
                    continue
            nodes.append((nid, node))
        return nodes

    def _get_edge_triples(self) -> list[tuple[str, Any, str, str]]:
        edges: list[tuple[str, Any, str, str]] = []
        since_ts = self._parse_time_filter(self._settings.since)
        until_ts = self._parse_time_filter(self._settings.until)
        for eid, edge in self._working_graph.edges.items():
            rel = edge.relationship
            rt = rel.type.type_name
            if (
                self._settings.include_relationship_types is not None
                and rt not in self._settings.include_relationship_types
            ):
                continue
            if (
                self._settings.exclude_relationship_types is not None
                and rt in self._settings.exclude_relationship_types
            ):
                continue
            if rel.confidence_score < self._settings.min_confidence:
                continue
            if rel.trust_weight < self._settings.min_trust_weight:
                continue
            # temporal filter
            if since_ts is not None or until_ts is not None:
                try:
                    last_seen = (
                        rel.last_seen.timestamp()
                        if hasattr(rel, "last_seen") and rel.last_seen
                        else 0
                    )
                    first_seen = (
                        rel.first_seen.timestamp()
                        if hasattr(rel, "first_seen") and rel.first_seen
                        else 0
                    )
                except (AttributeError, ValueError):
                    last_seen = 0
                    first_seen = 0
                if since_ts is not None and last_seen < since_ts:
                    continue
                if until_ts is not None and first_seen > until_ts:
                    continue
            src_tgt = self._working_graph.edge_node_map.get(eid)
            if src_tgt is None:
                continue
            src, tgt = src_tgt
            if src not in self._working_graph.nodes or tgt not in self._working_graph.nodes:
                continue
            edges.append((eid, edge, src, tgt))
        return edges

    def _community_for(self, node_id: str) -> str | None:
        if not self._settings.communities:
            return None
        for cid, members in self._settings.communities.items():
            if node_id in members:
                return cid
        return None

    def _safe(self, value: Any) -> str:
        if value is None:
            return ""
        s = str(value)
        return (
            s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        )

    def _dot_id(self, node_id: str) -> str:
        return '"' + node_id.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _metadata_dict(self) -> dict[str, Any]:
        if not self._settings.include_metadata:
            return {}
        wg = self._working_graph
        n = wg.node_count
        e = wg.edge_count
        density = (2.0 * e / (n * (n - 1))) if n > 1 else 0.0
        total_deg = sum(len(wg.adjacency.get(nid, set())) for nid in wg.nodes)
        avg_deg = (total_deg / n) if n > 0 else 0.0
        m: dict[str, Any] = {
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "version": __version__,
            "format": "graphml",
            "compressed": self._settings.compressed,
            "graph": {
                "node_count": n,
                "edge_count": e,
                "density": round(density, 6),
                "average_degree": round(avg_deg, 4),
            },
            "filtering": {
                "include_entity_types": (
                    sorted(self._settings.include_entity_types)
                    if self._settings.include_entity_types
                    else None
                ),
                "exclude_entity_types": (
                    sorted(self._settings.exclude_entity_types)
                    if self._settings.exclude_entity_types
                    else None
                ),
                "include_relationship_types": (
                    sorted(self._settings.include_relationship_types)
                    if self._settings.include_relationship_types
                    else None
                ),
                "exclude_relationship_types": (
                    sorted(self._settings.exclude_relationship_types)
                    if self._settings.exclude_relationship_types
                    else None
                ),
                "min_confidence": self._settings.min_confidence,
                "min_trust_weight": self._settings.min_trust_weight,
                "subgraph_node_id": self._settings.subgraph_node_id,
                "subgraph_depth": (
                    self._settings.subgraph_depth if self._settings.subgraph_node_id else None
                ),
            },
            "annotations": {
                "communities": self._settings.communities is not None,
                "centrality": self._settings.centrality is not None,
            },
        }
        return m

    def export(self, format: str = "graphml") -> str | bytes:
        if format not in self.SUPPORTED_FORMATS:
            alts = ", ".join(sorted(self.SUPPORTED_FORMATS))
            raise GraphExportError(f"Unsupported format: {format}. Supported: {alts}.")
        content = "".join(self._export_iter(format))
        if self._settings.compressed:
            if isinstance(content, str):
                return gzip.compress(content.encode("utf-8"))
            return gzip.compress(content)
        return content

    def export_iter(self, format: str = "graphml") -> Iterator[str]:
        if format not in self.SUPPORTED_FORMATS:
            alts = ", ".join(sorted(self.SUPPORTED_FORMATS))
            raise GraphExportError(f"Unsupported format: {format}. Supported: {alts}.")
        yield from self._export_iter(format)

    def _export_iter(self, format: str) -> Iterator[str]:
        if format == "graphml":
            yield from self._graphml_iter()
        elif format == "dot":
            yield from self._dot_iter()
        elif format == "json":
            yield from self._json_iter()
        elif format == "gexf":
            yield from self._gexf_iter()
        elif format == "csv":
            yield from self._csv_iter()

    def _build_node_attrs(self, node: Any) -> dict[str, Any]:
        entity = node.entity
        attrs: dict[str, Any] = {
            "label": getattr(entity, "name", None)
            or getattr(entity, "domain_name", None)
            or node.id[:8],
            "entity_type": node.entity_type,
        }
        try:
            attrs["confidence_score"] = entity.confidence_score
            attrs["trust_score"] = entity.trust_score
            attrs["first_seen"] = (
                entity.first_seen.isoformat()
                if hasattr(entity, "first_seen") and entity.first_seen
                else ""
            )
            attrs["last_seen"] = (
                entity.last_seen.isoformat()
                if hasattr(entity, "last_seen") and entity.last_seen
                else ""
            )
        except AttributeError:
            pass
        # threat_score from cache
        from intelgraph.core.graph.anomaly import _THREAT_SCORE_CACHE

        ts = _THREAT_SCORE_CACHE.get(str(node.id))
        if ts is not None:
            attrs["threat_score"] = round(ts, 2)
        community_id = self._community_for(node.id)
        if community_id is not None:
            attrs["community_id"] = community_id
        if self._settings.centrality and node.id in self._settings.centrality:
            for alg, val in self._settings.centrality[node.id].items():
                attrs[f"centrality_{alg}"] = round(val, 6)
        return attrs

    def _build_edge_attrs(self, edge: Any) -> dict[str, Any]:
        rel = edge.relationship
        return {
            "label": rel.type.type_name,
            "confidence_score": rel.confidence_score,
            "trust_weight": rel.trust_weight,
        }

    def _graphml_iter(self) -> Iterator[str]:
        nodes = self._get_node_list()
        edges = self._get_edge_triples()
        total = len(nodes) + len(edges)
        done = 0

        yield '<?xml version="1.0" encoding="UTF-8"?>\n'
        yield '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n'
        yield '  <key id="label" for="node" attr.name="label" attr.type="string"/>\n'
        yield '  <key id="entity_type" for="node" attr.name="entity_type" attr.type="string"/>\n'
        yield '  <key id="confidence_score" for="node" attr.name="confidence_score" attr.type="int"/>\n'
        yield '  <key id="trust_score" for="node" attr.name="trust_score" attr.type="int"/>\n'
        yield '  <key id="community_id" for="node" attr.name="community_id" attr.type="string"/>\n'
        yield '  <key id="centrality" for="node" attr.name="centrality" attr.type="string"/>\n'
        yield '  <key id="edge_label" for="edge" attr.name="label" attr.type="string"/>\n'
        yield '  <key id="edge_confidence" for="edge" attr.name="confidence_score" attr.type="int"/>\n'
        yield '  <key id="edge_trust" for="edge" attr.name="trust_weight" attr.type="int"/>\n'
        yield '  <graph id="G" edgedefault="undirected">\n'

        for nid, node in nodes:
            attrs = self._build_node_attrs(node)
            yield f'    <node id="{self._safe(nid)}">\n'
            for key, val in attrs.items():
                if val is not None and val != "":
                    if key.startswith("centrality_"):
                        yield f'      <data key="centrality">{key[11:]}:{val}</data>\n'
                    else:
                        yield f'      <data key="{key}">{self._safe(val)}</data>\n'
            yield "    </node>\n"
            done += 1
            if self._settings.progress_callback:
                self._settings.progress_callback(done, total)

        for eid, edge, src, tgt in edges:
            attrs = self._build_edge_attrs(edge)
            yield f'    <edge id="{self._safe(eid)}" source="{self._safe(src)}" target="{self._safe(tgt)}">\n'
            yield f'      <data key="edge_label">{self._safe(attrs["label"])}</data>\n'
            yield f'      <data key="edge_confidence">{attrs["confidence_score"]}</data>\n'
            yield f'      <data key="edge_trust">{attrs["trust_weight"]}</data>\n'
            yield "    </edge>\n"
            done += 1
            if self._settings.progress_callback:
                self._settings.progress_callback(done, total)

        yield "  </graph>\n"

        if self._settings.include_metadata:
            meta = self._metadata_dict()
            yield '  <data key="metadata">\n'
            yield f"    <![CDATA[{json.dumps(meta, indent=2)}]]>\n"
            yield "  </data>\n"

        yield "</graphml>\n"

    def _dot_iter(self) -> Iterator[str]:
        nodes = self._get_node_list()
        edges = self._get_edge_triples()
        total = len(nodes) + len(edges)
        done = 0
        indent = "  "

        yield "graph G {\n"
        yield f'{indent}graph [label="IntelGraph Export"];\n'
        yield f"{indent}node [shape=box, style=rounded];\n"

        for nid, node in nodes:
            attrs = self._build_node_attrs(node)
            parts = []
            for key, val in attrs.items():
                if val is not None and val != "":
                    parts.append(f"{key}={self._dot_id(str(val))}")
            attr_str = ", ".join(parts)
            if attr_str:
                yield f"{indent}{self._dot_id(nid)} [{attr_str}];\n"
            else:
                yield f"{indent}{self._dot_id(nid)};\n"
            done += 1
            if self._settings.progress_callback:
                self._settings.progress_callback(done, total)

        for _eid, edge, src, tgt in edges:
            attrs = self._build_edge_attrs(edge)
            parts = [f"label={self._dot_id(attrs['label'])}"]
            parts.append(f"confidence={attrs['confidence_score']}")
            parts.append(f"trust={attrs['trust_weight']}")
            attr_str = ", ".join(parts)
            yield f"{indent}{self._dot_id(src)} -- {self._dot_id(tgt)} [{attr_str}];\n"
            done += 1
            if self._settings.progress_callback:
                self._settings.progress_callback(done, total)

        if self._settings.include_metadata:
            meta = self._metadata_dict()
            yield f"{indent}// Metadata: {json.dumps(meta)}\n"

        yield "}\n"

    def _json_iter(self) -> Iterator[str]:
        nodes = self._get_node_list()
        edges = self._get_edge_triples()
        total = len(nodes) + len(edges)
        done = 0
        p = self._settings.pretty
        nl = "\n" if p else ""
        sp = "  " if p else ""

        yield "{" + nl
        yield f'{sp}"graph": {{' + nl
        yield f'{sp}{sp}"directed": false,' + nl
        yield f'{sp}{sp}"nodes": [' + nl

        for i, (nid, node) in enumerate(nodes):
            attrs = self._build_node_attrs(node)
            entry = {"id": nid, **attrs}
            j = json.dumps(entry, indent=2) if p else json.dumps(entry, separators=(",", ":"))
            lines = j.split("\n")
            for line in lines:
                yield f"{sp}{sp}{sp}{line}{nl}"
            if i < len(nodes) - 1:
                yield ","
            yield nl
            done += 1
            if self._settings.progress_callback:
                self._settings.progress_callback(done, total)

        yield f"{sp}{sp}]," + nl
        yield f'{sp}{sp}"edges": [' + nl

        for i, (eid, edge, src, tgt) in enumerate(edges):
            attrs = self._build_edge_attrs(edge)
            entry = {"id": eid, "source": src, "target": tgt, **attrs}
            j = json.dumps(entry, indent=2) if p else json.dumps(entry, separators=(",", ":"))
            lines = j.split("\n")
            for line in lines:
                yield f"{sp}{sp}{sp}{line}{nl}"
            if i < len(edges) - 1:
                yield ","
            yield nl
            done += 1
            if self._settings.progress_callback:
                self._settings.progress_callback(done, total)

        yield f"{sp}{sp}]" + nl
        meta = self._metadata_dict()
        if meta:
            yield f"{sp}}}," + nl
            yield f'{sp}"metadata": {json.dumps(meta, indent=2 if p else None)}' + nl
        else:
            yield f"{sp}}}" + nl
        yield "}" + nl

    def _gexf_iter(self) -> Iterator[str]:
        nodes = self._get_node_list()
        edges = self._get_edge_triples()
        total = len(nodes) + len(edges)
        done = 0

        yield '<?xml version="1.0" encoding="UTF-8"?>\n'
        yield '<gexf xmlns="http://gexf.net/1.3" version="1.3">\n'
        yield '  <meta lastmodifieddate="' + time.strftime("%Y-%m-%d") + '">\n'
        yield "    <creator>IntelGraph</creator>\n"
        yield "    <description>Intelligence Graph Export</description>\n"
        yield "  </meta>\n"
        yield '  <graph mode="static" defaultedgetype="undirected">\n'

        # Attribute definitions
        yield '    <attributes class="node">\n'
        yield '      <attribute id="label" title="Label" type="string"/>\n'
        yield '      <attribute id="entity_type" title="Entity Type" type="string"/>\n'
        yield '      <attribute id="confidence_score" title="Confidence" type="integer"/>\n'
        yield '      <attribute id="trust_score" title="Trust" type="integer"/>\n'
        yield '      <attribute id="threat_score" title="Threat Score" type="float"/>\n'
        yield '      <attribute id="first_seen" title="First Seen" type="string"/>\n'
        yield '      <attribute id="last_seen" title="Last Seen" type="string"/>\n'
        yield "    </attributes>\n"
        yield '    <attributes class="edge">\n'
        yield '      <attribute id="edge_label" title="Label" type="string"/>\n'
        yield '      <attribute id="edge_confidence" title="Confidence" type="integer"/>\n'
        yield '      <attribute id="edge_trust" title="Trust Weight" type="integer"/>\n'
        yield "    </attributes>\n"

        yield "    <nodes>\n"
        for nid, node in nodes:
            attrs = self._build_node_attrs(node)
            yield f'      <node id="{self._safe(nid)}" label="{self._safe(attrs.get("label", nid[:8]))}">\n'
            yield "        <attvalues>\n"
            for key in (
                "entity_type",
                "confidence_score",
                "trust_score",
                "threat_score",
                "first_seen",
                "last_seen",
            ):
                if key in attrs and attrs[key] is not None and attrs[key] != "":
                    yield f'          <attvalue for="{key}" value="{self._safe(str(attrs[key]))}"/>\n'
            yield "        </attvalues>\n"
            # Temporal (spell) support for Gephi timeline
            try:
                last_seen = node.entity.last_seen
                first_seen = node.entity.first_seen
                if last_seen and first_seen:
                    yield (
                        '        <spell start="'
                        + first_seen.isoformat()
                        + '" end="'
                        + last_seen.isoformat()
                        + '"/>\n'
                    )
                elif first_seen:
                    yield '        <spell start="' + first_seen.isoformat() + '"/>\n'
            except AttributeError:
                pass
            yield "      </node>\n"
            done += 1
            if self._settings.progress_callback:
                self._settings.progress_callback(done, total)

        yield "    </nodes>\n"
        yield "    <edges>\n"

        for _i, (eid, edge, src, tgt) in enumerate(edges):
            attrs = self._build_edge_attrs(edge)
            yield f'      <edge id="{self._safe(eid)}" source="{self._safe(src)}" target="{self._safe(tgt)}" label="{self._safe(attrs.get("label", ""))}">\n'
            yield "        <attvalues>\n"
            yield f'          <attvalue for="edge_confidence" value="{attrs.get("confidence_score", 0)}"/>\n'
            yield f'          <attvalue for="edge_trust" value="{attrs.get("trust_weight", 0)}"/>\n'
            yield "        </attvalues>\n"
            yield "      </edge>\n"
            done += 1
            if self._settings.progress_callback:
                self._settings.progress_callback(done, total)

        yield "    </edges>\n"
        yield "  </graph>\n"
        yield "</gexf>\n"

    def _csv_iter(self) -> Iterator[str]:
        nodes = self._get_node_list()
        edges = self._get_edge_triples()

        # Nodes CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "node_id",
                "label",
                "entity_type",
                "confidence_score",
                "trust_score",
                "threat_score",
                "first_seen",
                "last_seen",
            ]
        )
        for nid, node in nodes:
            attrs = self._build_node_attrs(node)
            writer.writerow(
                [
                    nid,
                    attrs.get("label", ""),
                    attrs.get("entity_type", ""),
                    attrs.get("confidence_score", ""),
                    attrs.get("trust_score", ""),
                    attrs.get("threat_score", ""),
                    attrs.get("first_seen", ""),
                    attrs.get("last_seen", ""),
                ]
            )
        yield output.getvalue()

        yield "\n--- EDGES ---\n"

        # Edges CSV
        output2 = io.StringIO()
        writer2 = csv.writer(output2)
        writer2.writerow(
            ["edge_id", "source", "target", "relationship_type", "confidence_score", "trust_weight"]
        )
        for eid, edge, src, tgt in edges:
            rel = edge.relationship
            writer2.writerow(
                [
                    eid,
                    src,
                    tgt,
                    rel.type.type_name if hasattr(rel, "type") else "",
                    rel.confidence_score,
                    rel.trust_weight,
                ]
            )
        yield output2.getvalue()
