from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

os.environ["OTX_API_KEY"] = "bc74aac50ae436dee05bfae89647406f73eed2cf947939f9d3e25461954ea12f"

from intelgraph.core.source.otx import OtxClient, fetch_urlhaus_iocs

URLHAUS_CSV = "/tmp/urlhaus_recent.csv"
KEV_PATH = "/tmp/opencode/phase10/kev.json"

# ── 1. Fetch OTX pulses (multi-page) ──
print("=" * 65)
print("FAZ 18 — OTX Genisletme + Capraz Kaynak Analizi")
print("=" * 65)

print("\n[1] OTX pulse cekiliyor (10 sayfa x 20 = 200 pulse)...")
t0 = time.time()
client = OtxClient()
pulses = client.get_pulses_all(max_pages=10, limit=20, delay=0.3)
elapsed = time.time() - t0
print(f"  {len(pulses)} pulse alindi ({elapsed:.1f}s)")
total_indicators = sum(len(p.indicators) for p in pulses)
print(f"  Toplam indicator: {total_indicators}")

# ── 2. Extract OTX IOCs by type ──
otx_iocs = client.extract_iocs(pulses)
print("\n  OTX IOC dagilimi:")
for t, items in sorted(otx_iocs.items()):
    if items:
        print(f"    {t}: {len(items)}")
        for s in items[:3]:
            print(f"      ornek: {s['indicator'][:50]}")
otx_all_indicators = set()
for t, items in otx_iocs.items():
    for it in items:
        otx_all_indicators.add(it["indicator"].strip().lower())

print(f"\n  OTX unique indicator: {len(otx_all_indicators)}")

# ── 3. Load URLhaus full dataset ──
print("\n[2] URLhaus tam veri seti yukleniyor...")
t0 = time.time()
urlhaus_iocs = fetch_urlhaus_iocs(URLHAUS_CSV)
urlhaus_all = set()
for t, items in urlhaus_iocs.items():
    for it in items:
        urlhaus_all.add(it["indicator"].strip().lower())
print(f"  {len(urlhaus_all)} unique IOC ({time.time() - t0:.1f}s)")
for t, items in sorted(urlhaus_iocs.items()):
    print(f"    {t}: {len(items)}")

# ── 4. Load CISA KEV full dataset ──
print("\n[3] CISA KEV tam veri seti yukleniyor...")
t0 = time.time()
kev_data = json.loads(Path(KEV_PATH).read_text())
kev_entries = kev_data["vulnerabilities"]
kev_cves = {v["cveID"].strip().lower() for v in kev_entries}
# Also collect IPs and domains mentioned in KEV descriptions
kev_ips = set()
kev_domains = set()
import re

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b")
for v in kev_entries:
    desc = v.get("shortDescription", "") + " " + v.get("notes", "")
    for m in IP_RE.finditer(desc):
        kev_ips.add(m.group())
    for m in DOMAIN_RE.finditer(desc):
        d = m.group().lower()
        if not d.startswith("http") and d.count(".") >= 1:
            kev_domains.add(d)
print(
    f"  {len(kev_cves)} CVE, {len(kev_ips)} IP, {len(kev_domains)} domain ({time.time() - t0:.1f}s)"
)

# ── 5. Cross-reference: OTX ∩ URLhaus ──
print("\n[4] Capraz referans analizi:")
print("-" * 50)

# OTX ∩ URLhaus
otx_urlhaus = otx_all_indicators & urlhaus_all
print(f"\n  OTX ∩ URLhaus: {len(otx_urlhaus)} ortak IOC")
if otx_urlhaus:
    for val in sorted(otx_urlhaus)[:10]:
        print(f"    {val}")

# OTX ∩ KEV (CVE)
otx_cves = {it["indicator"].strip().lower() for it in otx_iocs.get("CVE", [])}
otx_kev_cve = otx_cves & kev_cves
print(f"\n  OTX CVE ∩ KEV: {len(otx_kev_cve)} ortak CVE")
if otx_kev_cve:
    for val in sorted(otx_kev_cve)[:10]:
        print(f"    {val}")

