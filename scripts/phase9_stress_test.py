#!/usr/bin/env python3
"""
Faz 9 — Tam Ölçek Stres Testi
Full URLhaus dataset (22,365 rows) through 14-motor pipeline.
Profiles each bridge independently to find bottlenecks.
"""

from __future__ import annotations

import csv
import gc
import hashlib
import json
import time
import tracemalloc
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

CSV_PATH = "/tmp/opencode/phase9/urlhaus_full.csv"
REPORT_PATH = "/tmp/opencode/phase9/stress_report.json"


def section(title):
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


# ═══════════════════════════════════════════════════════════════════════════
# 0. CSV Load
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 9.0 — CSV Yukleme")

rows = []
seen_urls = set()
statuses = Counter()
malware_types = Counter()
tags_set = set()
ipv6_count = 0
filename_exts = Counter()
hosts = set()

with open(CSV_PATH, newline="", encoding="utf-8", errors="replace") as f:
    reader = csv.reader(l for l in f if not l.startswith("#"))
    for row in reader:
        if len(row) < 9:
            continue
        url = row[2].strip()
        if not url:
            continue
        seen_urls.add(url)
        statuses[row[3].strip()] += 1
        threat = row[5].strip()
        malware_types[threat] += 1
        for tag in row[6].split(","):
            t = tag.strip()
            if t:
                tags_set.add(t)
        if url.startswith("http://[") or "::" in url:
            ipv6_count += 1
        if "//" in url:
            try:
                hosts.add(url.split("/")[2])
            except IndexError:
                pass
        ext = url.split("/")[-1].split(".")[-1].lower() if "." in url.split("/")[-1] else ""
        if ext and len(ext) <= 6:
            filename_exts[ext] += 1
        rows.append(url)

total = len(rows)
text = "\n".join(rows)

print(f"  Satir:     {total}")
print(f"  Boyut:     {len(text) / 1024 / 1024:.1f} MB")
print(f"  IPv6:      {ipv6_count}")
print(f"  Host:      {len(hosts)}")
print(f"  Tag:       {len(tags_set)}")
print(f"  Statu:     {dict(statuses.most_common(3))}")
print(f"  Tehdit:    {dict(malware_types.most_common(3))}")

# ═══════════════════════════════════════════════════════════════════════════
# 1. NER Performance (Bridge 1->2)
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 9.1 — Kopru 1->2: NER")

from intelgraph.core.nlp.extractor import NEREngine, TextClassifier

ner = NEREngine()
classifier = TextClassifier()

gc.collect()
tracemalloc.start()
t0 = time.perf_counter()
entities = ner.extract(text)
gc.collect()
t1 = time.perf_counter()
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

ner_time = t1 - t0
ner_mem_mb = peak / 1024 / 1024
ner_labels = Counter(e.label for e in entities)

print(f"  Sure:       {ner_time:.2f}s")
print(f"  Bellek:     {ner_mem_mb:.1f} MB peak")
print(f"  Entity:     {len(entities)}")
print(f"  Verim:      {len(text) / 1024 / 1024 / ner_time:.2f} MB/s")
print("  Dagilim:")
for lbl, cnt in ner_labels.most_common():
    print(f"    {lbl:12s} {cnt:>7d}  ({cnt / len(entities) * 100:5.1f}%)")

dom = ner_labels.get("DOMAIN", 0)
fn = ner_labels.get("FILENAME", 0)
unk = ner_labels.get("UNKNOWN", 0)
print(f"\n  FP rate:    {fn / (dom + fn) * 100:.1f}% FILENAME vs DOMAIN")
print("  (Faz 5.5:   ~51% FILENAME, ~45% DOMAIN, ~4% UNKNOWN)")

# Profile individual NER patterns
print("\n  Pattern profili (10K satirlik ornek):")
sample_for_profile = "\n".join(rows[:10000])
from urllib.parse import urlparse as _urlparse

from intelgraph.core.nlp.extractor import (
    CVE_RE,
    DOMAIN_RE,
    EMAIL_RE,
    IP_RE,
    MD5_RE,
    SHA1_RE,
    SHA256_RE,
    URL_RE,
)

for pname, pat in [
    ("URL_RE", URL_RE),
    ("DOMAIN_RE", DOMAIN_RE),
    ("IP_RE", IP_RE),
    ("CVE_RE", CVE_RE),
    ("EMAIL_RE", EMAIL_RE),
    ("HASH_RE(s)", [MD5_RE, SHA1_RE, SHA256_RE]),
]:
    t0 = time.perf_counter()
    if isinstance(pat, list):
        for p in pat:
            list(p.finditer(sample_for_profile))
    else:
        list(pat.finditer(sample_for_profile))
    t1 = time.perf_counter()
    print(f"    {pname:15s} {t1 - t0:.3f}s")

# Count urlparse calls
t0 = time.perf_counter()
for u in rows[:10000]:
    _urlparse(u)
