"""Synthetic adversary-network simulation.

Generates seeded, parameterized simulated threat-actor campaigns (C2
infrastructure, phishing chains, malware hashes, exploited CVEs, and
cross-campaign infrastructure pivots) as text the IntelGraph pipeline can
ingest, plus a structured manifest.

All network indicators are drawn exclusively from address space reserved
for documentation and testing so that nothing generated here resolves to,
or identifies, any real infrastructure:

* IPv4  - RFC 5737 TEST-NET blocks (192.0.2.0/24, 198.51.100.0/24,
  203.0.113.0/24)
* IPv6  - RFC 3849 documentation block (2001:db8::/32)
* Domains - RFC 2606 / 6761 reserved names (example.com/.net/.org) and
  reserved TLDs (.test, .invalid, .example)

File hashes are randomly generated hex of the correct length and do not
correspond to any known sample. CVE identifiers reference real, publicly
disclosed and already-fixed vulnerabilities purely so CVE extraction has
something to match.

This is a defensive testing aid: it exists to exercise IntelGraph's
ingestion, entity extraction, and graph link-analysis against realistic
but entirely synthetic data. It performs no network activity of its own.
"""

from intelgraph.core.simulation.network import (
    Campaign,
    Indicator,
    Simulation,
    SimulationConfig,
    generate_simulation,
)

__all__ = [
    "Campaign",
    "Indicator",
    "Simulation",
    "SimulationConfig",
    "generate_simulation",
]
