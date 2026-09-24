#!/usr/bin/env python3
"""
Faz 14 — Proje Durumu Final Raporu + Saglik Kontrolu
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PHASE14 = Path("/tmp/opencode/phase14")
PHASE14.mkdir(parents=True, exist_ok=True)
REPO = Path("/home/berkay/intelgraph")


def section(t):
    print(f"\n{'=' * 72}\n  {t}\n{'=' * 72}")


# ═══════════════════════════════════════════════════════════════════════════
# 1. pytest regression
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 14.1 — pytest Regression")
t0 = time.perf_counter()
proc = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header", "--tb=short"],
    cwd=str(REPO),
    capture_output=True,
    text=True,
    timeout=300,
)
t1 = time.perf_counter()
pytest_output = proc.stdout + proc.stderr
pytest_passed = pytest_failed = 0
m = re.search(r"(\d+) passed", pytest_output)
if m:
    pytest_passed = int(m.group(1))
m = re.search(r"(\d+) failed", pytest_output)
if m:
    pytest_failed = int(m.group(1))
print(f"  passed: {pytest_passed}")
print(f"  failed: {pytest_failed}")
print(f"  duration: {t1 - t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 2. Full pipeline: URLhaus + OTX + KEV
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 14.2 — 3 Kaynak Pipeline Saglik Kontrolu")

from intelgraph.core.entity.cve import CveEntity
from intelgraph.core.pipeline.chain import Pipeline

# URLHaus sample (50 rows - pipeline scale limit ~100 nodes)
urlhaus_lines = []
with open("/tmp/opencode/phase9/urlhaus_full.csv") as f:
    for i, line in enumerate(f):
        if line.startswith("#"):
            continue
        if i >= 50:
            break
        urlhaus_lines.append(line.strip())
urlhaus_text = ". ".join(urlhaus_lines)

# OTX-like synth from real URLhaus IPs/domains
with open("/tmp/opencode/phase14/otx_source.txt") as f:
    otx_text = f.read()

# KEV: 25 known + 25 unknown
kev_data = json.load(open("/tmp/opencode/phase10/kev.json"))
kev_vulns = kev_data["vulnerabilities"]
known = [v for v in kev_vulns if v.get("knownRansomwareCampaignUse") == "Known"][:25]
unknown = [v for v in kev_vulns if v.get("knownRansomwareCampaignUse") == "Unknown"][:25]
kev_lines = [
    f"{v['cveID']}: {v.get('vendorProject', '')} {v.get('product', '')} - "
    f"{v.get('shortDescription', '')} Ransomware campaign use: {v.get('knownRansomwareCampaignUse', 'Unknown')}."
    for v in known + unknown
]
kev_text = "\n".join(kev_lines)

print(f"  URLhaus: {len(urlhaus_lines)} satir, {len(urlhaus_text)} char")
print(f"  OTX:     {len(otx_text)} char")
print(f"  KEV:     {len(known) + len(unknown)} kayit, {len(kev_text)} char")

pipeline = Pipeline()
t0 = time.perf_counter()
result = pipeline.run(
    sources=[
        {"id": "urlhaus", "name": "URLhaus Live Feed", "text": urlhaus_text, "value": 80},
        {"id": "otx", "name": "AlienVault OTX Pulses", "text": otx_text, "value": 85},
        {"id": "cisa_kev", "name": "CISA KEV Catalog", "text": kev_text, "value": 90},
    ],
    thresholds={},
    query_ip="",
    query_target="",
)
t1 = time.perf_counter()
print(f"\n  Pipeline: {t1 - t0:.2f}s")
print(f"  Errors: {len(result.errors)}")
for e in result.errors[:5]:
    print(f"    - {e}")

# NER label distribution
ner_labels = Counter(e.label for e in result.extracted_entities)
print(f"\n  NER etiket dagilimi ({len(result.extracted_entities)} toplam):")
for label, cnt in ner_labels.most_common():
    print(f"    {label:15s} {cnt}")

# Graph nodes by type
node_types = Counter()
for n in result.graph.nodes.values():
    node_types[type(n.entity).__name__] += 1
print(f"\n  Graph node ({len(result.graph.nodes)} total):")
for t, cnt in node_types.most_common():
    print(f"    {t:15s} {cnt}")
print(f"  Graph edge: {len(result.graph.edges)}")
print(f"  Alert: {len(result.alerts)}")
print(f"  Incident: {len(result.incidents)}")
print(f"  Relationship: {len(result.relationships)}")
print(f"  Contradiction: {len(result.contradictions)}")

# CveEntity ransomware boost
cve_nodes = [n for n in result.graph.nodes.values() if isinstance(n.entity, CveEntity)]
known_cves = [n.entity for n in cve_nodes if n.entity.known_ransomware_use]
unknown_cves = [n.entity for n in cve_nodes if not n.entity.known_ransomware_use]
known_avg = sum(e.confidence_score for e in known_cves) / max(len(known_cves), 1)
unknown_avg = sum(e.confidence_score for e in unknown_cves) / max(len(unknown_cves), 1)
print("\n  CveEntity ransomware boost:")
print(f"    Known:   {len(known_cves)} node, avg conf={known_avg:.1f}")
print(f"    Unknown: {len(unknown_cves)} node, avg conf={unknown_avg:.1f}")

# Save
report = {
    "pipeline_duration_sec": round(t1 - t0, 2),
    "total_entities": len(result.extracted_entities),
    "ner_label_distribution": dict(ner_labels),
    "graph_node_count": len(result.graph.nodes),
    "graph_node_by_type": dict(node_types),
    "graph_edge_count": len(result.graph.edges),
    "alerts": len(result.alerts),
    "incidents": len(result.incidents),
    "relationships": len(result.relationships),
    "contradictions": len(result.contradictions),
    "errors": len(result.errors),
    "cve_known_nodes": len(known_cves),
    "cve_unknown_nodes": len(unknown_cves),
    "cve_known_avg_confidence": round(known_avg, 1),
    "cve_unknown_avg_confidence": round(unknown_avg, 1),
}
with open(PHASE14 / "phase14_health_check.json", "w") as f:
    json.dump(
        {
            "pytest": {
                "passed": pytest_passed,
                "failed": pytest_failed,
                "duration_sec": round(t1 - t0, 1),
            },
            "pipeline": report,
        },
        f,
        indent=2,
        ensure_ascii=False,
    )
print(f"\n  Rapor: {PHASE14}/phase14_health_check.json")

section("FAZ 14 TAMAM")
print(f"  pytest: {pytest_passed}/{pytest_passed + pytest_failed}")
print(
    f"  Pipeline: {report['pipeline_duration_sec']}s, {report['graph_node_count']} node, {report['graph_edge_count']} edge"
)
print(
    f"  CveEntity boost: Known avg={report['cve_known_avg_confidence']}, Unknown avg={report['cve_unknown_avg_confidence']}"
)