# OTX IP ∩ URLhaus IP
otx_ips = {it["indicator"].strip().lower() for it in otx_iocs.get("IPv4", [])}
urlhaus_ips = {it["indicator"].strip().lower() for it in urlhaus_iocs.get("IPv4", [])}
otx_urlhaus_ip = otx_ips & urlhaus_ips
print(f"\n  OTX IPv4 ∩ URLhaus IPv4: {len(otx_urlhaus_ip)} ortak IP")
if otx_urlhaus_ip:
    for val in sorted(otx_urlhaus_ip)[:10]:
        print(f"    {val}")

# OTX domain ∩ URLhaus domain
otx_domains = {it["indicator"].strip().lower() for it in otx_iocs.get("domain", [])}
otx_domains |= {it["indicator"].strip().lower() for it in otx_iocs.get("hostname", [])}
urlhaus_domains = {it["indicator"].strip().lower() for it in urlhaus_iocs.get("domain", [])}
otx_urlhaus_domain = otx_domains & urlhaus_domains
print(f"\n  OTX domain/hostname ∩ URLhaus domain: {len(otx_urlhaus_domain)} ortak domain")
if otx_urlhaus_domain:
    for val in sorted(otx_urlhaus_domain)[:10]:
        print(f"    {val}")

# OTX IP ∩ KEV IP
otx_kev_ip = otx_ips & kev_ips
print(f"\n  OTX IPv4 ∩ KEV IP: {len(otx_kev_ip)} ortak IP")
if otx_kev_ip:
    for val in sorted(otx_kev_ip)[:10]:
        print(f"    {val}")

# ── 6. Detailed cross-match for pipeline test ──
print("\n" + "=" * 65)
print("[5] Detayli eslesme kontrolu")
print("=" * 65)

# If we found any overlaps, show details
if otx_urlhaus:
    print("\nOTX ↔ URLhaus eslesmeleri:")
    for val in sorted(otx_urlhaus)[:10]:
        # Find URLhaus entry
        uh = [
            it
            for t, items in urlhaus_iocs.items()
            for it in items
            if it["indicator"].strip().lower() == val
        ]
        ot = [
            it
            for t, items in otx_iocs.items()
            for it in items
            if it["indicator"].strip().lower() == val
        ]
        print(f"\n  Ortak: {val}")
        if uh:
            print(f"    URLhaus kaynak: {uh[0].get('source', '?')}")
        if ot:
            print(f"    OTX pulse: {ot[0].get('pulse_name', '?')[:50]}")
            print(f"    OTX tip: {ot[0].get('type', '?')}")

# ── 7. Pipeline test with overlapping data (if found) ──
print("\n" + "=" * 65)
print("[6] Pipeline testi (OTX + URLhaus + KEV)")
print("=" * 65)

# Build sources from OTX pulses
sources = []

# URLhaus: pick entries that overlap with OTX (or first 50 if no overlap)
urlhaus_overlap = otx_urlhaus
urlhaus_sample_text = ""
if urlhaus_overlap:
    print(f"\n  Kesisen {len(urlhaus_overlap)} IOC'li URLhaus verisi kullaniliyor")
    matching_rows = []
    with open(URLHAUS_CSV) as f:
        reader = csv.reader(l for l in f if not l.startswith("#"))
        for row in reader:
            if len(row) > 2:
                val = row[2].strip().lower()
                if val in urlhaus_overlap:
                    matching_rows.append(row)
    if matching_rows:
        urlhaus_sample_text = "\n".join(r[2] for r in matching_rows[:100])
        sources.append(
            {
                "id": "urlhaus_overlap",
                "name": f"URLhaus (OTX overlap, {len(matching_rows)} satir)",
                "text": urlhaus_sample_text,
                "value": 60,
            }
        )
        print(f"  {len(matching_rows)} URLhaus satiri eslesme bulundu")

if not urlhaus_sample_text:
    print("\n  (OTX ile URLhaus ortak IOC yok — ilk 50 URLhaus satiri kullaniliyor)")
    with open(URLHAUS_CSV) as f:
        reader = csv.reader(l for l in f if not l.startswith("#"))
        urlhaus_rows = [r[2] for i, r in enumerate(reader) if i < 50]
    urlhaus_sample_text = "\n".join(urlhaus_rows)
    sources.append(
        {
            "id": "urlhaus_50",
            "name": "URLhaus (50)",
            "text": urlhaus_sample_text,
            "value": 60,
        }
    )

