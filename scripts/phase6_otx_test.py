#!/usr/bin/env python3
"""
Phase 6 — OTX'i Ikinci Kaynak Olarak Ekle ve Çapraz Kaynak Testi

1. OTX'ten pulse/IOC çek (OTX_API_KEY env)
2. URLhaus'tan IOC çek
3. Çapraz kaynak eşleşmesi ara
4. Pipeline.run() ile her iki kaynağı aynı anda işle
5. EntityMatcher birleştirme davranışını doğrula
6. NER FP fix'inin OTX verisinde çalıştığını kontrol et
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

from intelgraph.core.nlp.extractor import NEREngine
from intelgraph.core.pipeline.chain import Pipeline
from intelgraph.core.source.otx import OtxClient, fetch_urlhaus_iocs

OUT_DIR = Path("/tmp/opencode/phase6")
OUT_DIR.mkdir(parents=True, exist_ok=True)

API_KEY = os.environ.get("OTX_API_KEY", "")
if not API_KEY:
    sys.exit("❌ OTX_API_KEY environment variable is not set.")

URLHAUS_CSV = "/tmp/urlhaus_recent.csv"
if not Path(URLHAUS_CSV).exists():
    sys.exit(f"❌ URLhaus CSV not found at {URLHAUS_CSV}")


def section(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


# ── 1. OTX'ten Pulse Çek ─────────────────────────────────────
section("1. OTX API'den Pulse Çekme")

client = OtxClient(api_key=API_KEY)
pulses = client.get_pulses(page=1, limit=10)
print(f"  Çekilen pulse sayısı: {len(pulses)}")

all_otx_iocs = client.extract_iocs(pulses)
total_otx_iocs = sum(len(v) for v in all_otx_iocs.values())
print(f"  Toplam IOC sayısı: {total_otx_iocs}")

# IOC tipi dağılımı
print("\n  IOC Tipi Dağılımı:")
for ioc_type, items in sorted(all_otx_iocs.items()):
    if items:
        print(f"    {ioc_type:12s}: {len(items)}")

# Pulse detaylarını göster
print("\n  Pulse Detayları:")
for p in pulses[:5]:
    print(f"    [{p.pulse_id[:12]}..] {p.name}")
    print(
        f"           author={p.author}, tags={p.tags[:5]}, "
        f"indicators={len(p.indicators)}, tlp={p.tlp}"
    )

# Bir pulse'ın source dict formatını göster
src_example = pulses[0].to_source_dict()
print("\n  Örnek source dict (ilk pulse):")
print(f"    id={src_example['id']}")
print(f"    text[:200]={src_example['text'][:200]}...")


# ── 2. URLhaus IOC'lerini Çek ─────────────────────────────────
section("2. URLhaus IOC'lerini Çek")

urlhaus_iocs = fetch_urlhaus_iocs(URLHAUS_CSV)
total_urlhaus = sum(len(v) for v in urlhaus_iocs.values())
print(f"  Toplam URLhaus IOC sayısı: {total_urlhaus}")
for ioc_type, items in sorted(urlhaus_iocs.items()):
    unique_vals = len({i["indicator"].strip().lower() for i in items if i.get("indicator")})
    print(f"    {ioc_type:12s}: {len(items)} entry, {unique_vals} unique")


# ── 3. Çapraz Kaynak Eşleşmesi ────────────────────────────────
section("3. Çapraz Kaynak Eşleşmesi")

common: list[tuple] = []
for ioc_type in ("domain", "IPv4", "URL"):
    matched = OtxClient.find_common_iocs(
        urlhaus_iocs.get(ioc_type, []),
        all_otx_iocs.get(ioc_type, []),
    )
    for u, o in matched:
        common.append((ioc_type, u, o))
    if matched:
        print(f"  {ioc_type}: {len(matched)} ortak IOC bulundu!")
        for u, o in matched[:5]:
            print(f"    ✓ '{u['indicator']}' — OTX pulse: {o['pulse_name'][:60]}")
    else:
        print(f"  {ioc_type}: ortak IOC bulunamadı")

# Even if no exact match, we check for IP overlaps specifically
# because URLhaus IPs are often in OTX too
urlhaus_domains = {i["indicator"].strip().lower() for i in urlhaus_iocs.get("domain", [])}
otx_domains = {i["indicator"].strip().lower() for i in all_otx_iocs.get("domain", [])}
urlhaus_ips = {i["indicator"].strip().lower() for i in urlhaus_iocs.get("IPv4", [])}
otx_ips = {i["indicator"].strip().lower() for i in all_otx_iocs.get("IPv4", [])}

ip_overlap = urlhaus_ips & otx_ips
domain_overlap = urlhaus_domains & otx_domains

print("\n  Küme kesişimi (unique değerler):")
print(f"    IP     URLhaus={len(urlhaus_ips)}  OTX={len(otx_ips)}  ortak={len(ip_overlap)}")
print(
    f"    Domain URLhaus={len(urlhaus_domains)}  OTX={len(otx_domains)}  ortak={len(domain_overlap)}"
)

if ip_overlap:
    for ip in list(ip_overlap)[:3]:
        print(f"    ✓ Ortak IP: {ip}")
if domain_overlap:
    for d in list(domain_overlap)[:3]:
        print(f"    ✓ Ortak Domain: {d}")


# ── 4. Pipeline ile Çift Kaynak Testi ─────────────────────────
section("4. Pipeline.run() — Çift Kaynak Testi")

# Build sources: URLhaus CSV + OTX pulses
urlhaus_text = "\n".join(
    r[2] for r in csv.reader(l for l in open(URLHAUS_CSV) if not l.startswith("#"))
)

sources = [
    {
        "id": "urlhaus_bulk",
        "name": "URLhaus Threat Feed",
        "text": urlhaus_text[:50000],  # first 50K chars
        "value": 60,
    },
]

# Add OTX pulse sources
for p in pulses[:5]:
    sources.append(p.to_source_dict())

print(f"  Kaynak sayısı: {len(sources)}")
for s in sources:
    print(f"    [{s['id'][:16]}] {s['name'][:60]} (value={s.get('value', '?')})")

thresholds = {
    "c2_detection": {
        "enabled": True,
        "metric_key": "overall_confidence",
        "max": 0.4,
        "severity": "critical",
    },
    "attack_path_found": {
        "enabled": True,
        "metric_key": "attack_path_found",
        "max": 0,
        "severity": "high",
    },
}

pipeline = Pipeline()
result = pipeline.run(
    sources=sources,
    thresholds=thresholds,
    query_ip="",
    query_target="",
)

print(f"\n  Source texts:          {len(result.source_texts)}")
print(f"  Extracted entities:    {len(result.extracted_entities)}")

# Entity label distribution
label_counts = Counter(e.label for e in result.extracted_entities)
print("\n  Entity label dağılımı:")
for label, cnt in label_counts.most_common():
    print(f"    {label:12s}: {cnt}")

# Show DOMAIN entities
domains = [e for e in result.extracted_entities if e.label == "DOMAIN"]
filenames = [e for e in result.extracted_entities if e.label == "FILENAME"]
unknowns = [e for e in result.extracted_entities if e.label == "UNKNOWN"]
print(f"\n  DOMAIN:   {len(domains)}")
print(f"  FILENAME: {len(filenames)}")
print(f"  UNKNOWN:  {len(unknowns)}")

if domains:
    unique_domains = sorted({d.text for d in domains})
    print(f"  Benzersiz domain: {len(unique_domains)}")
    print(f"  Örnek: {unique_domains[:10]}")

print(f"\n  Contradictions:        {len(result.contradictions)}")
print(f"  Graph node sayısı:     {len(result.graph.nodes) if result.graph else 0}")
print(f"  Reasoning paths:       {len(result.reasoning_paths)}")
print(f"  Alerts:                {len(result.alerts)}")
print(f"  Incidents:             {len(result.incidents)}")
print(f"  Hata:                  {len(result.errors)}")

if result.errors:
    for err in result.errors:
        print(f"    ❌ {err[:200]}")


# ── 5. EntityMatcher Doğrulama ────────────────────────────────
section("5. EntityMatcher Birleştirme Doğrulaması")

if result.graph:
    print(f"  Toplam node: {len(result.graph.nodes)}")
    # Show nodes grouped by type
    node_types = Counter()
    for nid, node in result.graph.nodes.items():
        node_types[node.entity.__class__.__name__] += 1
    for nt, cnt in node_types.most_common():
        print(f"    {nt}: {cnt}")

    # Check evidence provenance on nodes
    multi_source_nodes = 0
    for nid, node in result.graph.nodes.items():
        sources_set = set()
        for ev in node.entity.evidence:
            for prov in ev.provenance:
                sources_set.add(prov.source_name)
        if len(sources_set) >= 2:
            multi_source_nodes += 1
            if multi_source_nodes <= 3:
                print(f"\n  Çok kaynaklı node: {nid}")
                print(f"    entity: {node.entity.__class__.__name__}")
                print(f"    evidence sayısı: {len(node.entity.evidence)}")
                print(f"    kaynaklar: {sources_set}")
                for ev in node.entity.evidence[:2]:
                    for prov in ev.provenance[:2]:
                        print(
                            f"      provenance: source={prov.source_name}, "
                            f"confidence={prov.confidence}, "
                            f"method={prov.collection_method}"
                        )

    print(f"\n  Çok kaynaklı node: {multi_source_nodes}")
    print("  (2+ farklı provenans kaynağına sahip node sayısı)")
    if multi_source_nodes == 0:
        print("  (beklenir: ortak IOC bulunamazsa 0 olabilir)")

    # Show chain stats
    if result.chain_stats:
        print("\n  Chain istatistikleri:")
        for k, v in result.chain_stats.items():
            print(f"    {k}: {v}")


# ── 6. NER FP Fix'inin OTX'te Doğrulanması ───────────────────
section("6. NER False-Positive Fix — OTX Verisinde Doğrulama")

ner = NEREngine()
otx_ner_stats: dict[str, int] = Counter()
otx_ner_examples: dict[str, list[str]] = {"DOMAIN": [], "FILENAME": [], "UNKNOWN": []}

# Run NER on all OTX pulse texts
for p in pulses[:10]:
    entities = ner.extract(p.to_source_dict()["text"])
    for e in entities:
        otx_ner_stats[e.label] += 1
        if e.label in otx_ner_examples and len(otx_ner_examples[e.label]) < 5:
            if e.text not in otx_ner_examples[e.label]:
                otx_ner_examples[e.label].append(e.text)

print("  OTX pulse'larında NER entity dağılımı:")
total_ner = sum(otx_ner_stats.values())
for label, cnt in otx_ner_stats.most_common():
    print(f"    {label:12s}: {cnt} ({cnt / total_ner * 100:.1f}%)")

print("\n  Örnekler:")
for label, examples in otx_ner_examples.items():
    if examples:
        print(f"    {label}:")
        for ex in examples[:5]:
            print(f"      • '{ex}'")

# Specifically test: are filenames in OTX data correctly classified?
print("\n  FILENAME kontrolü (beklenen: .zip, .exe, .sh gibi uzantılar FILENAME):")
test_filename_patterns = [
    "sample.exe",
    "malware.zip",
    "script.sh",
    "payload.dll",
    "document.pdf",
    "data.csv",
    "config.xml",
    "image.png",
    "installer.msi",
    "virus.bat",
]
for fp in test_filename_patterns:
    entities = ner.extract(fp)
    found = [e for e in entities if e.text == fp]
    label = found[0].label if found else "NOT_MATCHED"
    status = "✓" if label == "FILENAME" else "✗"
    print(f"    {status} '{fp}' → {label}")

# Test real domains still work
print("\n  DOMAIN kontrolü (beklenen: geçerli TLD'ler DOMAIN):")
test_domain_patterns = [
    "evil.example.com",
    "malware.xyz",
    "c2.badguys.org",
    "pastebin.com",
    "github.com",
    "telegram.org",
]
for td in test_domain_patterns:
    entities = ner.extract(td)
    found = [e for e in entities if e.text == td]
    label = found[0].label if found else "NOT_MATCHED"
    status = "✓" if label == "DOMAIN" else "✗"
    print(f"    {status} '{td}' → {label}")


# ── 7. Özet ───────────────────────────────────────────────────
section("7. SONUÇ ÖZETİ")

print(f"""
OTX API:
  Pulse sayısı:            {len(pulses)}
  Toplam IOC:              {total_otx_iocs}
  IOC tipleri:             {[k for k, v in all_otx_iocs.items() if v]}

