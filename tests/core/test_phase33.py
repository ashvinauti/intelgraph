"""Phase 33 tests: Automated Reporting System."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from intelgraph.core.reporting.models import Report, ReportFormat, ReportType
from intelgraph.core.reporting.reporters import generate_report
from intelgraph.core.reporting.scheduler import ReportScheduler

# ---------------------------------------------------------------------------
# Test data fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def pipeline_data():
    return {
        "graph_node_count": 15,
        "graph_edge_count": 23,
        "contradiction_count": 2,
        "alert_count": 3,
        "incident_count": 1,
        "entity_count": 12,
        "path_count": 5,
        "source_count": 4,
        "chain_stats": {"total_chain_count": 8},
        "graph_nodes_summary": [
            {
                "node_id": "n1",
                "entity_type": "IPAddress",
                "entity_identifier": "107.172.135.60",
                "confidence": 85,
                "evidence_count": 4,
                "threat_score": 82.5,
                "first_seen": "2025-01-15T10:00:00",
                "last_seen": "2025-01-22T10:00:00",
            },
            {
                "node_id": "n2",
                "entity_type": "Domain",
                "entity_identifier": "evil.example.com",
                "confidence": 72,
                "evidence_count": 3,
                "threat_score": 65.0,
                "first_seen": "2025-01-10T10:00:00",
                "last_seen": "2025-01-22T10:00:00",
            },
            {
                "node_id": "n3",
                "entity_type": "CveEntity",
                "entity_identifier": "CVE-2024-1234",
                "confidence": 95,
                "evidence_count": 5,
                "threat_score": 91.0,
                "first_seen": "2025-01-05T10:00:00",
                "last_seen": "2025-01-22T10:00:00",
            },
            {
                "node_id": "n4",
                "entity_type": "IPAddress",
                "entity_identifier": "8.8.8.8",
                "confidence": 10,
                "evidence_count": 0,
                "threat_score": 0,
                "first_seen": "2025-01-01T10:00:00",
                "last_seen": "2025-01-02T10:00:00",
            },
        ],
        "graph_edges_summary": [
            {"source": "n1", "target": "n2", "type": "resolves"},
            {"source": "n1", "target": "n3", "type": "related"},
        ],
        "alerts": [
            {
                "alert_id": "alert_001",
                "severity": "critical",
                "message": "C2 IP detected",
                "category": "c2_detection",
            },
            {
                "alert_id": "alert_002",
                "severity": "high",
                "message": "Ransomware CVE",
                "category": "ransomware_cve",
            },
            {
                "alert_id": "alert_003",
                "severity": "medium",
                "message": "Suspicious domain",
                "category": "domain_alert",
            },
        ],
        "incidents": [
            {
                "alert_id": "inc_001",
                "severity": "critical",
                "message": "C2 incident",
                "confirmed": True,
            },
        ],
        "truth_entries": [
            {"source": "urlhaus"},
            {"source": "urlhaus"},
            {"source": "otx"},
            {"source": "kev"},
        ],
        "errors": [],
        "playbook_statuses": {
            "inc_001": {
                "playbook_name": "C2 IP Response",
                "matched_at": "2025-01-22T10:00:00",
                "steps": [
                    {
                        "step_id": "s1",
                        "action_type": "block",
                        "description": "Block IP on firewall",
                        "automated": True,
                        "completed": True,
                    },
                    {
                        "step_id": "s2",
                        "action_type": "notify",
                        "description": "Notify SOC team",
                        "automated": False,
                        "completed": False,
                    },
                ],
            },
        },
    }


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_report_creation(self):
        r = Report(report_id="rpt_1", report_type="threat_summary", html_content="<html></html>")
        assert r.report_id == "rpt_1"
        assert r.format == "html"
        d = r.to_dict()
        assert "html_content" not in d  # stripped from dict
        assert d["report_type"] == "threat_summary"

    def test_report_roundtrip(self):
        r = Report(
            report_id="rpt_2",
            report_type="entity_detail",
            html_content="<p>test</p>",
            time_range_start="2025-01-01",
            time_range_end="2025-01-22",
        )
        d = r.to_dict()
        r2 = Report.from_dict(d)
        assert r2.report_id == "rpt_2"
        assert r2.html_content == ""

    def test_report_type_enum(self):
        assert ReportType.THREAT_SUMMARY.value == "threat_summary"
        assert ReportType.ENTITY_DETAIL.value == "entity_detail"
        assert ReportType.EXECUTIVE_SUMMARY.value == "executive_summary"

    def test_report_format_enum(self):
        assert ReportFormat.HTML.value == "html"


# ---------------------------------------------------------------------------
# Reporter tests
# ---------------------------------------------------------------------------


class TestReportGenerators:
    def test_threat_summary_html(self, pipeline_data):
        report = generate_report("threat_summary", pipeline_data)
        html = report.html_content
        assert "<html" in html
        assert "Threat Summary Report" in html
        assert "107.172.135.60" in html  # top threat identifier
        assert "82.5" in html  # threat score
        assert "C2 IP detected" in html  # alert message
        assert "C2 incident" in html  # incident message
        assert "urlhaus" in html  # source distribution
        assert "IPAddress" in html  # entity type breakdown
        assert report.report_type == "threat_summary"

    def test_threat_summary_top_threats_sorted(self, pipeline_data):
        report = generate_report("threat_summary", pipeline_data)
        html = report.html_content
        # Top threat should be CVE-2024-1234 (91.0)
        # Check that it appears before the IP
        cve_pos = html.index("CVE-2024-1234")
        ip_pos = html.index("107.172.135.60")
        assert cve_pos < ip_pos  # higher score first

    def test_executive_summary_html(self, pipeline_data):
        report = generate_report("executive_summary", pipeline_data)
        html = report.html_content
        assert "<html" in html
        assert "Executive Summary Report" in html
        assert "3" in html  # alerts
        assert "1" in html  # incidents
        assert "CVE-2024-1234" in html
        assert "Recommendations" in html

    def test_executive_summary_findings(self, pipeline_data):
        report = generate_report("executive_summary", pipeline_data)
        html = report.html_content
        assert "Immediately investigate" in html  # recommendation for 82.5 threat score
        assert "high-risk CVE" in html  # finding about CVEs

    def test_entity_detail_html(self, pipeline_data):
        """Entity detail report from extracted entity data."""
        detail_data = {
            "entity_id": "n1",
            "entity_type": "IPAddress",
            "entity_identifier": "107.172.135.60",
            "confidence": 85,
            "threat_score": 82.5,
            "evidence_list": [
                {
                    "source": "urlhaus",
                    "content": "malicious payload",
                    "collected_at": "2025-01-22T10:00:00",
                    "trust_score": 90,
                    "reliability_score": 85,
                },
            ],
            "relationships": [
                {
                    "source_id": "n1",
                    "target_id": "n2",
                    "type": "resolves",
                    "first_seen": "2025-01-15T10:00:00",
                    "last_seen": "2025-01-22T10:00:00",
                },
            ],
            "chain": {
                "verification_status": "confirmed",
                "overall_confidence": 0.92,
                "steps": [{"source": "urlhaus", "support_type": "SUPPORTS", "confidence": 0.85}],
            },
            "playbook_status": {
                "playbook_name": "C2 IP Response",
                "steps": [
                    {
                        "description": "Block IP",
                        "action_type": "block",
                        "automated": True,
                        "completed": True,
                    }
                ],
            },
        }
        report = generate_report("entity_detail", detail_data)
        html = report.html_content
        assert "<html" in html
        assert "Entity Detail Report" in html
        assert "107.172.135.60" in html
        assert "urlhaus" in html  # evidence source
        assert "resolves" in html  # relationship type
        assert "confirmed" in html  # chain verification
        assert "C2 IP Response" in html  # playbook name


# ---------------------------------------------------------------------------
# Scheduler tests
# ---------------------------------------------------------------------------


class TestScheduler:
    def test_init(self):
        s = ReportScheduler(state_path="/tmp/opencode/test_rpt_sched.json")
        assert s.list_reports() == []
        s.stop()

    def test_save_and_list_report(self, pipeline_data):
        s = ReportScheduler(state_path="/tmp/opencode/test_rpt_savelist.json")
        report = generate_report("threat_summary", pipeline_data)
        s.save_report(report)
        reports = s.list_reports()
        assert len(reports) == 1
        assert reports[0]["report_id"] == report.report_id
        assert os.path.exists(reports[0]["file_path"])
        # Verify HTML content was written
        with open(reports[0]["file_path"]) as f:
            content = f.read()
        assert "Threat Summary Report" in content
        s.stop()

    def test_get_report_meta(self, pipeline_data):
        s = ReportScheduler(state_path="/tmp/opencode/test_rpt_get.json")
        report = generate_report("executive_summary", pipeline_data)
        s.save_report(report)
        meta = s.get_report(report.report_id)
        assert meta is not None
        assert meta["report_type"] == "executive_summary"
        s.stop()

    def test_get_report_html(self, pipeline_data):
        s = ReportScheduler(state_path="/tmp/opencode/test_rpt_html.json")
        report = generate_report("threat_summary", pipeline_data)
        s.save_report(report)
        html = s.get_report_html(report.report_id)
        assert html is not None
        assert "Top Threats" in html
        s.stop()

    def test_report_not_found(self):
        s = ReportScheduler(state_path="/tmp/opencode/test_rpt_nf.json")
        assert s.get_report("nonexistent") is None
        assert s.get_report_html("nonexistent") is None
        s.stop()

    def test_scheduler_persistence(self, pipeline_data):
        path = "/tmp/opencode/test_rpt_persist.json"
        if os.path.exists(path):
            os.remove(path)
        s1 = ReportScheduler(state_path=path)
        r1 = generate_report("threat_summary", pipeline_data)
        s1.save_report(r1)
        r2 = generate_report("executive_summary", pipeline_data)
        s1.save_report(r2)
        s1.stop()
        del s1

        s2 = ReportScheduler(state_path=path)
        reports = s2.list_reports()
        assert len(reports) == 2
        assert any(r["report_type"] == "threat_summary" for r in reports)
        s2.stop()
        os.remove(path)

    def test_scheduled_generation(self, pipeline_data):
        """Verify scheduler generates reports at interval using data provider."""
        s = ReportScheduler(state_path="/tmp/opencode/test_rpt_sched_gen.json")
        called = {"count": 0}

        def provider():
            called["count"] += 1
            return pipeline_data

        s.set_data_provider(provider)
        s.start(interval_seconds=0.5)
        time.sleep(1.2)
        s.stop()
        # Should have generated at least 1 report (maybe 2 if timing allows)
        reports = s.list_reports()
        assert len(reports) >= 1
        assert called["count"] >= 1

    def test_data_provider_none(self):
        """Scheduler should handle None provider gracefully."""
        s = ReportScheduler(state_path="/tmp/opencode/test_rpt_no_provider.json")
        s.set_data_provider(lambda: None)
        s.start(interval_seconds=0.3)
        time.sleep(0.4)
        s.stop()
        assert s.list_reports() == []


# ---------------------------------------------------------------------------
# Template integrity tests
# ---------------------------------------------------------------------------


class TestTemplates:
    def test_base_template_renders(self):
        import os

        from jinja2 import Environment, FileSystemLoader

        tmpl_dir = os.path.join(
            os.path.dirname(__file__), "../../intelgraph/core/reporting/templates"
        )
        env = Environment(loader=FileSystemLoader(tmpl_dir))
        tmpl = env.get_template("base.html")
        html = tmpl.render(title="Test", generated_at="2025-01-22T10:00:00")
        assert "Test" in html
        assert "IntelGraph Report" in html

    def test_threat_summary_empty_alerts(self):
        """Template should handle missing data gracefully."""
        data = {
            "graph_nodes_summary": [],
            "graph_edges_summary": [],
            "alerts": [],
            "incidents": [],
            "contradiction_count": 0,
            "chain_stats": {},
            "truth_entries": [],
        }
        report = generate_report("threat_summary", data)
        html = report.html_content
        assert "Top Threats" in html
        assert "No alerts" in html


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def teardown_module():
    for f in os.listdir("/tmp/opencode/"):
        if f.startswith("test_rpt") and f.endswith(".json"):
            try:
                os.remove(f"/tmp/opencode/{f}")
            except OSError:
                pass
    # Clean up report files
    rpt_dir = "/tmp/intelgraph/reports"
    if os.path.exists(rpt_dir):
        for f in os.listdir(rpt_dir):
            if f.startswith("rpt_"):
                try:
                    os.remove(os.path.join(rpt_dir, f))
                except OSError:
                    pass
