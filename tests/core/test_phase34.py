"""Phase 34 tests: Anomaly Detection Enhancement."""

import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


from intelgraph.core.entity.cve import CveEntity
from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.evidence.evidence import Evidence
from intelgraph.core.graph.anomaly import (
    _THREAT_SCORE_CACHE,
    AnomalyDetector,
    AnomalyResult,
)
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.relationship.base import Relationship

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ip(ip_str, confidence=50.0, evidence=None, first_seen_delta=-2, last_seen_delta=0):
    return IPAddress(
        id=f"ip_{ip_str.replace('.', '_')}",
        ip=ip_str,
        confidence_score=confidence,
        evidence=evidence or (),
        first_seen=datetime.now(UTC) + timedelta(hours=first_seen_delta),
        last_seen=datetime.now(UTC) + timedelta(hours=last_seen_delta),
    )


def _make_domain(domain, confidence=45.0):
    return Domain(
        id=f"dom_{domain.replace('.', '_')}",
        domain_name=domain,
        confidence_score=confidence,
        evidence=(),
        first_seen=datetime.now(UTC) - timedelta(days=5),
        last_seen=datetime.now(UTC),
    )


def _make_cve(cve_id, confidence=95.0, ransomware=False):
    return CveEntity(
        id=f"cve_{cve_id.replace('-', '_')}",
        cve_id=cve_id,
        confidence_score=confidence,
        known_ransomware_use=ransomware,
        evidence=(),
        first_seen=datetime.now(UTC) - timedelta(days=30),
        last_seen=datetime.now(UTC),
    )


def _ev(source="urlhaus", tier=1, collected_at=None):
    return Evidence(
        id=f"ev_{source}",
        source=source,
        content="malicious",
        collected_at=collected_at or datetime.now(UTC),
        source_tier=tier,
        trust_score=90,
        reliability_score=85,
    )


# ---------------------------------------------------------------------------
# AnomalyResult model tests
# ---------------------------------------------------------------------------


class TestAnomalyResult:
    def test_to_dict(self):
        r = AnomalyResult(
            node_id="n1",
            anomaly_type="threat_score",
            anomaly_score=82.5,
            explanation="High threat score",
            entity_type="IPAddress",
            entity_identifier="1.2.3.4",
        )
        d = r.to_dict()
        assert d["node_id"] == "n1"
        assert d["anomaly_type"] == "threat_score"
        assert d["anomaly_score"] == 82.5
        assert d["entity_identifier"] == "1.2.3.4"


# ---------------------------------------------------------------------------
# Threat score anomaly tests
# ---------------------------------------------------------------------------


class TestThreatScoreAnomaly:
    def test_no_anomaly_when_similar_scores(self):
        g = IntelligenceGraph()
        for i in range(5):
            g.add_entity(_make_ip(f"1.1.1.{i}", confidence=50.0))
        for nid in g.nodes:
            _THREAT_SCORE_CACHE[nid] = 30.0  # all same score
        d = AnomalyDetector(g)
        results = d.threat_score_anomaly()
        assert len(results) == 0
        _THREAT_SCORE_CACHE.clear()

    def test_detects_outlier(self):
        g = IntelligenceGraph()
        for i in range(4):
            g.add_entity(_make_ip(f"1.1.1.{i}", confidence=50.0))
        g.add_entity(_make_ip("9.9.9.9", confidence=95.0))
        outlier_id = None
        for nid, node in g.nodes.items():
            e = node.entity
            if getattr(e, "ip", "") == "9.9.9.9":
                outlier_id = nid
                _THREAT_SCORE_CACHE[nid] = 95.0
            else:
                _THREAT_SCORE_CACHE[nid] = 30.0
        d = AnomalyDetector(g)
        results = d.threat_score_anomaly()
        assert len(results) >= 1
        assert any(r.node_id == outlier_id for r in results)
        _THREAT_SCORE_CACHE.clear()

    def test_insufficient_data(self):
        g = IntelligenceGraph()
        g.add_entity(_make_ip("1.1.1.1", confidence=50.0))
        _THREAT_SCORE_CACHE["ip_1.1.1.1"] = 80.0
        d = AnomalyDetector(g)
        results = d.threat_score_anomaly()
        assert len(results) == 0  # need at least 2 same-type entities
        _THREAT_SCORE_CACHE.clear()


# ---------------------------------------------------------------------------
# Temporal spike anomaly tests
# ---------------------------------------------------------------------------


class TestTemporalSpikeAnomaly:
    def test_no_spike(self):
        g = IntelligenceGraph()
        recent = datetime.now(UTC)
        old = recent - timedelta(days=20)
        evs = tuple(_ev("urlhaus", collected_at=old) for _ in range(10))
        g.add_entity(_make_ip("1.1.1.1", evidence=evs))
        d = AnomalyDetector(g)
        results = d.temporal_spike_anomaly()
        assert len(results) == 0  # no recent activity

    def test_spike_detected(self):
        g = IntelligenceGraph()
        now = datetime.now(UTC)
        recent = now - timedelta(hours=2)
        old = now - timedelta(days=20)
        # 15 evidence in last 24h, 20 in last 30d
        evs = tuple(_ev("urlhaus", collected_at=recent) for _ in range(15))
        evs += tuple(_ev("otx", collected_at=old) for _ in range(5))
        g.add_entity(_make_ip("1.1.1.1", evidence=evs))
        d = AnomalyDetector(g)
        results = d.temporal_spike_anomaly()
        assert len(results) >= 1
        assert results[0].anomaly_type == "temporal_spike"

    def test_insufficient_data(self):
        g = IntelligenceGraph()
        g.add_entity(_make_ip("1.1.1.1"))
        d = AnomalyDetector(g)
        results = d.temporal_spike_anomaly()
        assert len(results) == 0  # no evidence


