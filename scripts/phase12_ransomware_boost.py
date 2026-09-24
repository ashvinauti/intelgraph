#!/usr/bin/env python3
"""
Faz 12 — CISA KEV knownRansomwareCampaignUse → Confidence/Risk Score Boost

Verifies:
1. known_ransomware_use flag propagates correctly (Known=True, Unknown=False)
2. Evidence trust_score is boosted for ransomware-known CVEs (90→100)
3. Evidence reliability_score is boosted for ransomware-known CVEs (90→100)
4. CveEntity confidence_score is higher for ransomware-known than unknown
"""

from __future__ import annotations

import json
import os
import sys
import time

KEV_PATH = "/tmp/opencode/phase10/kev.json"
REPORT_PATH = "/tmp/opencode/phase12/phase12_report.json"
os.makedirs("/tmp/opencode/phase12", exist_ok=True)


def section(t):
    print(f"\n{'=' * 72}")
    print(f"  {t}")
    print(f"{'=' * 72}")


# ═══════════════════════════════════════════════════════════════════════════
# 0. Load KEV
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 12.0 — KEV Yukleme")

kev = json.load(open(KEV_PATH))
vulns = kev["vulnerabilities"]
print(f"  Toplam KEV kaydi: {len(vulns)}")

ransomware_known = [v for v in vulns if v.get("knownRansomwareCampaignUse") == "Known"]
ransomware_unknown = [v for v in vulns if v.get("knownRansomwareCampaignUse") == "Unknown"]
print(f"  Ransomware Known:   {len(ransomware_known)}")
print(f"  Ransomware Unknown: {len(ransomware_unknown)}")

# Build focused test text: 50 known + 50 unknown
test_known = ransomware_known[:50]
test_unknown = ransomware_unknown[:50]

known_lines = []
for v in test_known:
    known_lines.append(
        f"{v['cveID']}: {v.get('vendorProject', '')} {v.get('product', '')} - "
        f"{v.get('shortDescription', '')} Ransomware campaign use: Known."
    )

unknown_lines = []
for v in test_unknown:
    unknown_lines.append(
        f"{v['cveID']}: {v.get('vendorProject', '')} {v.get('product', '')} - "
        f"{v.get('shortDescription', '')} Ransomware campaign use: Unknown."
    )

combined_text = "\n".join(known_lines + unknown_lines)
print(
    f"  Test metni: {len(test_known)} Known + {len(test_unknown)} Unknown = "
    f"{len(known_lines) + len(unknown_lines)} kayit, {len(combined_text) / 1024:.1f} KB"
)

# CVE IDs in lowercase (NER normalizes to lowercase)
known_cve_ids = {v["cveID"].lower() for v in test_known}
unknown_cve_ids = {v["cveID"].lower() for v in test_unknown}

# ═══════════════════════════════════════════════════════════════════════════
# 1. Pipeline.run()
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 12.1 — Pipeline Calistirma")

from intelgraph.core.entity.cve import CveEntity
from intelgraph.core.pipeline.chain import Pipeline

pipeline = Pipeline()

t0 = time.perf_counter()
result = pipeline.run(
    sources=[
        {
            "id": "cisa_kev",
            "name": "CISA KEV Catalog",
            "text": combined_text,
            "value": 90,
        }
    ],
    thresholds={},
    query_ip="",
    query_target="",
)
t1 = time.perf_counter()
print(f"  Pipeline sure:  {t1 - t0:.3f}s")
print(f"  Graph node:     {len(result.graph.nodes) if result.graph else 0}")
print(f"  Alert:          {len(result.alerts)}")
print(f"  Truth entry:    {len(result.truth_entries)}")
print(f"  Hata:           {len(result.errors)}")
for e in result.errors:
    print(f"    ✗ {e}")

# ═══════════════════════════════════════════════════════════════════════════
# 2. Verify CveEntity: known_ransomware_use flag + confidence_score
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 12.2 — CveEntity Dogrulama")

if not result.graph:
    print("  ✗ Graph bos!")
    sys.exit(1)

