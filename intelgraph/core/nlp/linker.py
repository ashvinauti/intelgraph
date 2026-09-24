from __future__ import annotations

from typing import Any


class EntityLinker:
    def __init__(self, graph: Any | None = None) -> None:
        self._graph = graph
        self._mention_log: list[dict[str, Any]] = []

    def set_graph(self, graph: Any) -> None:
        self._graph = graph

    def link(self, text: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
        if not self._graph:
            return self._no_graph_result(entities)
        matched: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []
        for ent in entities:
            node_id = self._find_in_graph(ent)
            if node_id:
                matched.append({"mention": ent, "graph_node_id": node_id, "confidence": 0.85})
            else:
                unmatched.append({"mention": ent, "graph_node_id": None, "confidence": 0.0})
        total = len(entities)
        accuracy = len(matched) / total if total else 1.0
        result = {
            "matched": matched,
            "unmatched": unmatched,
            "total_mentions": total,
            "matched_count": len(matched),
            "link_accuracy": round(accuracy, 4),
            "text_snippet": text[:100],
        }
        self._mention_log.append(result)
        return result

    def link_accuracy_stats(self, window: int = 100) -> dict[str, Any]:
        recent = self._mention_log[-window:]
        total_mentions = sum(r["total_mentions"] for r in recent)
        total_matched = sum(r["matched_count"] for r in recent)
        return {
            "total_mentions": total_mentions,
            "total_matched": total_matched,
            "link_accuracy": round(total_matched / total_mentions, 4) if total_mentions else 1.0,
            "documents_processed": len(recent),
        }

    def _find_in_graph(self, entity: dict[str, Any]) -> str | None:
        if not self._graph:
            return None
        text = entity.get("normalized", entity.get("text", "")).lower()
        for node_id, node_data in self._graph.nodes.items():
            name = node_data.get("name", "").lower()
            aliases = node_data.get("aliases", [])
            if text == name or text in [a.lower() for a in aliases]:
                return node_id
        for node_id, node_data in self._graph.nodes.items():
            name = node_data.get("name", "").lower()
            if text in name or name in text:
                return node_id
        for node_id, node_data in self._graph.nodes.items():
            props = node_data.get("properties", {})
            ip = props.get("ip", "").lower()
            domain = props.get("domain", "").lower()
            cve = props.get("cve_id", "").lower()
            if text == ip or text == domain or text == cve:
                return node_id
        return None

    def _no_graph_result(self, entities: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(entities)
        result = {
            "matched": [],
            "unmatched": [
                {"mention": e, "graph_node_id": None, "confidence": 0.0} for e in entities
            ],
            "total_mentions": total,
            "matched_count": 0,
            "link_accuracy": 0.0,
            "text_snippet": "",
            "note": "Graph not available",
        }
        self._mention_log.append(result)
        return result