URLhaus:
  Toplam IOC:              {total_urlhaus}

Çapraz Kaynak:
  Ortak domain:            {len(domain_overlap)}
  Ortak IP:                {len(ip_overlap)}
  Toplam eşleşme:          {len(ip_overlap) + len(domain_overlap)}

Pipeline:
  Kaynak sayısı:           {len(sources)}
  Entity sayısı:           {len(result.extracted_entities)}
  DOMAIN:                  {len(domains)}
  FILENAME:                {len(filenames)}
  UNKNOWN:                 {len(unknowns)}
  Graph node:              {len(result.graph.nodes) if result.graph else 0}
  Alert:                   {len(result.alerts)}
  Incident:                {len(result.incidents)}
  Hata:                    {len(result.errors)}

NER FP Fix (OTX):
  OTX NER entity:          {total_ner}
  DOMAIN/FILENAME/UNKNOWN: {otx_ner_stats.get("DOMAIN", 0)}/{otx_ner_stats.get("FILENAME", 0)}/{otx_ner_stats.get("UNKNOWN", 0)}
""")

# Save full result
with open(OUT_DIR / "phase6_result.json", "w") as f:
    json.dump(
        {
            "otx_pulses": len(pulses),
            "otx_iocs": total_otx_iocs,
            "urlhaus_iocs": total_urlhaus,
            "common_domains": len(domain_overlap),
            "common_ips": len(ip_overlap),
            "pipeline_entities": len(result.extracted_entities),
            "pipeline_domains": len(domains),
            "pipeline_filenames": len(filenames),
            "pipeline_unknowns": len(unknowns),
            "pipeline_nodes": len(result.graph.nodes) if result.graph else 0,
            "pipeline_alerts": len(result.alerts),
            "pipeline_incidents": len(result.incidents),
            "pipeline_errors": len(result.errors),
            "ner_fp_otx_domains": otx_ner_stats.get("DOMAIN", 0),
            "ner_fp_otx_filenames": otx_ner_stats.get("FILENAME", 0),
            "ner_fp_otx_unknowns": otx_ner_stats.get("UNKNOWN", 0),
        },
        f,
        indent=2,
    )
print(f"  Sonuç kaydedildi: {OUT_DIR / 'phase6_result.json'}")

pipeline.cleanup()
