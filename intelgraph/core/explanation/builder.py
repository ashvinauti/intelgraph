from __future__ import annotations

from typing import Any


class ExplanationBuilder:
    """Builds a human-readable + structured explanation chain for an incident.

    Uses only existing pipeline data — no new motors, no new extraction.
    Cross-references incidents, alerts, relationships, contradictions,
    truth entries, chain stats, graph nodes, merge audit, safety/review records.
    """

    def __init__(self, pipeline_result: dict[str, Any]) -> None:
        self._r = pipeline_result
        self._node_index: dict[str, dict[str, Any]] = {}
        self._init_node_index()

    def _init_node_index(self) -> None:
        for n in self._r.get("graph_nodes_summary", []):
            nid = n.get("node_id", "")
            if nid:
                self._node_index[nid] = n

    def _find_entity_id(self, incident: dict[str, Any]) -> str:
        """Extract the primary entity ID from incident."""
        eid = incident.get("entity_id", "") or (incident.get("entity_ids") or [None])[0] or ""
        if eid:
            return eid
        msg = incident.get("message", "")
        truth_entries = self._r.get("truth_entries", [])
        for te in truth_entries:
            key = te.get("key", "")
            if key and key in msg:
                return key
        if truth_entries:
            return truth_entries[0].get("key", "")
        return ""

    def _collect_entity_evidence(self, entity_id: str) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        entity_nid = entity_id.replace(".", "_").replace(":", "_")

        # Step 1: Graph node info (entity type + evidence count)
        node_info = self._node_index.get(entity_nid, {})
        entity_type = node_info.get("entity_type", "?")
        evidence_count = node_info.get("evidence_count", 0)
        node_conf_pct = node_info.get("confidence", 0)
        entity_identifier = node_info.get("entity_identifier", entity_id)
        steps.append(
            {
                "order": len(steps) + 1,
                "phase": "source_ingestion",
                "label": "Source Ingestion",
                "detail": f"Entity '{entity_identifier}' (type: {entity_type}, conf: {node_conf_pct}, {evidence_count} evidence)",
                "evidence": f"Graph node: {entity_identifier}",
                "confidence": (node_conf_pct / 100.0) or 1.0,
                "entity_type": entity_type,
                "evidence_count": evidence_count,
            }
        )

        # Step 1.5: Merge audit — check if entity was merged from multiple sources
        merge_audit = self._r.get("merge_audit", [])
        for entry in merge_audit:
            if entry.get("target_entity_id", "") == entity_nid:
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "phase": "entity_merge",
                        "label": "Entity Merge",
                        "detail": f"Merged with '{entry.get('source_entity_id', '?')}' "
                        f"(strategy: {entry.get('merge_strategy', '?')}, score: {entry.get('confidence', 0)})",
                        "evidence": f"Fields: {entry.get('fields_merged', [])}, "
                        f"Source: {entry.get('source_attribution', '?')}",
                        "confidence": entry.get("confidence", 0),
                        "merge_source": entry.get("source_entity_id", ""),
                        "merge_strategy": entry.get("merge_strategy", ""),
                    }
                )

        # Step 2: Source texts where this entity appears
        source_texts = self._r.get("source_texts", [])
        entity_lower = entity_id.lower()
        for i, st in enumerate(source_texts):
            if entity_lower in st.lower():
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "phase": "source_text",
                        "label": "Source Text",
                        "detail": f"Appears in source text #{i + 1}",
                        "evidence": st[:200],
                        "confidence": 1.0,
                    }
                )
                break

        # Step 3: Truth entries for this entity
        for te in self._r.get("truth_entries", []):
            if te.get("key", "") == entity_id:
                truth = te.get("truth", {})
                raw_conf = truth.get("confidence", 0)
                normal_conf = raw_conf / 100.0 if raw_conf > 1 else raw_conf
                te_identifier = self._node_index.get(entity_nid, {}).get(
                    "entity_identifier", entity_id
                )
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "phase": "truth_estimation",
                        "label": "Truth Assessment",
                        "detail": f"True value for entity '{te_identifier}': conf={raw_conf}",
                        "evidence": f"Source: {truth.get('source', '?')}, Value: {truth.get('value', {})}",
                        "confidence": normal_conf,
                    }
                )

        # Step 4: Contradictions involving this entity
        for c in self._r.get("contradictions", []):
            fa = c.get("fact_a", {})
            fb = c.get("fact_b", {})
            if fa.get("entity", "") == entity_id or fb.get("entity", "") == entity_id:
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "phase": "contradiction",
                        "label": "Contradiction Detection",
                        "detail": c.get("explanation", ""),
                        "evidence": f"{fa.get('source', '?')}: {fa.get('value', '?')} vs {fb.get('source', '?')}: {fb.get('value', '?')}",
                        "confidence": c.get("confidence", 0),
                        "resolution": c.get("resolution", "unresolved"),
                    }
                )

        # Step 5: Relationships involving this entity
        for r in self._r.get("relationships", []):
            src_text = (r.get("source") or {}).get("normalized", "") or r.get("subject", "")
            tgt_text = (r.get("target") or {}).get("normalized", "") or r.get("object", "")
            src_nid = src_text.replace(".", "_").replace(":", "_")
            tgt_nid = tgt_text.replace(".", "_").replace(":", "_")
            if entity_nid in (src_nid, tgt_nid):
                other_text = tgt_text if src_nid == entity_nid else src_text
                other_id = tgt_nid if src_nid == entity_nid else src_nid
                other_info = self._node_index.get(other_id, {})
                other_type = other_info.get("entity_type", "?")
                conf_bucket = (
                    "verb"
                    if r.get("confidence", 0) >= 0.55
                    else ("sentence" if r.get("confidence", 0) >= 0.4 else "document")
                )
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "phase": "relationship",
                        "label": f"Relationship: {r.get('relation', '?')}",
                        "detail": f"'{entity_id}' -> '{other_text}' (type: {other_type}, relation: {r.get('relation', '?')})",
                        "evidence": f"Co-occurrence level: {conf_bucket}, confidence: {r.get('confidence', 0)}",
                        "confidence": r.get("confidence", 0),
                        "relation_type": r.get("relation", ""),
                        "cooccurrence_level": conf_bucket,
                        "target_entity_id": other_id,
                        "target_entity_type": other_type,
                    }
                )

        # Step 6: Chain / evidence history
        chain_stats = self._r.get("chain_stats", {})
        if chain_stats:
            steps.append(
                {
                    "order": len(steps) + 1,
                    "phase": "evidence_chain",
                    "label": "Evidence Chain",
                    "detail": f"Total chains: {chain_stats.get('total_chain_count', '?')}, Avg confidence: {chain_stats.get('avg_confidence', '?')}",
                    "evidence": str(chain_stats),
                    "confidence": chain_stats.get("avg_confidence", 0),
                }
            )

        # Step 7: Alert generation
        for alert in self._r.get("alerts", []):
            ctx = alert.get("context", {})
            if ctx.get("entity_id", "") == entity_id:
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "phase": "alert",
                        "label": "Alert Generation",
                        "detail": f"Category: {alert.get('category', '?')}, Severity: {alert.get('severity', '?')}",
                        "evidence": alert.get("message", ""),
                        "confidence": ctx.get("confidence", 0),
                        "metric_key": alert.get("metric_key", ""),
                        "current_value": alert.get("current_value", 0),
                        "threshold_value": alert.get("threshold_value", 0),
                    }
                )

        # Step 8: SafetyGovernor decision
        sr = self._r.get("safety_result")
        if sr:
            steps.append(
                {
                    "order": len(steps) + 1,
                    "phase": "safety_governor",
                    "label": "Safety Decision",
                    "detail": f"Approval level: {sr.get('approval_level', '?')}, Risk: {sr.get('risk_score', 0)}",
                    "evidence": f"Decision: {sr.get('action_description', '?')}, Violations: {sr.get('violations', [])}",
                    "confidence": 1 - sr.get("risk_score", 0),
                    "approval_level": sr.get("approval_level", ""),
                    "risk_score": sr.get("risk_score", 0),
                }
            )

        # Step 9: Review outcome
        rr = self._r.get("review_record")
        if rr:
            steps.append(
                {
                    "order": len(steps) + 1,
                    "phase": "human_review",
                    "label": "Human Review",
                    "detail": f"Outcome: {rr.get('outcome', '?')}, Reviewer: {rr.get('reviewer', '?')}",
                    "evidence": rr.get("notes", ""),
                    "confidence": 1.0,
                }
            )

        # Step 10: Incident creation
        entity_identifier_step10 = self._node_index.get(entity_nid, {}).get(
            "entity_identifier", entity_id
        )
        steps.append(
            {
                "order": len(steps) + 1,
                "phase": "incident",
                "label": "Incident Record",
                "detail": f"Incident primary entity: '{entity_identifier_step10}'",
                "evidence": "Created by IncidentControlCenter via pipeline",
                "confidence": 1.0,
            }
        )

        return steps

    def _build_narrative(self, steps: list[dict[str, Any]]) -> str:
        lines = ["=== EVIDENCE CHAIN ===", ""]
        for s in steps:
            phase_emoji = {
                "source_ingestion": "📥",
                "source_text": "📄",
                "entity_merge": "🔀",
                "truth_estimation": "📊",
                "contradiction": "⚡",
                "relationship": "🔗",
                "evidence_chain": "🔬",
                "alert": "🚨",
                "safety_governor": "🛡️",
                "human_review": "👤",
                "incident": "📋",
            }.get(s["phase"], "•")
            lines.append(f"  {phase_emoji} Step {s['order']}: {s['label']}")
            lines.append(f"     {s['detail']}")
            if s.get("evidence"):
                lines.append(f"     Evidence: {s['evidence'][:200]}")
            if s.get("confidence"):
                raw = s["confidence"]
                pct = raw if raw > 1 else raw * 100
                lines.append(f"     Confidence: {pct:.2f}%")
            lines.append("")
        return "\n".join(lines)

    def explain(self, incident_id: str) -> dict[str, Any]:
        """Produce full explanation for a given incident ID."""
        incident = None
        for inc in self._r.get("incidents", []):
            if inc.get("alert_id", "") == incident_id or inc.get("id") == incident_id:
                incident = inc
                break
        if not incident:
            for alert in self._r.get("alerts", []):
                if alert.get("alert_id", "") == incident_id or alert.get("id") == incident_id:
                    incident = alert
                    break

        if not incident:
            return {
                "error": f"Incident '{incident_id}' not found",
                "available_incidents": [
                    i.get("id") or i.get("alert_id") for i in self._r.get("incidents", [])
                ]
                + [a.get("alert_id") for a in self._r.get("alerts", [])],
            }

        entity_id = self._find_entity_id(incident)
        if not entity_id:
            tes = self._r.get("truth_entries", [])
            entity_id = tes[0].get("key", "") if tes else "unknown"

        steps = self._collect_entity_evidence(entity_id)
        narrative = self._build_narrative(steps)

        entity_identifier = self._node_index.get(
            entity_id.replace(".", "_").replace(":", "_"), {}
        ).get("entity_identifier", entity_id)

        return {
            "incident_id": incident_id,
            "incident": incident,
            "primary_entity": entity_identifier,
            "chain_length": len(steps),
            "steps": steps,
            "narrative": narrative,
            "structured": {
                "entity": entity_identifier,
                "entity_type": steps[0].get("entity_type", "?") if steps else "?",
                "evidence_count": steps[0].get("evidence_count", 0) if steps else 0,
                "merge_entries": len(self._r.get("merge_audit", [])),
                "source_count": self._r.get("source_count", 0),
                "relationship_count": self._r.get("relationship_count", 0),
                "contradiction_count": self._r.get("contradiction_count", 0),
                "alert_count": self._r.get("alert_count", 0),
                "graph_nodes_summary_count": len(self._r.get("graph_nodes_summary", [])),
            },
        }
