from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

import pytest

from intelgraph.core.simulation import (
    SimulationConfig,
    generate_simulation,
)
from intelgraph.core.simulation.network import (
    CURATED_CVES,
    DOC_IPV4_BLOCKS,
    DOC_IPV6_BLOCK,
    RESERVED_DOMAINS,
    RESERVED_TLDS,
)

_DOC_V4_NETS = [ipaddress.ip_network(b) for b in DOC_IPV4_BLOCKS]
_DOC_V6_NET = ipaddress.ip_network(DOC_IPV6_BLOCK)


def _hostname(value: str) -> str:
    if "://" in value:
        return urlparse(value).hostname or ""
    if "@" in value:
        return value.split("@", 1)[1]
    return value


def _is_reserved_domain(host: str) -> bool:
    if host in RESERVED_DOMAINS:
        return True
    if any(host == d or host.endswith("." + d) for d in RESERVED_DOMAINS):
        return True
    tld = host.rsplit(".", 1)[-1]
    return tld in RESERVED_TLDS


class TestReservedSpaceInvariant:
    """The core safety guarantee: nothing points at real infrastructure."""

    def test_all_indicators_use_reserved_space(self):
        # Sweep many seeds/configs so the invariant is exercised broadly.
        for seed in range(50):
            sim = generate_simulation(
                SimulationConfig(seed=seed, campaigns=4, indicators_per_campaign=10, ipv6=True)
            )
            for camp in sim.campaigns:
                for ind in camp.indicators:
                    if ind.kind == "ip":
                        addr = ipaddress.ip_address(ind.value)
                        assert any(addr in net for net in _DOC_V4_NETS), ind.value
                    elif ind.kind == "ipv6":
                        assert ipaddress.ip_address(ind.value) in _DOC_V6_NET, ind.value
                    elif ind.kind in ("domain", "url", "email"):
                        host = _hostname(ind.value)
                        assert _is_reserved_domain(host), f"{ind.kind}: {ind.value}"
                    elif ind.kind in ("sha256", "md5", "sha1"):
                        expected = {"sha256": 64, "md5": 32, "sha1": 40}[ind.kind]
                        assert re.fullmatch(r"[0-9a-f]+", ind.value)
                        assert len(ind.value) == expected

    def test_cves_are_from_curated_fixed_list(self):
        sim = generate_simulation(SimulationConfig(seed=3, campaigns=5))
        for camp in sim.campaigns:
            for cve in camp.cves:
                assert cve in CURATED_CVES


class TestDeterminism:
    def test_same_seed_same_output(self):
        cfg = SimulationConfig(seed=99, campaigns=3, indicators_per_campaign=7)
        a = generate_simulation(cfg).render_text()
        b = generate_simulation(cfg).render_text()
        assert a == b

    def test_different_seed_different_output(self):
        a = generate_simulation(SimulationConfig(seed=1)).render_text()
        b = generate_simulation(SimulationConfig(seed=2)).render_text()
        assert a != b


class TestConfig:
    def test_rejects_too_few_campaigns(self):
        with pytest.raises(ValueError):
            SimulationConfig(campaigns=0)

    def test_rejects_too_few_indicators(self):
        with pytest.raises(ValueError):
            SimulationConfig(indicators_per_campaign=2)

    def test_rejects_out_of_range_overlap(self):
        with pytest.raises(ValueError):
            SimulationConfig(overlap=1.5)


class TestStructure:
    def test_campaign_and_indicator_counts(self):
        sim = generate_simulation(
            SimulationConfig(seed=5, campaigns=4, indicators_per_campaign=8)
        )
        assert len(sim.campaigns) == 4
        for camp in sim.campaigns:
            assert len(camp.indicators) == 8
            assert camp.cves  # at least one CVE
            assert camp.actor and camp.malware_family and camp.name

    def test_shared_flag_reflects_real_cross_campaign_use(self):
        sim = generate_simulation(
            SimulationConfig(seed=7, campaigns=6, indicators_per_campaign=8, overlap=0.9)
        )
        # Any indicator flagged shared must appear in >= 2 distinct campaigns.
        value_to_campaigns: dict[str, set[str]] = {}
        for camp in sim.campaigns:
            for ind in camp.indicators:
                value_to_campaigns.setdefault(ind.value, set()).add(camp.name)
        for camp in sim.campaigns:
            for ind in camp.indicators:
                if ind.shared:
                    assert len(value_to_campaigns[ind.value]) > 1, ind.value

    def test_high_overlap_produces_shared_infrastructure(self):
        sim = generate_simulation(
            SimulationConfig(seed=7, campaigns=6, indicators_per_campaign=8, overlap=0.9)
        )
        assert sim.shared_indicators

    def test_manifest_is_json_serializable_and_flagged_synthetic(self):
        import json

        sim = generate_simulation(SimulationConfig(seed=11, campaigns=2))
        manifest = sim.to_manifest()
        assert manifest["synthetic"] is True
        assert manifest["indicator_count"] == sim.indicator_count
        json.dumps(manifest)  # must not raise

    def test_render_text_has_safety_header(self):
        sim = generate_simulation(SimulationConfig(seed=1))
        text = sim.render_text()
        assert "SYNTHETIC" in text
        assert "reserved for" in text
