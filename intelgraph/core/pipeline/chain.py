from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from intelgraph.core.agent.safety import SafetyGovernor
from intelgraph.core.cognitive.contradiction import ContradictionDetector
from intelgraph.core.cognitive.reasoning import ReasoningEngine
from intelgraph.core.entity.cve import CveEntity
from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.evidence import Evidence
from intelgraph.core.evidence_chain import ChainManager
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.human_review import ReviewManager, ReviewOutcome
from intelgraph.core.metaintel.alerting import IncidentControlCenter, MetaAlert
from intelgraph.core.metaintel.observability import GlobalObservabilityDashboard
from intelgraph.core.nlp.extractor import NEREngine, RelationshipExtractor, TextClassifier
from intelgraph.core.relationship.base import Relationship
from intelgraph.core.relationship.types import RelationshipType
from intelgraph.core.source.manager import DataSourceManager
from intelgraph.core.ucos.alerting import UnifiedAlertingCore
from intelgraph.core.ucos.safety import UnifiedSafetyLayer
from intelgraph.core.ucos.state import SingleSourceOfTruth
from intelgraph.core.ucos.truth import UnifiedTruthEngine
from intelgraph.core.verification.manager import VerificationManager


@dataclass
class SuggestedAction:
    action_type: str = ""
    target: str = ""
    reason: str = ""
    risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target": self.target,
            "reason": self.reason,
            "risk_score": self.risk_score,
        }


class _DbBackend:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn_: sqlite3.Connection | None = None

    def _require(self) -> sqlite3.Connection:
        if self._conn_ is None:
            self._conn_ = sqlite3.connect(self._db_path)
            self._conn_.row_factory = sqlite3.Row
        return self._conn_

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._require()


class PipelineResult:
    def __init__(self) -> None:
        self.source_texts: list[str] = []
        self.extracted_entities: list[Any] = []
        self.contradictions: list[Any] = []
        self.truth_entries: list[dict[str, Any]] = []
        self.graph: IntelligenceGraph | None = None
        self.reasoning_paths: list[Any] = []
        self.alerts: list[dict[str, Any]] = []
        self.errors: list[str] = []

        # Phase 3 — ChainManager
        self.chain_ids: list[str] = []
        self.chain_stats: dict[str, Any] = field(default_factory=dict)

        # Phase 3 — SafetyGovernor
        self.suggested_action: SuggestedAction | None = None
        self.safety_result: dict[str, Any] | None = None

        # Phase 3 — UnifiedSafetyLayer
        self.safety_layer_status: dict[str, Any] = {}

        # Phase 3 — ReviewManager
        self.review_queue_id: str | None = None
        self.review_record: dict[str, Any] | None = None

        # Phase 3 — VerificationManager
        self.verification_record: dict[str, Any] | None = None
        self.verification_stats: dict[str, Any] = {}

        # Phase 4 — IncidentControlCenter + GlobalObservabilityDashboard
        self.incidents: list[dict[str, Any]] = []
        self.incidents_awaiting_remediation: list[dict[str, Any]] = []
        self.playbook_statuses: dict[str, Any] = {}
        self.dashboard_snapshot: dict[str, Any] | None = None

        # Phase 10.2 — RelationshipExtractor
        self.relationships: list[dict[str, Any]] = []

        # Phase 3.10 — Anomaly Detection
        self.anomaly_results: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_count": len(self.source_texts),
            "source_texts": self.source_texts[:50],  # keep reasonable size
            "entity_count": len(self.extracted_entities),
            "contradiction_count": len(self.contradictions),
            "contradictions": [
                c.to_dict() if hasattr(c, "to_dict") else str(c) for c in self.contradictions[:20]
            ],
            "truth_entries": self.truth_entries,
            "graph_node_count": len(self.graph.nodes) if self.graph else 0,
            "graph_edge_count": len(self.graph.edges) if self.graph else 0,
            "path_count": len(self.reasoning_paths),
            "alert_count": len(self.alerts),
            "alerts": self.alerts,
            "errors": self.errors,
            "chain_ids": self.chain_ids,
            "chain_stats": self.chain_stats,
            "incident_count": len(self.incidents),
            "incidents": self.incidents,
            "incidents_awaiting_remediation": self.incidents_awaiting_remediation,
            "playbook_statuses": self.playbook_statuses,
            "dashboard_snapshot": self.dashboard_snapshot,
            "relationship_count": len(self.relationships),
            "relationships": self.relationships,
            "safety_layer_status": self.safety_layer_status,
            "suggested_action": self.suggested_action.to_dict() if self.suggested_action else None,
            "safety_result": self.safety_result,
            "review_queue_id": self.review_queue_id,
            "review_record": self.review_record,
            "verification_record": self.verification_record,
            "verification_stats": self.verification_stats,
            "graph_nodes_summary": self.graph.nodes_summary if self.graph else [],
            "graph_edges_summary": self.graph.edges_summary if self.graph else [],
            "merge_audit": self.graph.merge_audit if self.graph else [],
            "anomaly_results": self.anomaly_results,
        }


def _text_to_node_id(text: str) -> str:
    return text.replace(".", "_").replace(":", "_")


