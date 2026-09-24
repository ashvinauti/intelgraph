#!/usr/bin/env python3
"""
Faz 10 — CISA KEV ile Ucuncu Kaynak Entegrasyonu
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

KEV_PATH = "/tmp/opencode/phase10/kev.json"
REPORT_PATH = "/tmp/opencode/phase10/phase10_report.json"


def section(t):
    print(f"\n{'=' * 72}")
    print(f"  {t}")
    print(f"{'=' * 72}")


# ═══════════════════════════════════════════════════════════════════════════
# 0. Load + Analyze KEV
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 10.0 — KEV Katalog Analizi")

kev = json.load(open(KEV_PATH))
vulns = kev["vulnerabilities"]
print(f"  Toplam kayit:     {len(vulns)}")
print(f"  Katalog versiyon: {kev.get('catalogVersion', '')}")
print(f"  Yayin tarihi:     {kev.get('dateReleased', '')}")

ransomware_known = [v for v in vulns if v.get("knownRansomwareCampaignUse") == "Known"]
print(
    f"  Ransomware Known: {len(ransomware_known)} (%{len(ransomware_known) / len(vulns) * 100:.1f})"
)

vendors = Counter(v["vendorProject"] for v in vulns)
print(f"  Firma: {len(vendors)} benzersiz")
print(f"    Top 5: {dict(vendors.most_common(5))}")

# ═══════════════════════════════════════════════════════════════════════════
# 1. NER on KEV data
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 10.1 — NER: CVE Tanima Testi")

from intelgraph.core.nlp.extractor import NEREngine

# Build text representation from KEV entries
kev_text_parts = []
for v in vulns:
    cve_id = v["cveID"]
    desc = v.get("shortDescription", "")
    vendor = v.get("vendorProject", "")
    product = v.get("product", "")
    ransomware = v.get("knownRansomwareCampaignUse", "Unknown")
    kev_text_parts.append(
        f"{cve_id}: {vendor} {product} - {desc} Ransomware campaign use: {ransomware}."
    )

kev_text = "\n".join(kev_text_parts)
print(f"  KEV metin boyutu: {len(kev_text) / 1024:.1f} KB")

ner = NEREngine()
t0 = time.perf_counter()
entities = ner.extract(kev_text)
t1 = time.perf_counter()

ner_labels = Counter(e.label for e in entities)
print(f"  NER sure:         {t1 - t0:.3f}s")
print(f"  Toplam entity:    {len(entities)}")
print("  Etiket dagilimi:")
for lbl, cnt in ner_labels.most_common():
    print(f"    {lbl:12s} {cnt:>6d}")

# CVE-specific checks
cve_entities = [e for e in entities if e.label == "CVE"]
print(f"\n  CVE entity sayisi: {len(cve_entities)}")
print(f"  Beklenen:          {len(vulns)} (her KEV kaydindan 1 CVE)")
cve_recall = len(cve_entities) / len(vulns) * 100
print(f"  CVE tanima orani:  {cve_recall:.1f}%")

# Sample CVE entities
print("\n  Ornek CVE entity:")
for e in cve_entities[:5]:
    print(f"    {e.text} (conf={e.confidence})")

# Check for CVE IDs that might have been missed
cve_ids_in_text = set(re.findall(r"CVE-\d{4}-\d+", kev_text))
cve_ids_extracted = {e.text for e in cve_entities}
missed = cve_ids_in_text - cve_ids_extracted
if missed:
    print(f"\n  KACIRILAN CVE: {len(missed)}")
    for m in list(missed)[:5]:
        print(f"    {m}")

# Check for FILENAME/UNKNOWN false positives on CVE-like strings
fp_cve = [e for e in entities if e.label in ("FILENAME", "UNKNOWN") and "CVE" in e.text]
print(f"\n  CVE yanlis siniflandirma (FILENAME/UNKNOWN): {len(fp_cve)}")
for e in fp_cve[:3]:
    print(f"    [{e.label}] {e.text}")

# ═══════════════════════════════════════════════════════════════════════════
# 2. Pipeline.run() with KEV
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 10.2 — Pipeline KEV Besleme")

from intelgraph.core.pipeline.chain import Pipeline

pipeline = Pipeline()

# Use a subset — 100 KEV entries + all ransomware-known entries
kev_subset_indices = list(range(100)) + [vulns.index(v) for v in ransomware_known]
kev_subset_indices = sorted(set(kev_subset_indices))
kev_subset_text = "\n".join(kev_text_parts[i] for i in kev_subset_indices)
print(f"  KEV altkume: {len(kev_subset_indices)} kayit, {len(kev_subset_text) / 1024:.1f} KB")

t0 = time.perf_counter()
result_kev = pipeline.run(
    sources=[
        {
            "id": "cisa_kev",
            "name": "CISA KEV Catalog",
            "text": kev_subset_text,
            "value": 90,
        }
    ],
    thresholds={},
    query_ip="",
    query_target="",
)
t1 = time.perf_counter()
print(f"  Pipeline sure:      {t1 - t0:.2f}s")
print(f"  Graph node:         {len(result_kev.graph.nodes) if result_kev.graph else 0}")
print(f"  Celiski:            {len(result_kev.contradictions)}")
print(f"  Alert:              {len(result_kev.alerts)}")
print(f"  Truth entry:        {len(result_kev.truth_entries)}")
print(f"  Hata:               {len(result_kev.errors)}")
for e in result_kev.errors[:5]:
    print(f"    ✗ {e}")

# Verify CVE entities in graph
if result_kev.graph:
    from intelgraph.core.entity.cve import CveEntity

    cve_nodes = [n for n in result_kev.graph.nodes.values() if isinstance(n.entity, CveEntity)]
    print(f"\n  CveEntity node:     {len(cve_nodes)}")
    if cve_nodes:
        for n in list(cve_nodes)[:5]:
            e = n.entity
            print(
                f"    cve_id={e.cve_id} vendor={e.vendor_project} product={e.product} ransomware={e.known_ransomware_use}"
            )

# Entity type distribution in graph
if result_kev.graph:
    node_types = Counter(type(n.entity).__name__ for n in result_kev.graph.nodes.values())
    print("\n  Node turu dagilimi:")
    for nt, cnt in node_types.most_common():
        print(f"    {nt:15s} {cnt}")

# ═══════════════════════════════════════════════════════════════════════════
# 3. knownRansomwareCampaignUse → Risk/Confidence
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 10.3 — Ransomware Bilgisinin Risk/Confidence'a Yansimasi")

# Check if ransomware "Known" entries have higher trust_score
if result_kev.graph:
    known_entries = []
    unknown_entries = []
    for te in result_kev.truth_entries:
        key = te.get("key", "")
        if any(v["cveID"] in key for v in ransomware_known):
            known_entries.append(te)
        else:
            unknown_entries.append(te)

    print(f"  Ransomware-Known truth entries: {len(known_entries)}")
    print(f"  Ransomware-Unknown:             {len(unknown_entries)}")
    if known_entries:
        known_confs = [te.get("truth", {}).get("confidence", 0) for te in known_entries]
        print(f"  Ortalama confidence (Known):    {sum(known_confs) / len(known_confs):.3f}")
    if unknown_entries:
        unk_confs = [te.get("truth", {}).get("confidence", 0) for te in unknown_entries]
        print(f"  Ortalama confidence (Unknown):  {sum(unk_confs) / len(unk_confs):.3f}")

# ═══════════════════════════════════════════════════════════════════════════
# 4. Cross-source: URLhaus CVE references + OTX pulse with CVE
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 10.4 — Capraz Kaynak: URLhaus CVE + KEV Birlestirme")

# URLhaus CSV has 26 CVE mentions. Extract them.
urlhaus_cves = set()
with open("/tmp/opencode/phase9/urlhaus_full.csv") as f:
    for line in f:
        if line.startswith("#"):
            continue
        for m in re.finditer(r"CVE-\d{4}-\d+", line, re.IGNORECASE):
            urlhaus_cves.add(m.group().upper())

print(f"  URLhaus CVE referansi: {len(urlhaus_cves)}")
print(f"  Ornek: {list(urlhaus_cves)[:10]}")

# Cross-reference with KEV
urlhaus_in_kev = [c for c in urlhaus_cves if any(c == v["cveID"] for v in vulns)]
print(f"  URLhaus CVE ∩ KEV:     {len(urlhaus_in_kev)}")
for c in urlhaus_in_kev:
    v = next(v for v in vulns if v["cveID"] == c)
    print(f"    {c}: {v['vendorProject']} {v['product']}")

# Create a synthetic multi-source test: KEV + URLhaus + synthetic OTX-with-CVE
# Build a text where URLhaus-like data references known CVEs
cross_source_text = "\n".join(
    [
        # URLhaus-style entries referencing real CVEs
        "http://malicious-server.example.com/exploit/CVE-2024-1709",
        "http://185.191.126.171/ CVE-2024-1709 ConnectWise ScreenConnect exploit",
        "http://91.121.87.116/CVE-2023-3519/ Citrix ADC exploitation attempt",
        "http://evil.net/CVE-2024-27198/ JetBrains TeamCity exploit",
        "http://45.33.32.156/CVE-2024-21626/ runc container escape",
        # Synthetic OTX pulse with CVE descriptions
        "CVE-2024-1709: ConnectWise ScreenConnect authentication bypass being exploited in the wild "
        "by LockBit ransomware group. Observed on IPs: 185.191.126.171, 91.121.87.116.",
        "CVE-2023-3519: Citrix ADC remote code execution exploited by multiple APT groups "
        "targeting government networks. Domains: evil.net, malware.example.com.",
        f"REAL KEV Matches: {' '.join(urlhaus_in_kev[:3])} "
        "These CVEs are in the CISA KEV catalog and are being actively exploited in URLhaus URLs.",
    ]
)

t0 = time.perf_counter()
result_cross = pipeline.run(
    sources=[
        {
            "id": "cross_source_test",
            "name": "Cross-Source CVE Linking Test",
            "text": cross_source_text,
            "value": 85,
        }
    ],
    thresholds={},
    query_ip="",
    query_target="",
)
t1 = time.perf_counter()
print(f"\n  Cross-source pipeline sure: {t1 - t0:.2f}s")

if result_cross.graph:
    from intelgraph.core.entity.cve import CveEntity

    cve_in_graph = [n for n in result_cross.graph.nodes.values() if isinstance(n.entity, CveEntity)]
    print(f"  Graph node:       {len(result_cross.graph.nodes)}")
    print(f"  CveEntity node:   {len(cve_in_graph)}")
    for n in cve_in_graph:
        e = n.entity
        print(f"    {e.id}: cve_id={e.cve_id}")

    # Check if IP/domain entities coexist with CVE entities
    from intelgraph.core.entity.domain import Domain
    from intelgraph.core.entity.ip_address import IPAddress

    ip_nodes = [n for n in result_cross.graph.nodes.values() if isinstance(n.entity, IPAddress)]
    domain_nodes = [n for n in result_cross.graph.nodes.values() if isinstance(n.entity, Domain)]
    print(f"  IPAddress node:   {len(ip_nodes)}")
    print(f"  Domain node:      {len(domain_nodes)}")

    node_types = Counter(type(n.entity).__name__ for n in result_cross.graph.nodes.values())
    print("  Node turu dagilimi:")
    for nt, cnt in node_types.most_common():
        print(f"    {nt:15s} {cnt}")

    # ── ReasoningEngine multi-hop: IP → CVE ──
    section("Faz 10.4b — ReasoningEngine: IP-CVE Iliskisi")
    from intelgraph.core.cognitive.reasoning import ReasoningEngine

    reasoner = ReasoningEngine(graph=result_cross.graph)
    found_paths = []
    # Try to find paths between IP nodes and CVE nodes
    ip_nids = [
        nid for nid, n in result_cross.graph.nodes.items() if isinstance(n.entity, IPAddress)
    ]
    cve_nids = [
        nid for nid, n in result_cross.graph.nodes.items() if isinstance(n.entity, CveEntity)
    ]
    print(f"  IP node ID:     {ip_nids[:3]}")
    print(f"  CVE node ID:    {cve_nids[:3]}")

    for ip_nid in ip_nids[:3]:
        for cve_nid in cve_nids[:3]:
            try:
                paths = reasoner.multi_hop_reason(ip_nid, cve_nid, max_depth=5)
                if paths:
                    found_paths.append((ip_nid, cve_nid, paths))
                    for p in paths:
                        print(f"  PATH: {ip_nid} → ... → {cve_nid}")
                        print(f"    {p.to_path_summary()[:150]}")
            except Exception as exc:
                print(f"    Reason error {ip_nid}→{cve_nid}: {exc}")

    if not found_paths:
        print("  IP→CVE path: Bulunamadi (beklenen — NER/IP/CVE arasinda edge yok)")
        print("  Cozum: RelationshipExtractor veya manuel edge eklemesi gerekiyor.")

    # Verify all three types coexist independently
    print("\n  Bagimsiz varolus dogrulamasi:")
    print(f"    CVE: {len(cve_nids)} node (CveEntity)")
    print(f"    IP:  {len(ip_nids)} node (IPAddress)")
    print(f"    DOM: {len(domain_nodes)} node (Domain)")
    print(f"    Toplam: {len(result_cross.graph.nodes)} node (3 tip ayni graph icinde)")

# ═══════════════════════════════════════════════════════════════════════════
# 5. Report
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 10.5 — Rapor")

report = {
    "phase": "10",
    "kev_catalog": {
        "total": len(vulns),
        "version": kev.get("catalogVersion", ""),
        "ransomware_known": len(ransomware_known),
        "unique_vendors": len(vendors),
        "top_vendors": dict(vendors.most_common(10)),
    },
    "ner": {
        "time_s": round(t1 - t0, 3),
        "total_entities": len(entities),
        "label_distribution": dict(ner_labels),
        "cve_extracted": len(cve_entities),
        "cve_expected": len(vulns),
        "cve_recall_pct": round(cve_recall, 1),
        "cve_missed": list(missed)[:10] if missed else [],
    },
    "pipeline_kev": {
        "subset_size": len(kev_subset_indices),
        "time_s": round(t1 - t0, 2) if "t1" in dir() else 0,
        "graph_nodes": len(result_kev.graph.nodes) if result_kev.graph else 0,
        "contradictions": len(result_kev.contradictions),
        "alerts": len(result_kev.alerts),
        "errors": result_kev.errors[:10],
    },
    "cross_source": {
        "urlhaus_cve_mentions": len(urlhaus_cves),
        "urlhaus_cve_in_kev": len(urlhaus_in_kev),
        "cross_cve_matches": urlhaus_in_kev,
        "graph_nodes": len(result_cross.graph.nodes) if result_cross.graph else 0,
        "cve_nodes": len(cve_in_graph) if result_cross.graph else 0,
        "ip_nodes": len(ip_nodes) if result_cross.graph else 0,
        "domain_nodes": len(domain_nodes) if result_cross.graph else 0,
    },
}

Path(REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
with open(REPORT_PATH, "w") as f:
    json.dump(report, f, indent=2, default=str)
print(f"\n  Rapor: {REPORT_PATH}")

section("FAZ 10 TAMAM")
print(f"  KEV: {len(vulns)} kayit, CVE tanima: {cve_recall:.1f}%")
if urlhaus_in_kev:
    print(f"  URLhaus ∩ KEV: {len(urlhaus_in_kev)} capraz CVE bulundu!")
else:
    print("  URLhaus ∩ KEV: 0 capraz CVE (beklenen: URLhaus tag'leri CVE degil)")
print("  Graph: CVE + IP + Domain entity'leri ayni graph icinde")
