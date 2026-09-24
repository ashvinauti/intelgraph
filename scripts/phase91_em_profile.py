#!/usr/bin/env python3
"""EntityMatcher growth curve profiling — no code changes, just measurement."""

import hashlib
import time
from datetime import UTC, datetime

from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.evidence import Evidence
from intelgraph.core.graph.graph import IntelligenceGraph


# Generate synthetic entities at increasing scales
def make_ip(ip_str):
    ev = Evidence(
        id=f"ev_{hashlib.md5(ip_str.encode()).hexdigest()[:8]}",
        source="test",
        content="malicious IP",
        collected_at=datetime.now(UTC),
        source_tier=1,
        trust_score=50,
        reliability_score=50,
    )
    return IPAddress(id=ip_str.replace(".", "_"), ip=ip_str, evidence=(ev,))


def make_domain(domain_str):
    ev = Evidence(
        id=f"ev_{hashlib.md5(domain_str.encode()).hexdigest()[:8]}",
        source="test",
        content="malicious domain",
        collected_at=datetime.now(UTC),
        source_tier=1,
        trust_score=50,
        reliability_score=50,
    )
    return Domain(id=domain_str.replace(".", "_"), domain_name=domain_str, evidence=(ev,))


sizes = [100, 500, 1000, 2000, 5000, 10000, 20000, 50000]
print(f"{'# entities':>12s}  {'Sure':>10s}  {'Node':>8s}  {'us/entity':>10s}  {'proj 100K':>10s}")
for sz in sizes:
    g = IntelligenceGraph(chain_manager=None)
    t0 = time.perf_counter()
    for i in range(sz):
        if i % 2 == 0:
            e = make_ip(f"10.0.{i >> 8}.{i & 255}")
        else:
            e = make_domain(f"malware{i}.example.com")
        g.add_entity(e)
    t1 = time.perf_counter()
    elapsed = t1 - t0
    us_per = elapsed / sz * 1_000_000
    proj_100k = us_per * 100_000 / 1_000_000  # seconds for 100K
    print(f"{sz:>12d}  {elapsed:>9.3f}s  {len(g.nodes):>8d}  {us_per:>9.1f}  {proj_100k:>9.0f}s")

# Threshold estimate
print("\nEslik analizi:")
print("  10K:  6ms/entity → 60s total")
print("  50K:  ~30ms/entity → ~1500s (25 dk)")
print("  100K: ~60ms/entity → ~6000s (1.7 saat) -- KIRILMA NOKTASI")
print("\nKanaat: 100K entity'de EntityMatcher optimizasyonu ZORUNLU.")
print(
    "        Hash-based pre-filter (gruplama) oncesinde kabul edilebilir ust sinir: ~20K-30K entity."
)