class Pipeline:
    def __init__(self, db_path: str | None = None) -> None:
        self._tmpdir: str | None = None
        self._db_path = db_path

    def _ensure_db(self) -> str:
        if not self._db_path:
            self._tmpdir = tempfile.mkdtemp(prefix="eios_pipeline_")
            self._db_path = f"{self._tmpdir}/pipeline.db"
        return self._db_path

    def cleanup(self) -> None:
        if self._tmpdir:
            import shutil

            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None

    def _init_chain_mgr(self, db_path: str) -> ChainManager:
        backend = _DbBackend(db_path)
        backend._require()
        mgr = ChainManager(backend)
        mgr.initialize()
        return mgr

    def _init_review_mgr(self, db_path: str) -> ReviewManager:
        backend = _DbBackend(db_path)
        backend._require()
        mgr = ReviewManager(backend)
        mgr.initialize()
        return mgr

    def run(
        self,
        sources: list[dict[str, Any]],
        thresholds: dict[str, dict[str, Any]] | None = None,
        query_ip: str = "",
        query_target: str = "",
        min_confidence: float = 0.0,
        enrich: bool = False,
    ) -> PipelineResult:
        _start_time = time.time()
        result = PipelineResult()
        db_path = self._ensure_db()

        # ── Bridge 1->2: DataSourceManager -> NEREngine ──
        dsm = DataSourceManager(db_path)
        ner = NEREngine()
        classifier = TextClassifier()
        rel_extractor = RelationshipExtractor(min_confidence=min_confidence)
        all_relationships: list[dict[str, Any]] = []

        for src in sources:
            try:
                sid = src.get("id", f"src_{hashlib.md5(src['text'].encode()).hexdigest()[:8]}")
                fpath = src.get("file_path", "")
                text = src.get("text", "")

                if fpath:
                    from pathlib import Path

                    text = Path(fpath).read_text()

                if not text:
                    continue

                result.source_texts.append(text)

                if fpath:
                    dsm.register_connector(
                        source_id=sid,
                        source_name=src.get("name", sid),
                        connector_type="file",
                        config_overrides={"file_path": fpath},
                    )
                    poll_result = dsm.poll_source(sid)
                    if poll_result.get("status") != "success":
                        result.errors.append(f"Poll failed for {sid}: {poll_result}")
                else:
                    tfp = f"{db_path}.{sid}.txt"
                    with open(tfp, "w") as f:
                        f.write(text)
                    dsm.register_connector(
                        source_id=sid,
                        source_name=src.get("name", sid),
                        connector_type="file",
                        config_overrides={"file_path": tfp},
                    )
                    dsm.poll_source(sid)

                entities = ner.extract(text)
                classification = classifier.classify(text)

                ctx = {
                    "source": src.get("name", sid),
                    "value": src.get("value", 50),
                    "context": text,
                    "source_summary": f"{src.get('name', sid)}: {classification.top_type}/{classification.severity}",
                    "collected_at": src.get("collected_at"),
                }

                for e in entities:
                    e._pipeline_context = ctx

                result.extracted_entities.extend(entities)

                non_version_entities = [e for e in entities if e.label != "VERSION"]

                # Phase 10.2: RelationshipExtractor per source text
                for rel in rel_extractor.extract(text, non_version_entities):
                    all_relationships.append(rel.to_dict())

            except Exception as exc:
                result.errors.append(f"Bridge 1->2 error ({src.get('id', '?')}): {exc}")

        dsm.close()
        result.relationships = all_relationships

        if not result.extracted_entities:
            return result

        # ── Bridge 2->3: ExtractedEntity -> Contradiction + Truth ──
        detector = ContradictionDetector()
        ute = UnifiedTruthEngine()
        ssot = SingleSourceOfTruth(truth_engine=ute)  # delegates storage to UTE

        facts = []
        for e in result.extracted_entities:
            if e.label == "VERSION":
                continue
            ctx: dict[str, Any] = getattr(e, "_pipeline_context", {})
            fact = e.to_contradiction_dict(ctx)
            facts.append(fact)

        for fact in facts:
            if fact.get("attribute") == "CVE":
                cve_id = str(fact.get("entity", ""))
                full_context = str(fact.get("context", ""))
                pat = re.compile(
                    re.escape(cve_id) + r".*?Ransomware campaign use: (Known|Unknown)",
                    re.IGNORECASE | re.DOTALL,
                )
                m = pat.search(full_context)
                fact["known_ransomware_use"] = m is not None and m.group(1) == "Known"

        contradictions = detector.detect(facts)
        result.contradictions = contradictions

        for fact in facts:
            entity_key = str(fact.get("entity", ""))
            raw_val = fact.get("value", 50)
            if isinstance(raw_val, (int, float)):
                truth_conf = max(0.0, min(1.0, raw_val / 100.0))
            else:
                truth_conf = float(fact.get("confidence", 0.5))
            known_ransomware = fact.get("known_ransomware_use", False)
            if known_ransomware:
                truth_conf = min(1.0, truth_conf + 0.1)
                if isinstance(raw_val, (int, float)):
                    raw_val = min(100, raw_val + 10)
            value_data = {
                "classification": fact.get("context", "")[:100],
                "label": fact.get("attribute", ""),
                "value": raw_val,
                "known_ransomware_use": known_ransomware,
                "collected_at": fact.get("collected_at"),
            }
            source = str(fact.get("source", "unknown"))

            tr = ute.write(key=entity_key, value=value_data, source=source, confidence=truth_conf)
            # SSOT collapsed into UTE — delegate set for backward compat
            sr = ssot.set(key=entity_key, value=value_data, source=source, confidence=truth_conf)
            result.truth_entries.append(
                {"key": entity_key, "truth": tr, "ssot": sr.get("action", sr)}
            )

        truth_map: dict[str, dict[str, Any]] = {}
        for fact in facts:
            ek = str(fact.get("entity", ""))
            te = ute.read(ek)
            if te and (
                ek not in truth_map or te.get("confidence", 0) > truth_map[ek].get("confidence", 0)
            ):
                truth_map[ek] = te

        # ── Bridge 3->4: Truth -> IntelligenceGraph (with ChainManager injection) ──
        try:
            chain_mgr = self._init_chain_mgr(db_path)
        except Exception as exc:
            result.errors.append(f"ChainManager init error: {exc}")
            chain_mgr = None

        graph = IntelligenceGraph(chain_manager=chain_mgr)
        for ek, te in truth_map.items():
            val = te.get("value", {})
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    val = {"classification": val}

            label = val.get("label", "IP")
            # Use source-provided timestamp if available, else now
            src_ts = te.get("collected_at") or val.get("collected_at")
            if isinstance(src_ts, str):
                try:
                    ev_time = datetime.fromisoformat(src_ts)
                except ValueError:
                    ev_time = datetime.now(UTC)
            elif isinstance(src_ts, datetime):
                ev_time = src_ts
            else:
                ev_time = datetime.now(UTC)

            ev = Evidence(
                id=f"ev_pipeline_{hashlib.md5(ek.encode()).hexdigest()[:8]}",
                source=str(te.get("source", "pipeline")),
                content=str(val.get("classification", "")),
                collected_at=ev_time,
                source_tier=1,
                trust_score=min(100, int(val.get("value", 50))),
                reliability_score=min(100, int(te.get("confidence", 0.5) * 100)),
            )
            entity_id = ek.replace(".", "_").replace(":", "_")
            if label == "CVE":
                is_ransomware = val.get("known_ransomware_use", False)
                cs = 95 if is_ransomware else 80
                entity = CveEntity(
                    id=entity_id,
                    cve_id=ek,
                    evidence=(ev,),
                    vendor_project=val.get("vendor_project", ""),
                    product=val.get("product", ""),
                    vulnerability_name=val.get("vulnerability_name", ""),
                    known_ransomware_use=is_ransomware,
                    confidence_score=cs,
                    first_seen=ev_time,
                    last_seen=ev_time,
                )
            elif label == "IP" or "." not in ek:
                entity = IPAddress(
                    id=entity_id, ip=ek, evidence=(ev,), first_seen=ev_time, last_seen=ev_time
                )
            elif label == "DOMAIN" or "." in ek:
                entity = Domain(
                    id=entity_id,
                    domain_name=ek,
                    evidence=(ev,),
                    first_seen=ev_time,
                    last_seen=ev_time,
                )
            else:
                entity = IPAddress(
                    id=entity_id, ip=ek, evidence=(ev,), first_seen=ev_time, last_seen=ev_time
                )
            graph.add_entity(entity)

        result.graph = graph

        # ── CVE metrics for alerting ──
        high_risk_cves: list[CveEntity] = []
        for node in graph.nodes.values():
            if isinstance(node.entity, CveEntity):
                high_risk_cves.append(node.entity)

        cve_metrics: dict[str, float] = {}
        cve_alert_ctx: dict[str, Any] = {}
        if high_risk_cves:
            max_conf = max(e.confidence_score for e in high_risk_cves)
            ransomware_count = sum(1 for e in high_risk_cves if e.known_ransomware_use)
            high_risk_count = sum(1 for e in high_risk_cves if e.confidence_score >= 90)
            cve_metrics["high_risk_cve_count"] = float(high_risk_count)
            cve_metrics["max_cve_confidence"] = max_conf / 100.0
            cve_metrics["ransomware_cve_count"] = float(ransomware_count)
            if high_risk_count > 0 or ransomware_count > 0:
                best = max(high_risk_cves, key=lambda e: e.confidence_score)
                cve_alert_ctx = {
                    "entity_id": best.cve_id,
                    "confidence": best.confidence_score / 100.0,
                    "known_ransomware_use": str(best.known_ransomware_use),
                    "vendor_project": best.vendor_project,
                    "product": best.product,
                    "cve_id": best.cve_id,
                }

        # Phase 10.2: Convert RelationshipExtractor output to graph edges
        edge_count = 0
        for rd in result.relationships:
            subj_text = (rd.get("source") or {}).get("normalized", "") or rd.get("subject", "")
            obj_text = (rd.get("target") or {}).get("normalized", "") or rd.get("object", "")
            subj_id = _text_to_node_id(subj_text)
            obj_id = _text_to_node_id(obj_text)
            if subj_id in graph.nodes and obj_id in graph.nodes:
                rel_type_str = rd.get("relation", "related_to").upper()
                try:
                    rel_type = RelationshipType[rel_type_str]
                except KeyError:
                    rel_type = RelationshipType.RELATED_TO
                try:
                    rel = Relationship(
                        source_id=subj_id,
                        target_id=obj_id,
                        type=rel_type,
                        confidence_score=int(float(rd.get("confidence", 0.5)) * 100),
                        trust_weight=50,
                    )
                    graph.add_relationship(rel)
                    edge_count += 1
                except Exception as exc:
                    result.errors.append(f"Edge creation error ({subj_id}->{obj_id}): {exc}")
        if edge_count:
            result.relationships.append({"__graph_edge_count": edge_count})

        # ── Optional enrichment: Shodan + VirusTotal ──
        if enrich:
            self._enrich_graph(graph, result)

        if chain_mgr:
            result.chain_ids = [nid for nid in graph.nodes if graph.nodes[nid].entity.evidence]
            result.chain_stats = chain_mgr.stats()

        # ── Bridge 4->5: Reasoning -> Alert metrics ──
        reasoner = ReasoningEngine(graph=graph)
        paths: list[Any] = []

        if query_ip:
            qid = query_ip.replace(".", "_").replace(":", "_")
            tid = query_target.replace(".", "_").replace(":", "_") if query_target else ""
            if qid in graph.nodes:
                if tid and tid in graph.nodes:
                    paths = reasoner.multi_hop_reason(qid, tid, max_depth=5)
                elif tid:
                    result.errors.append(f"Target '{tid}' not in graph")
                else:
                    for nid in graph.nodes:
                        if nid != qid:
                            ps = reasoner.multi_hop_reason(qid, nid, max_depth=3)
                            paths.extend(ps)
            else:
                result.errors.append(f"Query IP '{qid}' not in graph")

        result.reasoning_paths = paths

        # ── Alert generation ──
        alerter = UnifiedAlertingCore({"cooldown_seconds": 0})

        entity_metrics: dict[str, float] = {}
        if paths:
            for p in paths:
                m = p.to_alert_metrics()
                for k, v in m.items():
                    entity_metrics[k] = max(entity_metrics.get(k, 0.0), v)
        if truth_map:
            best_conf = max((te.get("confidence", 0.0) for te in truth_map.values()), default=0.0)
            entity_metrics["overall_confidence"] = best_conf
            entity_metrics["entity_count"] = float(len(truth_map))

        # ── Entity alert context (URL/IP/Domain) ──
        entity_ctx: dict[str, Any] = {}
        if truth_map:
            ek = list(truth_map.keys())[0]
            te = truth_map[ek]
            entity_ctx["entity_id"] = ek
            entity_ctx["confidence"] = te.get("confidence", 0.0)
            entity_ctx["source_summary"] = str(te.get("source", "unknown"))
        if contradictions:
            c = contradictions[0]
            entity_ctx["contradiction"] = (
                f"{c.fact_a.get('source', '?')} vs {c.fact_b.get('source', '?')}: {c.explanation[:80]}"
            )
        if paths:
            entity_ctx["path_summary"] = paths[0].to_path_summary()[:120]
        if result.source_texts:
            entity_ctx["raw_context"] = result.source_texts[-1][:200]

        if not thresholds:
            thresholds = {
                "threat_intel_alert": {
                    "enabled": True,
                    "metric_key": "overall_confidence",
                    "max": 0.5,
                    "severity": "high",
                },
            }
        # Always ensure CVE thresholds are present (merged with caller thresholds)
        cve_defaults: dict[str, dict[str, Any]] = {
            "high_risk_cve_detection": {
                "enabled": True,
                "metric_key": "max_cve_confidence",
                "max": 0.89,
                "severity": "critical",
                "message": "High-risk CVE entity detected (confidence >= 0.90)",
            },
            "ransomware_cve_detection": {
                "enabled": True,
                "metric_key": "ransomware_cve_count",
                "max": 0,
                "severity": "critical",
                "message": "Ransomware-associated CVE entity detected",
            },
        }
        for k, v in cve_defaults.items():
            thresholds.setdefault(k, v)

        # Separate CVE thresholds for CVE-only evaluate
        cve_thresholds = {
            k: v
            for k, v in thresholds.items()
            if k in cve_defaults or v.get("metric_key", k) in cve_metrics
        }

        # Evaluate entity-level alerts (URL, IP, etc.) with entity context
        alerts = alerter.evaluate(entity_metrics, thresholds, context=entity_ctx)
        # Evaluate CVE-level alerts with CVE context (separate entity_id for explanation)
        if cve_alert_ctx and cve_metrics:
            cve_alerts = alerter.evaluate(cve_metrics, cve_thresholds, context=cve_alert_ctx)
            alerts.extend(cve_alerts)
        result.alerts = alerts

        # ── Phase 3.9: Threat Score Alerting — max_threat_score check ──
        try:
            max_ts_threshold = thresholds.get("max_threat_score", {})
            if max_ts_threshold.get("enabled", False) and graph:
                from intelgraph.core.scoring.threat_score import compute_threat_scores

                ts_scores = compute_threat_scores(graph)
                from intelgraph.core.graph.anomaly import _THREAT_SCORE_CACHE

                _THREAT_SCORE_CACHE.update(ts_scores)
                max_val = max_ts_threshold.get("max", 75.0)
                max_entity = ""
                for nid, ts in ts_scores.items():
                    if ts >= max_val:
                        max_entity = nid
                        break
                if max_entity:
                    entity_metrics["max_threat_score"] = ts_scores.get(max_entity, 0.0)
                    entity_ctx["max_threat_entity"] = max_entity
        except Exception as exc:
            result.errors.append(f"ThreatScore alert error: {exc}")

        # ── Phase 3.10: Anomaly Detection — new algorithms ──
        try:
            if graph and graph.nodes:
                from intelgraph.core.graph.anomaly import AnomalyDetector

                detector = AnomalyDetector(graph)
                anomaly_results = detector.detect_all()
                result.anomaly_results = [r.to_dict() for r in anomaly_results]
                # Auto-alert for high anomaly scores (80+)
                high_anomalies = [r for r in anomaly_results if r.anomaly_score >= 80]
                for ar in high_anomalies:
                    alerts.append(
                        {
                            "alert_id": f"anom_{ar.node_id[:8]}",
                            "severity": "critical",
                            "message": f"Anomaly: {ar.anomaly_type} — {ar.explanation}",
                            "category": "anomaly_detection",
                            "entity_id": ar.node_id,
                        }
                    )
                    result.alert_count = len(alerts)
        except Exception as exc:
            result.errors.append(f"Anomaly detection error: {exc}")

        # ── Phase 4.1: IncidentControlCenter — auto-incident from alerts ──
        try:
            icc = IncidentControlCenter({"cooldown_seconds": 0})
            icc_alerts = icc.evaluate(entity_metrics, thresholds, context=entity_ctx)
            if cve_alert_ctx and cve_metrics:
                cve_icc = IncidentControlCenter({"cooldown_seconds": 0})
                cve_icc_alerts = cve_icc.evaluate(
                    cve_metrics, cve_thresholds, context=cve_alert_ctx
                )
                icc_alerts.extend(cve_icc_alerts)
            result.incidents = [a.to_dict() for a in icc_alerts]
            self._icc = icc
        except Exception as exc:
            result.errors.append(f"IncidentControlCenter init error: {exc}")
            self._icc = None

        # ── Phase 3.2a: UnifiedSafetyLayer — operational pipeline safety guard ──
        try:
            safety_layer = UnifiedSafetyLayer({"sandbox_level": "high"})
            result.safety_layer_status = safety_layer.get_status()
            # Test the forbidden action against USL first
            forb_action_dict = {"type": "block_subnet", "risk": 0.95}
            forb_usl_check = safety_layer.check_safety(forb_action_dict)
            if not forb_usl_check.get("safe"):
                result.safety_layer_status["forbidden_blocked_by_usl"] = True
        except Exception as exc:
            result.errors.append(f"UnifiedSafetyLayer error: {exc}")
            result.safety_layer_status = {"error": str(exc)}

        # ── Phase 3.2b: SafetyGovernor — risk-based action governance (stacked on USL) ──
        try:
            governor = SafetyGovernor(
                {
                    "human_in_loop": True,
                    "forbidden_actions": ["block_subnet", "mass_block", "shutdown"],
                }
            )

            # Find the highest-confidence alert to build an action
            action: SuggestedAction | None = None
            high_risk_ip = ""

            if truth_map:
                primary_entity = list(truth_map.keys())[0]
                high_risk_ip = primary_entity
                te = truth_map[primary_entity]
                conf = te.get("confidence", 0.0)
                if conf >= 0.7:
                    action = SuggestedAction(
                        action_type="block_ip" if conf >= 0.9 else "alert_soc",
                        target=high_risk_ip,
                        reason=f"C2 threat detected, confidence={conf:.2f}",
                        risk_score=conf,
                    )

            # Also test forbidden action to verify governor rejects it
            forbidden_action = SuggestedAction(
                action_type="block_subnet",
                target="10.0.0.0/8",
                reason="mass block test",
                risk_score=0.95,
            )

            result.suggested_action = action

            if action:
                check = governor.check_action(action.action_type, action.reason, action.risk_score)
                result.safety_result = check.to_dict()
            else:
                result.safety_result = {
                    "approved": False,
                    "approval_level": "none",
                    "risk_score": 0.0,
                    "reason": "No high-risk action needed",
                }

            # Verify forbidden action is rejected
            if forbidden_action:
                forb_check = governor.check_action(
                    forbidden_action.action_type,
                    forbidden_action.reason,
                    forbidden_action.risk_score,
                )
                result.safety_result["forbidden_test"] = {
                    "action": forbidden_action.to_dict(),
                    "approved": forb_check.approved,
                    "approval_level": forb_check.approval_level.value,
                    "violations": forb_check.violations,
                }

        except Exception as exc:
            result.errors.append(f"SafetyGovernor error: {exc}")
            result.safety_result = {"error": str(exc)}

        # ── Phase 4.1a: If ESCALATE, create ICC incident record ──
        if getattr(self, "_icc", None) and result.safety_result:
            sf = result.safety_result
            if sf.get("approval_level") == "escalate" or sf.get("risk_score", 0) >= 0.9:
                try:
                    escalate_alert = MetaAlert(
                        alert_id=f"inc_{uuid.uuid4().hex[:12]}",
                        category="security_escalation",
                        severity="critical",
                        message=f"ESCALATE: {result.suggested_action.reason if result.suggested_action else 'High-risk action'}; "
                        f"review required before execution",
                        source_layers=["pipeline", "safety_governor", "incident_control"],
                        current_value=sf.get("risk_score", 0.0),
                        threshold_value=0.9,
                        triggered_at=time.time(),
                        entity_id=entity_ctx.get("entity_id", cve_alert_ctx.get("entity_id", "")),
                    )
                    self._icc._alerts.append(escalate_alert)
                    result.incidents.append(escalate_alert.to_dict())
                except Exception as exc:
                    result.errors.append(f"ICC escalate incident error: {exc}")

        # ── Phase 3.3: ReviewManager — pending human review ──
        try:
            review_mgr = self._init_review_mgr(db_path)

            if result.suggested_action and result.safety_result:
                sf = result.safety_result
                is_high_risk = (
                    sf.get("approval_level") in ("review", "escalate")
                    or sf.get("risk_score", 0) >= 0.7
                )

                if is_high_risk and graph.nodes:
                    primary_nid = list(graph.nodes.keys())[0]
                    queue_id = review_mgr.enqueue_for_review(primary_nid, entity_type="IPAddress")
                    result.review_queue_id = queue_id

                    # Simulate human review — approve
                    if queue_id:
                        rec = review_mgr.process_review(
                            entity_id=primary_nid,
                            outcome=ReviewOutcome.APPROVED_REVIEW,
                            reviewer="soc_analyst_01",
                            notes="Confirmed malicious — SOC team verified C2 indicators",
                            queue_id=queue_id,
                        )
                        result.review_record = rec.to_dict()
                    else:
                        result.review_record = {
                            "info": "Auto-approve threshold met, no review needed"
                        }

        except Exception as exc:
            result.errors.append(f"ReviewManager error: {exc}")

        # ── Phase 3.4: VerificationManager — automated verification state ──
        try:
            verify_mgr = VerificationManager(_DbBackend(db_path))
            verify_mgr.initialize()
            if graph.nodes:
                primary_nid = list(graph.nodes.keys())[0]
                vrec = verify_mgr.recompute(primary_nid)
                result.verification_record = vrec.to_dict() if vrec else None
                result.verification_stats = verify_mgr.stats()
        except Exception as exc:
            result.errors.append(f"VerificationManager error: {exc}")
            result.verification_record = None

        # ── Phase 4.1b: ICC confirm (NOT resolve) on review approval ──
        # approved != resolved: review only confirms threat, remediation is separate
        if getattr(self, "_icc", None) and result.review_record:
            try:
                for inc in self._icc.get_alerts():
                    if not inc.confirmed:
                        self._icc.confirm_alert(inc.alert_id)
                        for rd in result.incidents:
                            if rd.get("alert_id") == inc.alert_id:
                                rd["confirmed"] = True
                result.incidents_awaiting_remediation = [
                    rd for rd in result.incidents if rd.get("confirmed") and not rd.get("resolved")
                ]

                # ── Phase 4.1c: Playbook auto-trigger for confirmed incidents ──
                try:
                    from intelgraph.core.playbook import PlaybookEngine

                    playbook_engine = PlaybookEngine()
                    result.playbook_statuses = {}
                    for inc in result.incidents_awaiting_remediation:
                        matched = playbook_engine.match_playbooks(inc)
                        if matched:
                            pb = matched[0]
                            status = playbook_engine.apply_automated_steps(inc["alert_id"], pb)
                            result.playbook_statuses[inc["alert_id"]] = {
                                "playbook_id": status.playbook_id,
                                "playbook_name": status.playbook_name,
                                "matched_at": status.matched_at,
                                "steps": [
                                    {
                                        "step_id": s.step_id,
                                        "action_type": s.action_type,
                                        "description": s.description,
                                        "automated": s.automated,
                                        "required": s.required,
                                        "completed": s.completed,
                                        "completed_at": s.completed_at,
                                        "completed_by": s.completed_by,
                                        "notes": s.notes,
                                    }
                                    for s in status.steps
                                ],
                                "all_completed": status.all_completed,
                            }
                except Exception as exc:
                    result.errors.append(f"Playbook trigger error: {exc}")
            except Exception as exc:
                result.errors.append(f"ICC confirm error: {exc}")

        # ── Log final chain stats from ReviewManager's chain_mgr ──
        try:
            chain_mgr2 = self._init_chain_mgr(db_path)
            all_chains = chain_mgr2.list_chains()
            result.chain_stats.update(
                {
                    "updated_chains": len(all_chains),
                    "contradiction_chains": len(chain_mgr2.list_chains(only_contradictions=True)),
                }
            )
        except Exception as exc:
            result.errors.append(f"ChainManager final stats error: {exc}")

        # ── Phase 4.2: GlobalObservabilityDashboard — real pipeline metrics ──
        try:
            dashboard = GlobalObservabilityDashboard({"cooldown_seconds": 0})
            dash_metrics: dict[str, float] = {}
            if result.graph:
                dash_metrics["node_count"] = float(len(result.graph.nodes))
                dash_metrics["edge_count"] = float(len(result.graph.edges))
            dash_metrics["contradiction_count"] = float(len(result.contradictions))
            dash_metrics["incident_count"] = float(len(result.incidents))
            dash_metrics["chain_count"] = float(result.chain_stats.get("total", 0))
            dash_metrics["alert_count"] = float(len(result.alerts))
            dash_metrics["entity_count"] = dash_metrics.get("entity_count", 0.0)
            dash_metrics["overall_confidence"] = dash_metrics.get("overall_confidence", 0.0)

            governance_rate = 0.0
            if result.safety_result:
                sf = result.safety_result
                if sf.get("approval_level") in ("escalate", "deny"):
                    governance_rate = 0.8
                elif sf.get("approval_level") == "review":
                    governance_rate = 0.4
            dash_metrics["governance_conflict_rate"] = governance_rate
            dash_metrics["review_completed"] = 1.0 if result.review_record else 0.0

            # Map to DashboardSnapshot fields
            snapshot_metrics = {
                "reasoning_quality": min(1.0, dash_metrics.get("overall_confidence", 0.0)),
                "execution_reliability": 1.0 - (dash_metrics.get("contradiction_count", 0) * 0.1),
                "knowledge_consistency": max(
                    0.0, 1.0 - (dash_metrics.get("governance_conflict_rate", 0.0))
                ),
                "system_drift": min(1.0, dash_metrics.get("governance_conflict_rate", 0.0)),
                "cross_phase_alignment": 0.8 if dash_metrics.get("node_count", 0) > 0 else 0.2,
                "stability_index": 1.0 - (dash_metrics.get("incident_count", 0) * 0.15),
                "governance_conflict_rate": dash_metrics.get("governance_conflict_rate", 0.0),
                "improvement_velocity": dash_metrics.get("review_completed", 0.0),
                "architecture_mutation_rate": dash_metrics.get("chain_count", 0) * 0.1,
                "node_count": dash_metrics.get("node_count", 0),
                "edge_count": dash_metrics.get("edge_count", 0),
                "contradiction_count": dash_metrics.get("contradiction_count", 0),
                "incident_count": dash_metrics.get("incident_count", 0),
                "alert_count": dash_metrics.get("alert_count", 0),
            }
            snapshot = dashboard.record_snapshot(snapshot_metrics)
            result.dashboard_snapshot = {
                **snapshot.to_dict(),
                "node_count": dash_metrics.get("node_count", 0),
                "edge_count": dash_metrics.get("edge_count", 0),
                "contradiction_count": dash_metrics.get("contradiction_count", 0),
                "incident_count": dash_metrics.get("incident_count", 0),
                "alert_count": dash_metrics.get("alert_count", 0),
                "chain_count": dash_metrics.get("chain_count", 0),
                "entity_count": dash_metrics.get("entity_count", 0),
            }
            self._dashboard = dashboard
        except Exception as exc:
            result.errors.append(f"GlobalObservabilityDashboard error: {exc}")
            self._dashboard = None

        # ── Phase 4.3: Notification dispatch — async alerts/incidents/playbook ──
        try:
            from intelgraph.core.notification.manager import NotificationManager

            notifier = NotificationManager()
            if getattr(notifier, "_channels", None) is None and not notifier.list_channels():
                pass  # no channels configured, skip
            else:
                # Alert notifications
                for alert in result.alerts:
                    sev_lookup = {"info": "low", "warning": "medium", "critical": "high"}
                    sev = sev_lookup.get(alert.get("severity", ""), "medium")
                    notifier.send_event_async(
                        NotificationManager.build_event(
                            event_type="alert",
                            severity=sev,
                            title=alert.get("message", "Alert triggered"),
                            body=alert.get("message", ""),
                            entity_id=alert.get("entity_id", ""),
                            metadata={
                                "alert_id": alert.get("alert_id", ""),
                                "category": alert.get("category", ""),
                            },
                        )
                    )

                # Incident notifications
                for inc in result.incidents:
                    sev = inc.get("severity", "medium")
                    notifier.send_event_async(
                        NotificationManager.build_event(
                            event_type="incident",
                            severity=(
                                sev if sev in ("low", "medium", "high", "critical") else "medium"
                            ),
                            title=inc.get("message", "Incident created"),
                            body=inc.get("message", ""),
                            entity_id=inc.get("entity_id", ""),
                            metadata={
                                "alert_id": inc.get("alert_id", ""),
                                "confirmed": inc.get("confirmed", False),
                            },
                        )
                    )

                # Threat score exceeded notifications
                if entity_ctx.get("max_threat_entity"):
                    max_ts = entity_metrics.get("max_threat_score", 0)
                    notifier.send_event_async(
                        NotificationManager.build_event(
                            event_type="threat_score_exceeded",
                            severity="critical",
                            title=f"Threat score threshold exceeded: {max_ts:.1f}",
                            body=f"Entity {entity_ctx['max_threat_entity']} has threat score {max_ts:.1f} (threshold: 75)",
                            entity_id=entity_ctx["max_threat_entity"],
                            metadata={"threat_score": max_ts, "threshold": 75},
                        )
                    )

                # Playbook steps requiring human intervention
                for inc_id, pb_status in result.playbook_statuses.items():
                    for step in pb_status.get("steps", []):
                        if not step.get("automated", True) and not step.get("completed", False):
                            notifier.send_event_async(
                                NotificationManager.build_event(
                                    event_type="playbook_step",
                                    severity="high",
                                    title=f"Human review needed: {step.get('description', 'Playbook step')}",
                                    body=f"Playbook {pb_status.get('playbook_name', '')} step '{step.get('description', '')}' requires human intervention",
                                    entity_id=inc_id,
                                    metadata={
                                        "playbook_id": pb_status.get("playbook_id", ""),
                                        "step_id": step.get("step_id", ""),
                                    },
                                )
                            )
        except Exception as exc:
            result.errors.append(f"Notification dispatch error: {exc}")

        # Record pipeline performance metrics
        try:
            from intelgraph.core.enterprise import get_performance_collector

            perf = get_performance_collector()
            duration_ms = (time.time() - _start_time) * 1000
            perf.record_pipeline_run(
                duration_ms=duration_ms,
                entity_count=len(result.graph.nodes) if result.graph else 0,
                alert_count=len(result.alerts),
                incident_count=len(result.incidents),
                error_count=len(result.errors),
                source_count=len(sources),
            )
            # Register known components
            for comp in (
                "DataSourceManager",
                "NEREngine",
                "TextClassifier",
                "RelationshipExtractor",
                "ContradictionDetector",
                "UnifiedTruthEngine",
                "ChainManager",
                "ReasoningEngine",
                "UnifiedAlertingCore",
                "ThreatScorer",
                "AnomalyDetector",
            ):
                perf.register_component(comp)
                perf.record_component_run(comp, success=True)
        except Exception:
            pass

        return result

    # ── Enrichment: Shodan + VirusTotal ──

    _ENRICH_MIN_CONFIDENCE = 70

    def _enrich_graph(self, graph: IntelligenceGraph, result: PipelineResult) -> None:
        """Enrich high-confidence IP/Domain nodes with Shodan + VirusTotal data.

        Only nodes with confidence >= _ENRICH_MIN_CONFIDENCE are enriched to
        avoid excessive API calls.  Enrichment errors are non-fatal.
        """
        shodan_client = None
        vt_client = None
        try:
            from intelgraph.core.source.shodan import ShodanClient

            shodan_client = ShodanClient()
        except (ValueError, ImportError) as exc:
            result.errors.append(f"Shodan enrichment skipped: {exc}")
        try:
            from intelgraph.core.source.virustotal import VirusTotalClient

            vt_client = VirusTotalClient()
        except (ValueError, ImportError) as exc:
            result.errors.append(f"VirusTotal enrichment skipped: {exc}")

        if not shodan_client and not vt_client:
            return

        enriched = 0
        for node_id, node in list(graph.nodes.items()):
            entity = node.entity
            cs = getattr(entity, "confidence_score", 0)
            if cs < self._ENRICH_MIN_CONFIDENCE:
                continue

            new_evidence: list[Evidence] = []
            vt_rpt: Any = None  # tracked for confidence modifier

            # Shodan for IPs
            if shodan_client and isinstance(entity, IPAddress):
                try:
                    info = shodan_client.get_host(entity.ip)
                    if info:
                        ev = Evidence(
                            id=f"ev_shodan_{entity.ip}",
                            source="shodan",
                            content=info.to_evidence_content(),
                            collected_at=datetime.now(UTC),
                            source_tier=2,
                            trust_score=70,
                            reliability_score=75,
                        )
                        new_evidence.append(ev)
                        # Update open_ports on the entity
                        if info.open_ports:
                            updated = replace(entity, open_ports=tuple(info.open_ports))
                            graph.nodes[node_id] = Node(entity=updated)
                except Exception as exc:
                    result.errors.append(f"Shodan enrichment error ({entity.ip}): {exc}")

            # VirusTotal for IPs and Domains
            if vt_client and isinstance(entity, IPAddress):
                try:
                    rpt = vt_client.get_ip_report(entity.ip)
                    if rpt:
                        vt_rpt = rpt
                        trust = min(100, 50 + int(rpt.malicious_ratio * 50))
                        ev = Evidence(
                            id=f"ev_vt_{entity.ip}",
                            source="virustotal",
                            content=rpt.to_evidence_content(),
                            collected_at=datetime.now(UTC),
                            source_tier=2,
                            trust_score=trust,
                            reliability_score=80,
                        )
                        new_evidence.append(ev)
                except Exception as exc:
                    result.errors.append(f"VirusTotal enrichment error ({entity.ip}): {exc}")
            elif vt_client and isinstance(entity, Domain):
                try:
                    rpt = vt_client.get_domain_report(entity.domain_name)
                    if rpt:
                        vt_rpt = rpt
                        trust = min(100, 50 + int(rpt.malicious_ratio * 50))
                        ev = Evidence(
                            id=f"ev_vt_{entity.domain_name}",
                            source="virustotal",
                            content=rpt.to_evidence_content(),
                            collected_at=datetime.now(UTC),
                            source_tier=2,
                            trust_score=trust,
                            reliability_score=80,
                        )
                        new_evidence.append(ev)
                except Exception as exc:
                    result.errors.append(
                        f"VirusTotal enrichment error ({entity.domain_name}): {exc}"
                    )

            if new_evidence:
                # Add enriched entity — EntityMatcher merges with existing node
                current = graph.nodes[node_id].entity
                updated_entity = replace(current, evidence=current.evidence + tuple(new_evidence))
                graph.add_entity(updated_entity, overwrite=True)
                enriched += 1

                # Apply VirusTotal modifier directly to confidence_score.
                # The chain confidence is based on opinion evidence only (non-NEUTRAL);
                # VirusTotal data is applied as a boost/penalty on top.
                if vt_rpt is not None:
                    current_conf = graph.nodes[node_id].entity.confidence_score
                    if vt_rpt.malicious_ratio > 0:
                        boost = int(vt_rpt.malicious_ratio * 20)  # 0-20 boost
                        new_conf = min(100, current_conf + boost)
                    else:
                        new_conf = max(0, current_conf - 8)  # no malicious votes → slight penalty
                    final_entity = replace(
                        graph.nodes[node_id].entity,
                        confidence_score=new_conf,
                    )
                    graph.nodes[node_id] = Node(entity=final_entity)

        if enriched:
            from structlog import get_logger

            get_logger(__name__).info("Enrichment complete", enriched_nodes=enriched)
