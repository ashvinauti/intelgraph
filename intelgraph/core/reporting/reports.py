from collections.abc import Callable
from datetime import UTC
from typing import Any

from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.reporting.formatter import format_output


class ReportBuilder:
    def __init__(
        self,
        verification_lookup: Callable[[str], dict[str, Any] | None] | None = None,
        chain_lookup: Callable[[str], dict[str, Any] | None] | None = None,
        source_lookup: Callable[[str], dict[str, Any] | None] | None = None,
        graph: IntelligenceGraph | None = None,
    ) -> None:
        self._verification_lookup = verification_lookup
        self._chain_lookup = chain_lookup
        self._source_lookup = source_lookup
        self._graph = graph

    def entity_report(self, entity_id: str, fmt: str = "json") -> str:
        data: dict[str, Any] = {"entity_id": entity_id}
        vrec = self._verification_lookup(entity_id) if self._verification_lookup else None
        chain = self._chain_lookup(entity_id) if self._chain_lookup else None
        node = self._graph.get_node(entity_id) if self._graph else None

        if node:
            data["entity_type"] = node.entity_type
            ent = node.entity
            attrs: dict[str, Any] = {}
            for attr in ("name", "domain_name", "address", "username", "ip", "fingerprint"):
                val = getattr(ent, attr, None)
                if val:
                    attrs[attr] = val
            data["attributes"] = attrs

        if vrec:
            data["verification_status"] = vrec.get("verification_state", "unknown")
            data["confidence"] = vrec.get("confidence", 0)
        if chain:
            data["evidence_count"] = len(chain.get("evidence", []))
        else:
            data["evidence_count"] = 0

        return format_output("Entity", data, fmt)

    def evidence_report(self, entity_id: str, fmt: str = "json") -> str:
        chain = self._chain_lookup(entity_id) if self._chain_lookup else None
        if chain is None:
            data: dict[str, Any] = {"entity_id": entity_id, "error": "No evidence chain found"}
            return format_output("Evidence", data, fmt)
        data = dict(chain)
        if "evidence" in data:
            data["evidence_count"] = len(data["evidence"])
        return format_output("Evidence", data, fmt)

    def verification_report(self, entity_id: str, fmt: str = "json") -> str:
        vrec = self._verification_lookup(entity_id) if self._verification_lookup else None
        if vrec is None:
            data: dict[str, Any] = {"entity_id": entity_id, "error": "No verification record found"}
            return format_output("Verification", data, fmt)
        return format_output("Verification", vrec, fmt)

    def source_report(self, source_id: str, fmt: str = "json") -> str:
        src = self._source_lookup(source_id) if self._source_lookup else None
        if src is None:
            data: dict[str, Any] = {"source_id": source_id, "error": "No source found"}
            return format_output("Source", data, fmt)
        return format_output("Source", src, fmt)

    def full_report(self, fmt: str = "json") -> str:
        from datetime import datetime

        data: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "entity_count": 0,
            "edge_count": 0,
            "entities": [],
            "evidence": [],
            "verifications": [],
            "sources": [],
        }

        if self._graph:
            data["entity_count"] = self._graph.node_count
            data["edge_count"] = self._graph.edge_count
            for node in self._graph.nodes.values():
                eid = node.id
                ent_data: dict[str, Any] = {"entity_id": eid, "entity_type": node.entity_type}
                vrec = self._verification_lookup(eid) if self._verification_lookup else None
                if vrec:
                    ent_data["verification_state"] = vrec.get("verification_state", "unknown")
                    ent_data["confidence"] = vrec.get("confidence", 0)
                data["entities"].append(ent_data)

                chain = self._chain_lookup(eid) if self._chain_lookup else None
                if chain:
                    data["evidence"].append(
                        {
                            "entity_id": eid,
                            "confidence": chain.get("confidence", 0),
                            "contradiction_score": chain.get("contradiction_score", 0),
                            "status": chain.get("status", "unknown"),
                            "evidence_count": len(chain.get("evidence", [])),
                        }
                    )
                    data["verifications"].append(
                        {
                            "entity_id": eid,
                            "state": (vrec or {}).get("verification_state", "unknown"),
                            "confidence": (vrec or {}).get("confidence", 0),
                        }
                    )

        if self._source_lookup:
            pass

        return format_output("Full", data, fmt)
