"""Phase 31 tests: Threat Scoring model integration."""

import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from intelgraph.core.entity.cve import CveEntity
from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.evidence.evidence import Evidence
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.relationship.base import Relationship
from intelgraph.core.scoring.threat_score import (
    ThreatScorer,
    _clear_score_cache,
    compute_threat_scores,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ip(ip_str, confidence=85.0, evidence=None, first_seen_delta=-2, last_seen_delta=0):
    """Create an IPAddress entity with optional evidence tuple passed at construction."""
    e = IPAddress(
        id=f"ip_{ip_str.replace('.', '_')}",
        ip=ip_str,
        confidence_score=confidence,
        evidence=evidence or (),
        first_seen=datetime.now(UTC) + timedelta(hours=first_seen_delta),
        last_seen=datetime.now(UTC) + timedelta(hours=last_seen_delta),
    )
    return e


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


def _ev(source="urlhaus", tier=1):
    return Evidence(
        id=f"ev_{source}",
        source=source,
        content="malicious",
        collected_at=datetime.now(UTC),
        source_tier=tier,
        trust_score=90,
        reliability_score=85,
    )


# ---------------------------------------------------------------------------
# Test: ThreatScorer scoring
# ---------------------------------------------------------------------------


class TestThreatScorer:
    def test_score_zero_for_none(self):
        assert ThreatScorer().score(None, None) == 0.0

    def test_high_confidence_ip_scores_above_low(self):
        g = IntelligenceGraph()
        ip_high = _make_ip("1.1.1.1", confidence=90.0)
        ip_low = _make_ip("2.2.2.2", confidence=10.0)
        g.add_entity(ip_high)
        g.add_entity(ip_low)
        s = ThreatScorer()
        assert s.score(g.nodes[ip_high.id], g) > s.score(g.nodes[ip_low.id], g)

    def test_relationship_increases_score(self):
        g = IntelligenceGraph()
        e1 = _make_ip("1.1.1.1", confidence=50.0)
        e2 = _make_domain("evil.com", confidence=50.0)
        g.add_entity(e1)
        g.add_entity(e2)
        g.add_relationship(Relationship(source_id=e1.id, target_id=e2.id, type="resolves"))
        s = ThreatScorer()
        score_with_rel = s.score(g.nodes[e1.id], g)

        g2 = IntelligenceGraph()
        e1_only = _make_ip("1.1.1.1", confidence=50.0)
        g2.add_entity(e1_only)
        score_without_rel = s.score(g2.nodes[e1_only.id], g2)
        assert score_with_rel > score_without_rel

    def test_more_evidence_increases_score(self):
        g = IntelligenceGraph()
        e = _make_ip(
            "1.1.1.1", confidence=50.0, evidence=(_ev("urlhaus"), _ev("otx"), _ev("abusech"))
        )
        g.add_entity(e)
        s = ThreatScorer()
        score_multi = s.score(g.nodes[e.id], g)

        g2 = IntelligenceGraph()
        e2 = _make_ip("1.1.1.1", confidence=50.0, evidence=(_ev("urlhaus"),))
        g2.add_entity(e2)
        score_single = s.score(g2.nodes[e2.id], g2)
        assert score_multi > score_single

    def test_recent_activity_scores_higher(self):
        g = IntelligenceGraph()
        e_recent = _make_ip("1.1.1.1", confidence=50.0, first_seen_delta=-1, last_seen_delta=0)
        g.add_entity(e_recent)

        g2 = IntelligenceGraph()
        e_old = _make_ip(
            "2.2.2.2", confidence=50.0, first_seen_delta=-24 * 60, last_seen_delta=-24 * 60 + 1
        )
        g2.add_entity(e_old)

        s = ThreatScorer()
        assert s.score(g.nodes[e_recent.id], g) > s.score(g2.nodes[e_old.id], g2)

    def test_malicious_signals_ransomware(self):
        g = IntelligenceGraph()
        e = _make_cve("CVE-2024-0001", ransomware=True, confidence=95.0)
        g.add_entity(e)
        s = ThreatScorer()
        score_rw = s.score(g.nodes[e.id], g)

        g2 = IntelligenceGraph()
        e2 = _make_cve("CVE-2024-0002", ransomware=False, confidence=95.0)
        g2.add_entity(e2)
        score_no_rw = s.score(g2.nodes[e2.id], g2)
        assert score_rw > score_no_rw

    def test_score_all_returns_sorted(self):
        g = IntelligenceGraph()
        g.add_entity(_make_ip("1.1.1.1", confidence=90.0))
        g.add_entity(_make_ip("2.2.2.2", confidence=10.0))
        s = ThreatScorer()
        results = s.score_all(g)
        assert len(results) == 2
        assert results[0]["threat_score"] >= results[1]["threat_score"]

    def test_top_k_returns_k(self):
        g = IntelligenceGraph()
        for i in range(5):
            g.add_entity(_make_ip(f"1.1.1.{i}", confidence=50.0 + i * 10))
        s = ThreatScorer()
        top3 = s.top_k(g, k=3)
        assert len(top3) == 3
        assert top3[0]["threat_score"] >= top3[-1]["threat_score"]

    def test_compute_threat_scores_dict(self):
        g = IntelligenceGraph()
        ip_high = _make_ip("1.1.1.1", confidence=90.0)
        ip_low = _make_ip("2.2.2.2", confidence=10.0)
        g.add_entity(ip_high)
        g.add_entity(ip_low)
        scores = compute_threat_scores(g)
        assert ip_high.id in scores
        assert isinstance(scores[ip_high.id], float)
        assert scores[ip_high.id] > scores[ip_low.id]

    def test_cache(self):
        _clear_score_cache()
        g = IntelligenceGraph()
        g.add_entity(_make_ip("1.1.1.1", confidence=50.0))
        s1 = compute_threat_scores(g)
        s2 = compute_threat_scores(g)
        assert s1 == s2


# ---------------------------------------------------------------------------
# Test: nodes_summary includes threat_score
# ---------------------------------------------------------------------------


class TestNodesSummary:
    def test_nodes_summary_has_threat_score(self):
        g = IntelligenceGraph()
        g.add_entity(_make_ip("1.1.1.1", confidence=50.0))
        summary = g.nodes_summary
        assert "threat_score" in summary[0]
        assert isinstance(summary[0]["threat_score"], float)
        assert summary[0]["threat_score"] > 0

    def test_low_risk_low_score(self):
        g = IntelligenceGraph()
        g.add_entity(
            _make_ip(
                "1.1.1.1", confidence=5.0, first_seen_delta=-24 * 60, last_seen_delta=-24 * 60 + 1
            )
        )
        assert g.nodes_summary[0]["threat_score"] < 25.0

    def test_high_confidence_ransomware_scores_high(self):
        _clear_score_cache()
        g = IntelligenceGraph()
        e = _make_cve("CVE-2024-0001", ransomware=True, confidence=95.0)
        g.add_entity(e)
        assert g.nodes_summary[0]["threat_score"] > 30.0

    def test_cache_per_graph_instance(self):
        _clear_score_cache()
        g1 = IntelligenceGraph()
        g1.add_entity(_make_ip("1.1.1.1", confidence=90.0))
        g2 = IntelligenceGraph()
        g2.add_entity(_make_ip("2.2.2.2", confidence=10.0))
        assert g1.nodes_summary[0]["threat_score"] != g2.nodes_summary[0]["threat_score"]


# ---------------------------------------------------------------------------
# Test: max_threat_score threshold in config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_max_threat_threshold_exists(self):
        from intelgraph.core.config import DEFAULT_CONFIG

        t = DEFAULT_CONFIG["alerting"]["thresholds"]["max_threat_score"]
        assert t["enabled"] is True
        assert t["max"] == 75.0
        assert t["severity"] == "critical"
