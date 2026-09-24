from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path

os.environ["OTX_API_KEY"] = "bc74aac50ae436dee05bfae89647406f73eed2cf947939f9d3e25461954ea12f"

from intelgraph.api.routers.dashboard import dashboard_state
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.pipeline.chain import Pipeline
from intelgraph.core.source.otx import OtxClient

URLHAUS_CSV = "/tmp/urlhaus_recent.csv"
KEV_PATH = "/tmp/opencode/phase10/kev.json"

# ── Overlapping IOCs (from cross-reference analysis) ──
OVERLAP_IPS = {"107.172.135.60", "107.172.235.213", "62.60.226.159"}
OVERLAP_DOMAINS = {"azurenetfiles.net", "everycarebd.com", "spasopro.at"}
OVERLAP_URLS = {
    "http://107.172.135.60/96/ibredgoodforbestthingscomingbackform.hta",
    "http://107.172.235.213/87/img_015059.png",
    "http://azurenetfiles.net:443/agent.ashx",
    "https://as.al/file/kbn1rc",
}
OVERLAP_CVES = {
    "cve-2015-2051",
    "cve-2016-4437",
    "cve-2017-11882",
    "cve-2017-9841",
    "cve-2018-0802",
    "cve-2018-15982",
    "cve-2018-20250",
    "cve-2021-26855",
    "cve-2021-26857",
    "cve-2021-26858",
}

print("=" * 65)
print("FAZ 19 — Dedup Duzeltmesi + Hash Dahil Tam Olcum")
print("=" * 65)

# ── 1. Load URLhaus entries that overlap ──
print("\n[1] URLhaus kesisen IOC'ler yukleniyor...")
matching_urls = []
with open(URLHAUS_CSV) as f:
    reader = csv.reader(l for l in f if not l.startswith("#"))
    for row in reader:
        if len(row) > 2:
            url = row[2].strip()
            ip = row[3].strip() if len(row) > 3 else ""
            # Check if this row overlaps with any known IOC
            if any(o in url.lower() for o in list(OVERLAP_IPS | OVERLAP_DOMAINS | OVERLAP_URLS)):
                matching_urls.append(url)
                if len(matching_urls) >= 10:
                    break

urlhaus_text = "\n".join(matching_urls)
print(f"  {len(matching_urls)} URLhaus satiri")

# ── 2. Load KEV entries that overlap ──
print("\n[2] KEV kesisen CVE'ler yukleniyor...")
kev_data = json.loads(Path(KEV_PATH).read_text())
matching_cves = [
    v for v in kev_data["vulnerabilities"] if v["cveID"].strip().lower() in OVERLAP_CVES
]
kev_text = "\n".join(
    f"{v['cveID']} {v.get('vendorProject', '')} {v.get('product', '')} "
    f"{v.get('shortDescription', '')} {v.get('knownRansomwareCampaignUse', '')}"
    for v in matching_cves
)
print(f"  {len(matching_cves)} CVE kaydi")

# ── 3. Fetch a small set of OTX pulses ──
print("\n[3] OTX pulse cekiliyor (5 sayfa x 20 = 100 pulse)...")
client = OtxClient()
pulses = client.get_pulses_all(max_pages=5, limit=20, delay=0.3)
print(f"  {len(pulses)} pulse")

# ── 4. Build sources ──
sources = [
    {
        "id": "urlhaus_overlap",
        "name": f"URLhaus ({len(matching_urls)} satir)",
        "text": urlhaus_text,
        "value": 60,
    },
    {
        "id": "kev_overlap",
        "name": f"CISA KEV ({len(matching_cves)} CVE)",
        "text": kev_text,
        "value": 90,
    },
]
for p in pulses:
    src = p.to_source_dict()
    sources.append(src)

# ── Hash indicator summary for Phase 19 ──
hash_counts: dict[str, int] = {"SHA256": 0, "MD5": 0, "SHA1": 0}
for p in pulses:
    for ind in p.indicators:
        itype = ind.get("type", "")
        if "SHA256" in itype:
            hash_counts["SHA256"] += 1
        if "MD5" in itype:
            hash_counts["MD5"] += 1
        if "SHA1" in itype:
            hash_counts["SHA1"] += 1
hash_total = sum(hash_counts.values())
print(
    f"\n  Hash indicator count: {hash_total} (SHA256={hash_counts['SHA256']}, MD5={hash_counts['MD5']}, SHA1={hash_counts['SHA1']})"
)

print(f"\n  Toplam kaynak: {len(sources)}")

# ── 5. Run pipeline ──
print("\n[5] Pipeline calistiriliyor...")
thresholds = {
    "c2_detection": {
        "enabled": True,
        "metric_key": "overall_confidence",
        "max": 0.4,
        "severity": "critical",
    },
}

t0 = time.time()
pipeline = Pipeline()
result = pipeline.run(sources=sources, thresholds=thresholds)
elapsed = time.time() - t0

result_dict = result.to_dict()
result_dict["source_texts"] = result.source_texts
dashboard_state.feed(result_dict)