# KEV: use overlapping CVEs if found
kev_overlap = otx_kev_cve
kev_text = ""
if kev_overlap:
    print(f"\n  Kesisen {len(kev_overlap)} CVE'li KEV verisi kullaniliyor")
    matching = [v for v in kev_entries if v["cveID"].strip().lower() in kev_overlap]
    if matching:
        kev_text = "\n".join(
            f"{v['cveID']} {v.get('vendorProject', '')} {v.get('product', '')} "
            f"{v.get('shortDescription', '')} {v.get('knownRansomwareCampaignUse', '')}"
            for v in matching[:20]
        )
        sources.append(
            {
                "id": "kev_overlap",
                "name": f"CISA KEV (OTX overlap, {len(matching)} CVE)",
                "text": kev_text,
                "value": 90,
            }
        )

if not kev_text:
    print("\n  (OTX ile KEV ortak CVE yok — ilk 10 KEV kaydi kullaniliyor)")
    kev_text = "\n".join(
        f"{v['cveID']} {v.get('vendorProject', '')} {v.get('product', '')} "
        f"{v.get('shortDescription', '')} {v.get('knownRansomwareCampaignUse', '')}"
        for v in kev_entries[:10]
    )
    sources.append(
        {
            "id": "kev_10",
            "name": "CISA KEV (10)",
            "text": kev_text,
            "value": 90,
        }
    )

# OTX: use all pulses (but filter indicators to IP/domain/CVE to avoid hash O(n²) explosion)
for p in pulses:
    src = p.to_source_dict()
    # Keep only relevant indicators for cross-source matching
    text_parts = []
    for ind in p.indicators:
        itype = ind.get("type", "")
        ival = ind.get("indicator", "")
        if itype in ("IPv4", "domain", "hostname", "URL", "CVE") and ival:
            text_parts.append(f"{itype}:{ival}")
    if text_parts:
        src["text"] = "OTX Pulse: " + p.name + ". Indicators: " + "; ".join(text_parts[:50]) + "."
    sources.append(src)

print(f"\n  Toplam kaynak: {len(sources)} ({sum(len(s.get('text', '')) for s in sources)} chars)")

# Run pipeline
from intelgraph.api.routers.dashboard import dashboard_state
from intelgraph.core.pipeline.chain import Pipeline

thresholds = {
    "c2_detection": {
        "enabled": True,
        "metric_key": "overall_confidence",
        "max": 0.4,
        "severity": "critical",
    },
}

print("\n  Pipeline calistiriliyor...")
t0 = time.time()
pipeline = Pipeline()
result = pipeline.run(sources=sources, thresholds=thresholds)
elapsed = time.time() - t0
result_dict = result.to_dict()
result_dict["source_texts"] = result.source_texts
dashboard_state.feed(result_dict)

print(f"  Pipeline: {elapsed:.2f}s")
print(f"  Entity:  {len(result.extracted_entities)}")
print(f"  Graph node: {len(result.graph.nodes) if result.graph else 0}")
print(f"  Graph edge: {len(result.graph.edges) if result.graph else 0}")
print(f"  Alert: {len(result.alerts)}")
print(f"  Incident: {len(result.incidents)}")
print(f"  Relationship: {len(result.relationships)}")
print(f"  Contradiction: {len(result.contradictions)}")
print(f"  Merge audit: {len(result_dict.get('merge_audit', []))}")
print(f"  Hata: {len(result.errors)}")

# Show CVE entities
from intelgraph.core.entity.cve import CveEntity

cve_nodes = [(nid, n) for nid, n in result.graph.nodes.items() if isinstance(n.entity, CveEntity)]
print(f"\n  CveEntity node: {len(cve_nodes)}")
for nid, n in cve_nodes:
    e = n.entity
    print(
        f"    {nid}: conf={e.confidence_score} rw={e.known_ransomware_use} vendor={e.vendor_project}"
    )

# Show incidents with explain
print("\n  Incidentler:")
from intelgraph.core.explanation.builder import ExplanationBuilder

builder = ExplanationBuilder(result_dict)
for inc in result.incidents:
    inc_id = inc.get("alert_id", "")
    expl = builder.explain(inc_id)
    steps = expl.get("steps", [])
    phases = [s["phase"] for s in steps]
    print(f"    {inc_id}: [{inc.get('category')}] {len(steps)} adim: {phases}")

pipeline.cleanup()

print("\n" + "=" * 65)
print("FAZ 18 TAMAM")
print("=" * 65)