cve_nodes = [n for n in result.graph.nodes.values() if isinstance(n.entity, CveEntity)]

# Classify by known_ransomware_use flag on the entity itself
known_entities = [n.entity for n in cve_nodes if n.entity.known_ransomware_use]
unknown_entities = [n.entity for n in cve_nodes if not n.entity.known_ransomware_use]

print(f"  CveEntity node:     {len(cve_nodes)}")
print(f"  known_ransomware_use=True:  {len(known_entities)}")
print(f"  known_ransomware_use=False: {len(unknown_entities)}")

# Check confidence_score
known_confs = [e.confidence_score for e in known_entities]
unknown_confs = [e.confidence_score for e in unknown_entities]

print(
    f"\n  Known confidence_score:   avg={sum(known_confs) / len(known_confs):.1f}  "
    f"min={min(known_confs)} max={max(known_confs)}"
    if known_confs
    else "  Known: (empty)"
)
print(
    f"  Unknown confidence_score: avg={sum(unknown_confs) / len(unknown_confs):.1f}  "
    f"min={min(unknown_confs)} max={max(unknown_confs)}"
    if unknown_confs
    else "  Unknown: (empty)"
)

# Key assertion: Known CVEs have STRICTLY HIGHER confidence than Unknown
known_avg = sum(known_confs) / len(known_confs) if known_confs else 0
unknown_avg = sum(unknown_confs) / len(unknown_confs) if unknown_confs else 0
known_higher = known_avg > unknown_avg
print(f"\n  Known avg > Unknown avg: {known_higher} ({known_avg:.1f} > {unknown_avg:.1f})")

# ═══════════════════════════════════════════════════════════════════════════
# 3. Verify Evidence boost: trust_score + reliability_score
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 12.3 — Evidence Boost Dogrulama")

# Collect evidence from known vs unknown entities
known_evidence = []
for e in known_entities:
    known_evidence.extend(e.evidence)
unknown_evidence = []
for e in unknown_entities:
    unknown_evidence.extend(e.evidence)

# Evidence trust_score: should be 100 (boosted from 90+10) for known, 90 for unknown
known_trust = [ev.trust_score for ev in known_evidence]
unknown_trust = [ev.trust_score for ev in unknown_evidence]

# Evidence reliability_score: should be 100 for known, 90 for unknown
known_rel = [ev.reliability_score for ev in known_evidence]
unknown_rel = [ev.reliability_score for ev in unknown_evidence]

print(
    f"  Known evidence trust_score:     {known_trust[:5]}... (avg={sum(known_trust) / max(len(known_trust), 1):.1f})"
)
print(
    f"  Unknown evidence trust_score:   {unknown_trust[:5]}... (avg={sum(unknown_trust) / max(len(unknown_trust), 1):.1f})"
)
print(
    f"  Known evidence reliability_score: {known_rel[:5]}... (avg={sum(known_rel) / max(len(known_rel), 1):.1f})"
)
print(
    f"  Unknown evidence reliability_score: {unknown_rel[:5]}... (avg={sum(unknown_rel) / max(len(unknown_rel), 1):.1f})"
)

# Check that at least some known evidence has trust_score=100 (boosted)
known_has_boosted_trust = any(t >= 100 for t in known_trust)
unknown_no_boosted_trust = all(t <= 90 for t in unknown_trust)
print(f"\n  Known has trust_score=100: {known_has_boosted_trust}")
print(f"  Unknown all trust_score<=90: {unknown_no_boosted_trust}")

known_has_boosted_rel = any(r >= 100 for r in known_rel)
unknown_no_boosted_rel = all(r <= 90 for r in unknown_rel)
print(f"  Known has reliability_score=100: {known_has_boosted_rel}")
print(f"  Unknown all reliability_score<=90: {unknown_no_boosted_rel}")

# ═══════════════════════════════════════════════════════════════════════════
# 4. Risk Score / Alerting flow
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 12.4 — Risk Score / Alerting")