print(f"\n  Pipeline: {elapsed:.2f}s")
print(f"  Entity:        {len(result.extracted_entities)}")
print(f"  Graph node:    {len(result.graph.nodes) if result.graph else 0}")
print(f"  Graph edge:    {len(result.graph.edges) if result.graph else 0}")
print(f"  Alert:         {len(result.alerts)}")
print(f"  Incident:      {len(result.incidents)}")
print(f"  Relationship:  {len(result.relationships)}")
print(f"  Contradiction: {len(result.contradictions)}")
print(f"  Merge audit:   {len(result_dict.get('merge_audit', []))}")
print(f"  Hata:          {len(result.errors)}")

# ── 6. Check EntityMatcher merge behavior ──
print("\n" + "=" * 65)
print("[6] EntityMatcher capraz birlestirme kontrolu")
print("=" * 65)

# Show merged entities with their evidence count
from intelgraph.core.entity.cve import CveEntity
from intelgraph.core.entity.domain import Domain

print(f"\n  Graph nodes: {len(result.graph.nodes)}")
print(f"  Merge audit entries: {len(result_dict.get('merge_audit', []))}")
print(f"  Graph edges: {len(result.graph.edges)}")

# Check specific overlapping entities
print("\n  --- Overlap test: overlapping IPs ---")
for nid, node in result.graph.nodes.items():
    if isinstance(node.entity, IPAddress):
        ip = node.entity.ip
        if ip in OVERLAP_IPS:
            print(f"    {ip}: {len(node.entity.evidence)} evidence, node_id={nid}")

print("\n  --- Overlap test: overlapping domains ---")
for nid, node in result.graph.nodes.items():
    if isinstance(node.entity, Domain):
        domain = node.entity.domain_name
        if domain in OVERLAP_DOMAINS or any(o in domain for o in OVERLAP_DOMAINS):
            print(f"    {domain}: {len(node.entity.evidence)} evidence, node_id={nid}")

print("\n  --- Overlap test: overlapping CVEs ---")
for nid, node in result.graph.nodes.items():
    if isinstance(node.entity, CveEntity):
        if node.entity.cve_id.lower() in OVERLAP_CVES:
            print(
                f"    {node.entity.cve_id}: conf={node.entity.confidence_score} ev={len(node.entity.evidence)} node_id={nid}"
            )

# Show merge audit details for overlapping entities
print("\n  --- Merge audit (all) ---")
for ma in result_dict.get("merge_audit", []):
    print(
        f"    {ma.get('source_entity_id', '')} -> {ma.get('target_entity_id', '')} ({ma.get('merge_strategy', '?')})"
    )

# Show alerts
print("\n  --- Alerts ---")
for a in result.alerts:
    ctx = a.get("context", {})
    print(
        f"    [{a['category']}] entity={ctx.get('entity_id', '')[:40]} cve={ctx.get('cve_id', '')}"
    )

# ── Phase 19: Hash indicator → node counting ──
print("\n" + "=" * 65)
print("[7] Hash indicator graph node analizi (Faz 19)")
print("=" * 65)
hash_entity_count = 0
hash_entity_types: dict[str, int] = {}
for e in result.extracted_entities:
    if e.label in ("HASH_MD5", "HASH_SHA1", "HASH_SHA256"):
        hash_entity_count += 1
        hash_entity_types[e.label] = hash_entity_types.get(e.label, 0) + 1
print(f"\n  NER tarafından çıkarılan hash entity: {hash_entity_count}")
for t, c in sorted(hash_entity_types.items()):
    print(f"    {t}: {c}")
hash_node_count = 0
if result.graph:
    for node in result.graph.nodes.values():
        if isinstance(node.entity, IPAddress):
            ip = node.entity.ip
            if (
                re.match(r"^[a-fA-F0-9]{32}$", ip)
                or re.match(r"^[a-fA-F0-9]{40}$", ip)
                or re.match(r"^[a-fA-F0-9]{64}$", ip)
            ):
                hash_node_count += 1
print(f"  Graph node (hash → IPAddress): {hash_node_count}")
print(
    f"  Hash entity → graph node oranı: {hash_node_count}/{hash_entity_count} ({hash_node_count * 100 // max(hash_entity_count, 1)}%)"
)
print(
    f"  Hash entity'lerin merge edilme oranı: {hash_entity_count - hash_node_count}/{hash_entity_count} ({(hash_entity_count - hash_node_count) * 100 // max(hash_entity_count, 1)}%)"
)

# Show explain for each incident
print("\n  --- Incidents ---")
from intelgraph.core.explanation.builder import ExplanationBuilder

builder = ExplanationBuilder(result_dict)
for inc in result.incidents:
    inc_id = inc.get("alert_id", "")
    expl = builder.explain(inc_id)
    steps = expl.get("steps", [])
    print(
        f"    {inc_id}: [{inc.get('category')}] {len(steps)} steps, entity={expl.get('primary_entity', '')[:40]}"
    )

pipeline.cleanup()
print("\n" + "=" * 65)
print("FAZ 19 TAMAM")
print("=" * 65)