# ---------------------------------------------------------------------------
# Relationship outlier anomaly tests
# ---------------------------------------------------------------------------


class TestRelationshipOutlierAnomaly:
    def test_no_outlier(self):
        g = IntelligenceGraph()
        ips = [_make_ip(f"1.1.1.{i}") for i in range(3)]
        dom = _make_domain("test.com")
        for ip_ent in ips:
            g.add_entity(ip_ent)
        g.add_entity(dom)
        for ip_ent in ips:
            g.add_relationship(Relationship(source_id=ip_ent.id, target_id=dom.id, type="resolves"))
        d = AnomalyDetector(g)
        results = d.relationship_outlier_anomaly()
        assert len(results) == 0  # all IPs have 1 edge

    def test_outlier_detected(self):
        g = IntelligenceGraph()
        ips = [_make_ip(f"1.1.1.{i}") for i in range(4)]
        outlier = _make_ip("9.9.9.9")
        doms = [_make_domain(f"evil{i}.com") for i in range(10)]
        for ip_ent in ips:
            g.add_entity(ip_ent)
        g.add_entity(outlier)
        for dom_ent in doms:
            g.add_entity(dom_ent)
            g.add_relationship(
                Relationship(source_id=outlier.id, target_id=dom_ent.id, type="resolves")
            )
        # Normal IPs get 1 edge each
        g.add_entity(_make_domain("normal.com"))
        for ip_ent in ips:
            g.add_relationship(
                Relationship(source_id=ip_ent.id, target_id="dom_normal.com", type="resolves")
            )
        d = AnomalyDetector(g)
        results = d.relationship_outlier_anomaly()
        assert len(results) >= 1
        assert any(r.node_id == outlier.id for r in results)
        ip_results = [r for r in results if r.node_id == outlier.id]
        assert len(ip_results) > 0


# ---------------------------------------------------------------------------
# detect_all tests
# ---------------------------------------------------------------------------


class TestDetectAll:
    def test_detect_all_combines_anomalies(self):
        g = IntelligenceGraph()
        datetime.now(UTC)
        # Create a high-threat entity with lots of edges
        outlier = _make_ip("9.9.9.9", confidence=95.0)
        g.add_entity(outlier)
        _THREAT_SCORE_CACHE[outlier.id] = 95.0
        dom = _make_domain("evil.com")
        g.add_entity(dom)
        g.add_relationship(Relationship(source_id=outlier.id, target_id=dom.id, type="resolves"))
        # Add some normal IPs
        for i in range(3):
            g.add_entity(_make_ip(f"1.1.1.{i}", confidence=30.0))
            _THREAT_SCORE_CACHE[f"ip_1.1.1.{i}"] = 20.0
        d = AnomalyDetector(g)
        results = d.detect_all()
        assert len(results) >= 1
        # Should include multi_factor for all entities
        types = {r.anomaly_type for r in results}
        assert "multi_factor" in types
        _THREAT_SCORE_CACHE.clear()

    def test_detect_all_sorted(self):
        g = IntelligenceGraph()
        now = datetime.now(UTC)
        evs = tuple(_ev("urlhaus", collected_at=now - timedelta(hours=1)) for _ in range(20))
        high = _make_ip("9.9.9.9", confidence=95.0, evidence=evs)
        g.add_entity(high)
        _THREAT_SCORE_CACHE[high.id] = 95.0
        low = _make_ip("1.1.1.1", confidence=10.0)
        g.add_entity(low)
        _THREAT_SCORE_CACHE[low.id] = 5.0
        d = AnomalyDetector(g)
        results = d.detect_all()
        assert len(results) >= 2
        # First result should have highest score
        scores = [r.anomaly_score for r in results]
        assert scores == sorted(scores, reverse=True)
        _THREAT_SCORE_CACHE.clear()

    def test_detect_all_empty_graph(self):
        g = IntelligenceGraph()
        d = AnomalyDetector(g)
        results = d.detect_all()
        assert results == []


# ---------------------------------------------------------------------------
# Pipeline integration test (via AnomalyDetector usability)
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    def test_anomaly_cache_set_by_pipeline(self):
        """Verify _THREAT_SCORE_CACHE is populated by the pipeline Phase 3.9."""

        from intelgraph.core.pipeline.chain import Pipeline

        _THREAT_SCORE_CACHE.clear()
        pipeline = Pipeline()
        sources = [
            {
                "text": "Malicious IP 107.172.135.60 communicating with C2 server and ransomware CVE-2024-1234"
            }
        ]
        thresholds = {
            "max_threat_score": {"enabled": True, "max": 75.0, "severity": "critical"},
        }
        result = pipeline.run(sources, thresholds=thresholds)
        assert result is not None
        # _THREAT_SCORE_CACHE should have entries
        assert len(_THREAT_SCORE_CACHE) > 0
        # anomaly_results should exist in result
        assert hasattr(result, "anomaly_results")
        assert isinstance(result.anomaly_results, list)
        pipeline.cleanup()
        _THREAT_SCORE_CACHE.clear()


# ---------------------------------------------------------------------------
# Test data provider for scheduler
# ---------------------------------------------------------------------------


def teardown_module():
    _THREAT_SCORE_CACHE.clear()
    for f in os.listdir("/tmp/opencode/"):
        if f.startswith("test_anom") and f.endswith(".json"):
            try:
                os.remove(f"/tmp/opencode/{f}")
            except OSError:
                pass