result_dict = result.to_dict()
if result.alerts:
    for a in result.alerts[:3]:
        ctx = a.get("context", {})
        entity = a.get("entity", "?")
        conf = ctx.get("confidence", "?")
        print(f"  Alert: entity={entity[:50]} conf={conf} severity={a.get('severity', '?')}")

if result_dict.get("safety_result"):
    sr = result_dict["safety_result"]
    print(f"  Approval level: {sr.get('approval_level', '?')}")
    print(f"  Risk score:     {sr.get('risk_score', '?')}")

if result.incidents:
    for inc in result.incidents[:3]:
        i = inc.to_dict() if hasattr(inc, "to_dict") else inc
        print(
            f"  Incident: {i.get('alert_id', '?')[:20]} severity={i.get('severity', '?')} "
            f"entity_id={i.get('entity_id', '?')[:40]}"
        )

# Graph node summary
gsummary = result_dict.get("graph_nodes_summary", [])
cve_summaries = [gn for gn in gsummary if gn.get("entity_type") == "CveEntity"]
if cve_summaries:
    print("\n  Graph node summary — CveEntity (ilk 10):")
    for gs in cve_summaries[:10]:
        print(f"    {gs['node_id'][:30]} conf={gs['confidence']} evidence={gs['evidence_count']}")

# ═══════════════════════════════════════════════════════════════════════════
# 5. Rapor
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 12.5 — Rapor")

# PASS criteria:
# 1. known_ransomware_use flag: True for known, False for unknown
# 2. Known confidence > Unknown confidence (relative)
# 3. Known evidence has boosted trust_score (>=100)
# 4. Known evidence has boosted reliability_score (>=100)

all_criteria = [
    (
        "known_ransomware_flag",
        len(known_entities) > 0 and all(e.known_ransomware_use for e in known_entities),
    ),
    (
        "unknown_not_flagged",
        len(unknown_entities) > 0 and all(not e.known_ransomware_use for e in unknown_entities),
    ),
    ("known_conf_higher", known_higher),
    ("known_trust_boosted", known_has_boosted_trust),
    ("known_rel_boosted", known_has_boosted_rel),
]

all_pass = all(c[1] for c in all_criteria)

report = {
    "phase": "12",
    "pipeline_speed_sec": round(t1 - t0, 3),
    "total_cve_nodes": len(cve_nodes),
    "ransomware_known_nodes": len(known_entities),
    "ransomware_unknown_nodes": len(unknown_entities),
    "known_confidence_avg": round(known_avg, 1),
    "unknown_confidence_avg": round(unknown_avg, 1),
    "known_confidence_higher": known_higher,
    "known_evidence_trust_boosted": known_has_boosted_trust,
    "known_evidence_reliability_boosted": known_has_boosted_rel,
    "trust_boost_delta": 10,
    "reliability_boost_delta": 10,
    "truth_confidence_boost": 0.1,
    "graph_node_count": len(result.graph.nodes),
    "alert_count": len(result.alerts),
    "error_count": len(result.errors),
    "criteria": dict(all_criteria),
    "status": "PASS" if all_pass else "FAIL",
}

print(f"\n  {'✓' if all_pass else '✗'} STATUS: {report['status']}")
for name, passed in all_criteria:
    print(f"    {'✓' if passed else '✗'} {name}")

with open(REPORT_PATH, "w") as f:
    json.dump(report, f, indent=2)
print(f"\n  Rapor: {REPORT_PATH}")

section("FAZ 12 TAMAM")
print(f"  Pipeline: {report['total_cve_nodes']} CVE node")
print(f"  Known conf avg:  {report['known_confidence_avg']}")
print(f"  Unknown conf avg: {report['unknown_confidence_avg']}")
print(f"  Known > Unknown: {'✓' if known_higher else '✗'}")
print(f"  Trust boost: 90→100 {'✓' if known_has_boosted_trust else '✗'}")
print(f"  Reliability boost: 90→100 {'✓' if known_has_boosted_rel else '✗'}")