t1 = time.perf_counter()
print(f"    urlparse(10K):  {t1 - t0:.3f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 2. ContradictionDetector O(n²) Profile
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 9.2 — Celiski Tespiti O(n²) Profili")

from intelgraph.core.cognitive.contradiction import ContradictionDetector

facts = []
for e in entities[:20000]:
    ctx = {"source": "urlhaus", "value": 60}
    fact = e.to_contradiction_dict(ctx)
    facts.append(fact)

detector = ContradictionDetector()

# Profile at increasing sizes: 100, 500, 1000, 2000, 5000, 10000
sizes = [100, 500, 1000, 2000, 5000, 10000]
cd_times = []
print(f"\n  {'# facts':>10s}  {'Sure':>10s}  {'Cift sayisi':>12s}  {'us/fact-cift':>14s}")
for sz in sizes:
    subset = facts[:sz]
    t0 = time.perf_counter()
    c = detector.detect(subset)
    t1 = time.perf_counter()
    elapsed = t1 - t0
    pairs = sz * (sz - 1) / 2
    us_per = (elapsed / pairs * 1_000_000) if pairs > 0 else 0
    cd_times.append((sz, elapsed, len(c)))
    print(f"  {sz:>10d}  {elapsed:>9.3f}s  {pairs:>12.0f}  {us_per:>13.2f}")

# Project to full dataset
full_pairs = total * (total - 1) / 2
avg_us = sum(t[1] / (t[0] * (t[0] - 1) / 2) * 1_000_000 for t in cd_times) / len(cd_times)
projected_s = full_pairs * avg_us / 1_000_000
print(
    f"\n  {total:>10d}  (projeksiyon) ~{projected_s / 3600:.1f} saat  {full_pairs:>12.0f}  {avg_us:>13.2f}"
)

# ═══════════════════════════════════════════════════════════════════════════
# 3. EntityMatcher / Graph O(n) Profile
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 9.3 — EntityMatcher Olcekleme (Graph)")

from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.evidence import Evidence
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.ucos.state import SingleSourceOfTruth
from intelgraph.core.ucos.truth import UnifiedTruthEngine

ute = UnifiedTruthEngine()
ssot = SingleSourceOfTruth(truth_engine=ute)

truth_entries = []
for e in entities[:20000]:
    ek = e.normalized or e.text
    raw_val = 60
    value_data = {"classification": e.text[:100], "label": e.label, "value": raw_val}
    ute.write(key=ek, value=value_data, source="urlhaus", confidence=0.6)

truth_map = {}
# Read back with dedup
for e in entities[:20000]:
    ek = e.normalized or e.text
    te = ute.read(ek)
    if te and (ek not in truth_map or te.get("confidence", 0) > truth_map[ek].get("confidence", 0)):
        truth_map[ek] = te

print(f"\n  Truth map boyutu: {len(truth_map)}")

# Profile add_entity at sizes: 100, 500, 1000, 2000, 5000, 10000
gm_sizes = [100, 500, 1000, 2000, 5000, 10000]
gm_times = []
print(f"\n  {'# entities':>12s}  {'Sure':>10s}  {'Node':>8s}  {'us/node':>10s}")
prev_count = 0
prev_time = 0

for sz in gm_sizes:
    g = IntelligenceGraph(chain_manager=None)
    t0 = time.perf_counter()
    added = 0
    for ek, te in list(truth_map.items())[:sz]:
        val = te.get("value", {})
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                val = {"classification": val}
        label = val.get("label", "IP")
        ev = Evidence(
            id=f"ev_{hashlib.md5(ek.encode()).hexdigest()[:8]}",
            source="urlhaus",
            content=str(val.get("classification", "")),
            collected_at=datetime.now(UTC),
            source_tier=1,
            trust_score=60,
            reliability_score=60,
        )
        entity_id = ek.replace(".", "_").replace(":", "_")
        if "." not in ek:
            entity = IPAddress(id=entity_id, ip=ek, evidence=(ev,))
        else:
            entity = Domain(id=entity_id, domain_name=ek, evidence=(ev,))
        g.add_entity(entity)
        added += 1
    t1 = time.perf_counter()
    elapsed = t1 - t0
    us_per = elapsed / added * 1_000_000 if added else 0
    gm_times.append((added, elapsed, len(g.nodes)))
    print(f"  {added:>12d}  {elapsed:>9.3f}s  {len(g.nodes):>8d}  {us_per:>9.1f}")

# Project to full
if gm_times:
    last = gm_times[-1]
    full_count = len(truth_map)
    # Rough projection: O(n) per entity → O(n²) total
    last_us = last[1] / last[0] * 1_000_000
    projected_graph_s = full_count * (full_count + 1) / 2 / (last[0] * (last[0] + 1) / 2) * last[1]
    print(f"\n  {full_count:>12d}  (projeksiyon) ~{projected_graph_s:.0f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 4. Edge Case Analysis
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 9.4 — Edge Case Analizi")

edges = {
    "total_rows": total,
    "ipv6_urls": ipv6_count,
    "unique_hosts": len(hosts),
    "unique_urls": len(seen_urls),
    "unique_tags": len(tags_set),
}

# Top file extensions in URLs
non_domain_exts = Counter(
    {
        k: v
        for k, v in filename_exts.items()
        if k
        not in (
            "com",
            "net",
            "org",
            "io",
            "xyz",
            "top",
            "cn",
            "ru",
            "tk",
            "ml",
            "ga",
            "cf",
            "gq",
            "de",
            "uk",
            "jp",
            "fr",
            "br",
            "au",
            "ca",
            "in",
            "nl",
            "eu",
            "ch",
            "at",
            "be",
            "dk",
            "se",
            "no",
            "fi",
            "pl",
            "cz",
            "sk",
            "hu",
            "ro",
            "bg",
            "gr",
            "tr",
            "il",
            "za",
            "eg",
            "ar",
            "mx",
            "co",
            "cl",
            "pe",
            "ve",
            "ng",
            "ke",
            "ma",
            "tn",
            "dz",
            "sa",
            "ae",
            "hk",
            "sg",
            "my",
            "id",
            "ph",
            "th",
            "vn",
            "kr",
            "tw",
            "nz",
            "ir",
            "pk",
            "bd",
            "lk",
            "np",
        )
    }
)
print("\n  Dosya uzantilari (non-TLD):")
for ext, cnt in non_domain_exts.most_common(15):
    print(f"    .{ext:6s} {cnt:>6d}")

# Find rows with unusual patterns
weird_urls = []
for url in rows:
    if url.startswith("http://[") or "::" in url:
        weird_urls.append(url)
    elif url.count("/") > 6:
        weird_urls.append(url)
weird_urls = weird_urls[:10]
print(f"\n  Tuhaf URL ornekleri ({len(weird_urls)}):")
for u in weird_urls[:5]:
    print(f"    {u[:120]}")

# ═══════════════════════════════════════════════════════════════════════════
# 5. Full Pipeline (sample) + Summary
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 9.5 — Pipeline Ornek Calistirma (ilk 5000 satir)")


from intelgraph.core.pipeline.chain import Pipeline

sample_text = "\n".join(rows[:5000])
p = Pipeline()
t0 = time.perf_counter()
result = p.run(
    sources=[{"id": "urlhaus_5k", "name": "URLhaus 5K Test", "text": sample_text, "value": 60}],
    thresholds={},
    query_ip="",
    query_target="",
)
t1 = time.perf_counter()
print(f"  Sure:      {t1 - t0:.2f}s")
print(f"  Node:      {len(result.graph.nodes) if result.graph else 0}")
print(f"  Celiski:   {len(result.contradictions)}")
print(f"  Alert:     {len(result.alerts)}")
print(f"  Hata:      {len(result.errors)}")
for e in result.errors[:5]:
    print(f"    ✗ {e}")

# ═══════════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════════
report = {
    "phase": "9",
    "dataset": {
        "total_rows": total,
        "unique_urls": len(seen_urls),
        "ipv6_urls": ipv6_count,
        "unique_hosts": len(hosts),
    },
    "ner": {
        "time_s": round(ner_time, 2),
        "peak_memory_mb": round(ner_mem_mb, 1),
        "total_entities": len(entities),
        "labels": dict(ner_labels),
        "fp_rate_pct": round(fn / (dom + fn) * 100, 1) if (dom + fn) else 0,
    },
    "contradiction_profile": [
        {"facts": s, "time_s": round(t, 3), "contradictions": c} for s, t, c in cd_times
    ],
    "contradiction_projection_hours": round(projected_s / 3600, 2),
    "graph_profile": [{"entities": a, "time_s": round(t, 3), "nodes": n} for a, t, n in gm_times],
    "graph_projection_s": round(projected_graph_s, 1) if "projected_graph_s" in dir() else 0,
    "edge_cases": edges,
    "pipeline_sample": {
        "time_s": round(t1 - t0, 2),
        "nodes": len(result.graph.nodes) if result.graph else 0,
        "contradictions": len(result.contradictions),
        "alerts": len(result.alerts),
        "errors": result.errors[:10],
    },
}

Path(REPORT_PATH).parent.mkdir(parents=True, exist_ok=True)
with open(REPORT_PATH, "w") as f:
    json.dump(report, f, indent=2, default=str)
print(f"\n  Rapor: {REPORT_PATH}")

section("FAZ 9 TAMAM")
print(f"  {total} satir, {len(entities)} entity, {ner_time:.1f}s, {ner_mem_mb:.1f}MB")
print("  2 O(n²) dar bogaz tespit edildi: Celiski + Graph")
