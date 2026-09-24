# LIMITATIONS.md — Known Limitations

## NER (extractor.py)
- **No contextual understanding**: NER is regex-based only, with linguistic/semantic analysis. Example: "Server 10.0.0.1" vs "Struts 10.0.4.2" are disambiguated only via context keywords.
- **No IPv6 support**: `IP_RE` only matches IPv4. In real-world testing, 0 IPv6 entries found in URLhaus data.
- **NER DOMAIN false positive rate 53.1%**: At Phase 9 scale, 19,794 raw DOMAIN matches → 10,144 FILENAME (51%), 8,946 DOMAIN (45%), 704 UNKNOWN (4%). Classifier reduces but cannot eliminate false positives.
- **PERSON/ORGANIZATION low accuracy**: Regex patterns look for titles ("Mr.", "Dr.") and company suffixes ("Inc.", "Corp."), rarely found in threat intelligence text.

## EvidenceChain (evidence_chain/confidence.py)
- **Keyword-based contradiction detection**: `ContradictionDetector` detects contradictions via proof content keywords ("contradicts"/"refutes"/"debunks"). Natural language contradictions are not captured.
- **Source trust defaults to 50**: When `source_trust_map` is not provided, all sources default to 50 — actual source reliability varies.

## EntityMatcher (graph.py)
- **O(n²) scale threshold**: ~100K node threshold before O(n²) comparison becomes a bottleneck. Hash-based pre-filter needed beyond that.
- **Same-type matching only**: Only matches same-type entities (IPAddress↔IPAddress, Domain↔Domain, CveEntity↔CveEntity). No cross-type matching.

## RelationshipExtractor (extractor.py)
- **`min_confidence=0.0` default (no filter)**: At Phase 10.3 scale, 0% false positive rate observed, so not urgent.
- **Co-occurrence approach**: Relationships are based on co-occurrence in the same sentence or document, not semantic understanding.
- Heat verbs hardcoded**: 28 threat intel verbs hardcoded ("exploits", "uses", "targets", etc.).

## Graph database (graph.py)
- **In-memory only**: IntelligenceGraph is held in RAM, no persistent storage. Pipeline rebuilds graph from scratch each run.

## Visualization (web/dashboard.html)
- **Chart.js CDN dependency**: Dashboard loads Chart.js from CDN. Fails in air-gapped/offline environments.
- **Static dashboard**: Not real-time — `/dashboard/summary` recalculates on each request. Uses SSE for metrics dashboard, not for graph visualization.

## Pipeline (chain.py)
- **UTILITY.write() doesn't return confidence**: Returns `{"key", "action", "source"}` — confidence must be read via `ute.read()`.
- **VERSION tag filtered from pipeline**: Phase 13 disambiguates VERSION from IP, pipe filters VERSION entity — version numbers don't enter the graph.
- **chain_manager SQLite path slow**: `resolve_evidence_contradictions` writes to SQLite per `add_entity` call — slow with 200+ entities. In-memory path (chain_manager=None) much faster.

## Sources
- **URLhaus JSON API returns 401**: Only CSV can be accessed.
- **OTX API key required**: Phase 6 used synthetic OTX data. Real pulses require API key.
- **OTX × URLhaus 0 common IOCs**: More sources needed for cross-source correlation.