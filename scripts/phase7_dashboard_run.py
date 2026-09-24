# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Phase 7 — Backend-connected Dashboard

1. Pipeline'i URLhaus + OTX ile çalıştır
2. DashboardState'e veriyi yükle
3. FastAPI/Uvicorn ile dashboard'u serve et
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

import uvicorn

os.environ["OTX_API_KEY"] = "bc74aac50ae436dee05bfae89647406f73eed2cf947939f9d3e25461954ea12f"

from intelgraph.api.routers.dashboard import dashboard_state
from intelgraph.core.pipeline.chain import Pipeline
from intelgraph.core.source.otx import OtxClient

URLHAUS_CSV = "/tmp/urlhaus_recent.csv"
if not Path(URLHAUS_CSV).exists():
    sys.exit("URLhaus CSV not found. Run Phase 5 first.")

print("=" * 60)
print("PHASE 7 — Feeding dashboard with real pipeline data")
print("=" * 60)

# ── 1. Fetch OTX pulses ──
print("\nFetching OTX pulses...")
client = OtxClient()
pulses = client.get_pulses(page=1, limit=5)
otx_all = client.extract_iocs(pulses)
total_otx = sum(len(v) for v in otx_all.values())
print(f"  {len(pulses)} pulses, {total_otx} IOCs")

# ── 2. Load URLhaus sample ──
with open(URLHAUS_CSV) as f:
    reader = csv.reader(l for l in f if not l.startswith("#"))
    urlhaus_rows = [r[2] for i, r in enumerate(reader) if i < 50]
urlhaus_text = "\n".join(urlhaus_rows)
print(f"  URLhaus: {len(urlhaus_rows)} entries")

# ── 3. Build sources ──
sources = [
    {"id": "urlhaus_50", "name": "URLhaus (50)", "text": urlhaus_text, "value": 60},
]
for p in pulses:
    sources.append(p.to_source_dict())

# ── 4. Run pipeline ──
print("\nRunning pipeline...")
sys.stdout.flush()
t0 = time.time()

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
result = pipeline.run(sources=sources, thresholds=thresholds)
elapsed = time.time() - t0
print(f"  Pipeline completed in {elapsed:.1f}s")

# ── 5. Feed dashboard state ──
result_dict = result.to_dict()
result_dict["source_texts"] = result.source_texts
dashboard_state.feed(result_dict)

# Feed source info
dashboard_state.feed_sources(
    {
        "URLhaus": {"iocs": len(urlhaus_rows), "entities": len(result.extracted_entities)},
        "OTX": {"iocs": total_otx, "pulses": len(pulses)},
    }
)

# Feed NER stats
from collections import Counter

ner_labels = Counter(e.label for e in result.extracted_entities)
ner_samples: dict[str, list[str]] = {"DOMAIN": [], "FILENAME": [], "UNKNOWN": []}
seen: dict[str, set[str]] = {k: set() for k in ner_samples}
for e in result.extracted_entities:
    if e.label in seen and e.text not in seen[e.label]:
        seen[e.label].add(e.text)
        if len(ner_samples[e.label]) < 10:
            ner_samples[e.label].append(e.text)
dashboard_state.feed_ner(dict(ner_labels), ner_samples)

pipeline.cleanup()

print(f"\n{'=' * 60}")
print("Dashboard state populated:")
print(f"  Entities:  {len(result.extracted_entities)}")
print(f"  DOMAIN:    {ner_labels.get('DOMAIN', 0)}")
print(f"  FILENAME:  {ner_labels.get('FILENAME', 0)}")
print(f"  UNKNOWN:   {ner_labels.get('UNKNOWN', 0)}")
print(f"  Nodes:     {len(result.graph.nodes) if result.graph else 0}")
print(f"  Alerts:    {len(result.alerts)}")
print(f"  Incidents: {len(result.incidents)}")
print(f"  Errors:    {len(result.errors)}")
print(f"{'=' * 60}")

# ── 6. Save result JSON ──
out = Path("/tmp/opencode/phase7")
out.mkdir(parents=True, exist_ok=True)
with open(out / "pipeline_result.json", "w") as f:
    json.dump(
        {
            "sources": len(sources),
            "entities": len(result.extracted_entities),
            "domains": ner_labels.get("DOMAIN", 0),
            "filenames": ner_labels.get("FILENAME", 0),
            "unknowns": ner_labels.get("UNKNOWN", 0),
            "graph_nodes": len(result.graph.nodes) if result.graph else 0,
            "alerts": len(result.alerts),
            "incidents": len(result.incidents),
            "errors": len(result.errors),
            "elapsed_seconds": round(elapsed, 1),
        },
        f,
        indent=2,
    )

# ── 7. Start server ──
print("\nStarting dashboard server...")
print("  Open: http://127.0.0.1:8111")
print("  API:  http://127.0.0.1:8111/dashboard/summary")
print("  Stop: Ctrl+C\n")

uvicorn.run(
    "intelgraph.api.main:create_app",
    host="127.0.0.1",
    port=8111,
    factory=True,
    log_level="info",
)
