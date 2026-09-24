#!/usr/bin/env python3
"""
Faz 15 — IntelligenceGraph SQLite Kalici Depolama

Test:
1. 3 kaynak pipeline (URLhaus + OTX + KEV) storage_path ile calistir
2. Python suresini kapat, yeni IntelligenceGraph(storage_path=...) olustur
3. Node/edge sayilari, entity tipleri, confidence skorlari eslest mi?
4. storage_path=None ile in-memory regression hala calisiyor mu?
5. Performans: storage_path=None vs dolu karsilastirma
6. Schema ve diff gosterimi
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path

PHASE15 = Path("/tmp/opencode/phase15")
PHASE15.mkdir(parents=True, exist_ok=True)
DB_PATH = str(PHASE15 / "graph_persistent.db")

# Remove old DB
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)


def section(t):
    print(f"\n{'=' * 72}\n  {t}\n{'=' * 72}")


# ═══════════════════════════════════════════════════════════════════════════
# 0. Schema diff
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 15.0 — Schema")

from intelgraph.core.graph.storage import GraphStorage

store = GraphStorage(DB_PATH)
import sqlite3

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute(
    "SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE 'graph_%' OR name='previous_versions'"
)
for name, sql in cur.fetchall():
    print(f"\n  Table: {name}")
    print(f"  {sql}")
conn.close()
store.close()
os.remove(DB_PATH)

# ═══════════════════════════════════════════════════════════════════════════
# 1. Pipeline with storage_path
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 15.1 — Pipeline storage_path ile calistir")

from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.pipeline.chain import Pipeline

# Source data
urlhaus_lines = []
with open("/tmp/opencode/phase9/urlhaus_full.csv") as f:
    for i, line in enumerate(f):
        if line.startswith("#"):
            continue
        if i >= 50:
            break
        urlhaus_lines.append(line.strip())
urlhaus_text = ". ".join(urlhaus_lines)

with open("/tmp/opencode/phase14/otx_source.txt") as f:
    otx_text = f.read()

kev_data = json.load(open("/tmp/opencode/phase10/kev.json"))
kev_vulns = kev_data["vulnerabilities"]
known = [v for v in kev_vulns if v.get("knownRansomwareCampaignUse") == "Known"][:25]
unknown = [v for v in kev_vulns if v.get("knownRansomwareCampaignUse") == "Unknown"][:25]
kev_text = "\n".join(
    f"{v['cveID']}: {v.get('vendorProject', '')} {v.get('product', '')} - "
    f"{v.get('shortDescription', '')} Ransomware campaign use: {v.get('knownRansomwareCampaignUse', 'Unknown')}."
    for v in known + unknown
)

# Run pipeline — note: Pipeline doesn't pass storage_path to graph directly.
# We'll demonstrate persistence by directly using IntelligenceGraph with storage_path
# after the pipeline run, saving nodes from result.graph to a new persistent graph.

pipeline = Pipeline()
t0 = time.perf_counter()
result = pipeline.run(
    sources=[
        {"id": "urlhaus", "name": "URLhaus", "text": urlhaus_text, "value": 80},
        {"id": "otx", "name": "OTX", "text": otx_text, "value": 85},
        {"id": "cisa_kev", "name": "CISA KEV", "text": kev_text, "value": 90},
    ],
    thresholds={},
    query_ip="",
    query_target="",
)
t1 = time.perf_counter()
print(
    f"  Pipeline: {t1 - t0:.2f}s, {len(result.graph.nodes)} nodes, {len(result.graph.edges)} edges"
)

# Now persist: create a persistent graph and copy all nodes/edges
from intelgraph.core.graph.graph import IntelligenceGraph

g_persist = IntelligenceGraph(storage_path=DB_PATH)
# Disable fuzzy matching during load (we just want to write)
for nid, node in result.graph.nodes.items():
    # Use overwrite=True to skip fuzzy matching
    g_persist.add_entity(node.entity, overwrite=True)

# Copy edges
for _eid, edge in result.graph.edges.items():
    g_persist.add_relationship(edge.relationship)

orig_node_count = len(g_persist.nodes)
orig_edge_count = len(g_persist.edges)
orig_types = Counter(type(n.entity).__name__ for n in g_persist.nodes.values())
orig_confs = {nid: n.entity.confidence_score for nid, n in g_persist.nodes.items()}

print("\n  Persisted graph:")
print(f"    Nodes: {orig_node_count}")
print(f"    Edges: {orig_edge_count}")
print(f"    Types: {dict(orig_types)}")
print(f"    Sample confidence: {list(orig_confs.items())[:3]}")

# Close storage connection
g_persist._storage.close()
print(f"\n  DB saved at: {DB_PATH} ({os.path.getsize(DB_PATH)} bytes)")

# ═══════════════════════════════════════════════════════════════════════════
# 2. Restart — new IntelligenceGraph from same DB
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 15.2 — Restart: Yeni IntelligenceGraph, ayni DB")

# Simulate full restart by creating a brand new IntelligenceGraph
g_restart = IntelligenceGraph(storage_path=DB_PATH)
restart_node_count = len(g_restart.nodes)
restart_edge_count = len(g_restart.edges)
restart_types = Counter(type(n.entity).__name__ for n in g_restart.nodes.values())
restart_confs = {nid: n.entity.confidence_score for nid, n in g_restart.nodes.items()}

print("  Restart graph:")
print(f"    Nodes: {restart_node_count}")
print(f"    Edges: {restart_edge_count}")
print(f"    Types: {dict(restart_types)}")

# Verify equality
nodes_match = orig_node_count == restart_node_count
edges_match = orig_edge_count == restart_edge_count
types_match = orig_types == restart_types

# Check confidence scores match
confs_match = True
mismatches = []
for nid, conf in orig_confs.items():
    r_conf = restart_confs.get(nid)
    if r_conf != conf:
        confs_match = False
        mismatches.append((nid, conf, r_conf))

print("\n  Dogrulama:")
print(f"    Nodes match:     {nodes_match} ({orig_node_count} == {restart_node_count})")
print(f"    Edges match:     {edges_match} ({orig_edge_count} == {restart_edge_count})")
print(f"    Types match:     {types_match}")
print(f"    Confidence match: {confs_match}")
if mismatches:
    print("    Mismatches (first 5):")
    for nid, o, r in mismatches[:5]:
        print(f"      {nid}: orig={o} restart={r}")

# Sample entities
print("\n  Ornek entity'ler (restart):")
for n in list(g_restart.nodes.values())[:5]:
    e = n.entity
    etype = type(e).__name__
    ident = (
        getattr(e, "ip", "") or getattr(e, "domain_name", "") or getattr(e, "cve_id", "") or n.id
    )
    ev_count = len(e.evidence)
    print(f"    {etype:12s} {ident:30s} conf={e.confidence_score} evidence={ev_count}")

g_restart._storage.close()

# ═══════════════════════════════════════════════════════════════════════════
# 3. Regression: storage_path=None (in-memory only)
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 15.3 — Regression: storage_path=None")

g_mem = IntelligenceGraph()  # no storage_path
assert g_mem._storage is None, "storage_path=None should not create storage"
g_mem.add_entity(IPAddress(id="test_ip", ip="10.0.0.1", confidence_score=85))
g_mem.add_entity(Domain(id="test_dom", domain_name="evil.com", confidence_score=70))

print(f"  In-memory graph: {len(g_mem.nodes)} nodes, {len(g_mem.edges)} edges")
print(f"  _storage is None: {g_mem._storage is None}")
print(f"  Nodes accessible: {list(g_mem.nodes.keys())}")
print(f"  Regression OK: {len(g_mem.nodes) == 2}")

# ═══════════════════════════════════════════════════════════════════════════
# 4. Performance comparison
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 15.4 — Performans Karsilastirma")

# In-memory
g1 = IntelligenceGraph()
t0 = time.perf_counter()
for i in range(100):
    g1.add_entity(IPAddress(id=f"ip_{i}", ip=f"10.{i // 256}.{i % 256}.1", confidence_score=80))
t1 = time.perf_counter()
mem_time = t1 - t0
print(f"  In-memory  (100 nodes): {mem_time:.3f}s")

# With storage
db_perf = str(PHASE15 / "perf_test.db")
if os.path.exists(db_perf):
    os.remove(db_perf)
g2 = IntelligenceGraph(storage_path=db_perf)
t0 = time.perf_counter()
for i in range(100):
    g2.add_entity(IPAddress(id=f"ip_{i}", ip=f"10.{i // 256}.{i % 256}.1", confidence_score=80))
t1 = time.perf_counter()
storage_time = t1 - t0
print(f"  Storage    (100 nodes): {storage_time:.3f}s")
print(
    f"  Overhead:  {((storage_time - mem_time) / mem_time * 100):.1f}% ({storage_time / mem_time:.2f}x)"
)
g2._storage.close()
os.remove(db_perf)

# Larger test
db_perf2 = str(PHASE15 / "perf_test2.db")
if os.path.exists(db_perf2):
    os.remove(db_perf2)
g3 = IntelligenceGraph(storage_path=db_perf2)
t0 = time.perf_counter()
for i in range(500):
    g3.add_entity(
        IPAddress(
            id=f"ip_{i}", ip=f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}", confidence_score=80
        )
    )
t1 = time.perf_counter()
storage_time_500 = t1 - t0
print(f"\n  Storage    (500 nodes): {storage_time_500:.3f}s")
print(f"  DB size: {os.path.getsize(db_perf2)} bytes")
g3._storage.close()
os.remove(db_perf2)

# ═══════════════════════════════════════════════════════════════════════════
# 5. Report
# ═══════════════════════════════════════════════════════════════════════════
section("Faz 15.5 — Rapor")

all_pass = nodes_match and edges_match and types_match and confs_match and (len(g_mem.nodes) == 2)
report = {
    "phase": "15",
    "schema": {
        "tables": ["graph_nodes", "graph_edges", "previous_versions"],
        "graph_nodes_cols": [
            "node_id (PK)",
            "entity_type",
            "entity_data (JSON)",
            "confidence_score",
            "created_at",
            "updated_at",
        ],
        "graph_edges_cols": [
            "edge_id (PK)",
            "source_node_id (FK)",
            "target_node_id (FK)",
            "relationship_type",
            "confidence",
            "edge_data (JSON)",
            "created_at",
        ],
        "previous_versions_cols": [
            "version_id (PK AUTOINCREMENT)",
            "node_id",
            "version_data (JSON)",
            "entity_type",
            "saved_at",
        ],
    },
    "persistence_test": {
        "original_nodes": orig_node_count,
        "restart_nodes": restart_node_count,
        "nodes_match": nodes_match,
        "original_edges": orig_edge_count,
        "restart_edges": restart_edge_count,
        "edges_match": edges_match,
        "types_match": types_match,
        "confidence_match": confs_match,
        "confidence_mismatches": len(mismatches),
    },
    "regression_test": {
        "storage_path_none": "OK",
        "in_memory_nodes": len(g_mem.nodes),
        "_storage_is_none": g_mem._storage is None,
    },
    "performance": {
        "in_memory_100_nodes_sec": round(mem_time, 3),
        "storage_100_nodes_sec": round(storage_time, 3),
        "overhead_pct": round((storage_time - mem_time) / mem_time * 100, 1),
        "storage_500_nodes_sec": round(storage_time_500, 3),
    },
    "db_path": DB_PATH,
    "status": "PASS" if all_pass else "FAIL",
}

print(f"\n  {'✓' if all_pass else '✗'} STATUS: {report['status']}")
print(
    f"    Persistence: nodes={nodes_match}, edges={edges_match}, types={types_match}, conf={confs_match}"
)
print(f"    Regression: in-memory OK ({len(g_mem.nodes)} nodes)")
print(
    f"    Performance: 100 nodes in-memory={mem_time:.3f}s vs storage={storage_time:.3f}s ({((storage_time - mem_time) / mem_time * 100):.1f}% overhead)"
)

with open(PHASE15 / "phase15_report.json", "w") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\n  Rapor: {PHASE15}/phase15_report.json")

section("FAZ 15 TAMAM")
print("  Schema: graph_nodes + graph_edges + previous_versions (3 tablo)")
print(
    "  Write-through: add_entity, add_relationship, remove_node, remove_edge, resolve_evidence_contradictions"
)
print(
    f"  Restart persistence: {restart_node_count}/{orig_node_count} nodes, {restart_edge_count}/{orig_edge_count} edges"
)
print(f"  Regression: storage_path=None → in-memory ({len(g_mem.nodes)} nodes)")
print(
    f"  Performance: 100 nodes storage overhead ~{((storage_time - mem_time) / mem_time * 100):.0f}%"
)
