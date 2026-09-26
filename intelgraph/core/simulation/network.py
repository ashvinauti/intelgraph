"""Seeded generator for synthetic adversary-network simulations.

See :mod:`intelgraph.core.simulation` for the safety model. Everything here
is deterministic given a seed, uses only reserved/documentation address
space, and performs no network activity.
"""

from __future__ import annotations

import ipaddress
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------------------
# Reserved address space (nothing below resolves to real infrastructure)
# ---------------------------------------------------------------------------

# RFC 5737 TEST-NET blocks reserved for documentation.
DOC_IPV4_BLOCKS: tuple[str, ...] = ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
# RFC 3849 IPv6 documentation block.
DOC_IPV6_BLOCK = "2001:db8::/32"
# RFC 2606 / 6761 reserved second-level names and TLDs.
RESERVED_DOMAINS: tuple[str, ...] = ("example.com", "example.net", "example.org")
RESERVED_TLDS: tuple[str, ...] = ("test", "invalid", "example")

# Real, publicly disclosed, already-fixed CVEs. Included only so CVE
# extraction has something to match; no exploit detail is generated.
CURATED_CVES: tuple[str, ...] = (
    "CVE-2021-44228",  # Log4Shell
    "CVE-2023-23397",  # Outlook privilege escalation
    "CVE-2021-34527",  # PrintNightmare
    "CVE-2020-1472",  # Zerologon
    "CVE-2019-19781",  # Citrix ADC
    "CVE-2022-30190",  # Follina
    "CVE-2021-26855",  # ProxyLogon
    "CVE-2018-13379",  # Fortinet path traversal
    "CVE-2023-34362",  # MOVEit
    "CVE-2017-0144",  # EternalBlue
)

# Malware-family "surnames" pair a codeword with one of the extractor's
# recognized malware keywords so that a malware entity is reliably produced.
_MALWARE_KEYWORDS: tuple[str, ...] = (
    "loader",
    "stealer",
    "backdoor",
    "dropper",
    "rat",
    "ransomware",
    "trojan",
    "webshell",
    "botnet",
)
_CODEWORDS_A: tuple[str, ...] = (
    "Amber",
    "Cobalt",
    "Crimson",
    "Iron",
    "Jade",
    "Midnight",
    "Onyx",
    "Scarlet",
    "Silent",
    "Umbra",
    "Vermillion",
    "Void",
)
_CODEWORDS_B: tuple[str, ...] = (
    "Adder",
    "Falcon",
    "Harrier",
    "Jackal",
    "Kestrel",
    "Lynx",
    "Mantis",
    "Osprey",
    "Raven",
    "Scorpion",
    "Viper",
    "Wolf",
)

# Kill-chain stages a campaign narrative can touch, roughly ordered.
_KILL_CHAIN: tuple[str, ...] = (
    "reconnaissance",
    "initial-access",
    "delivery",
    "exploitation",
    "command-and-control",
    "exfiltration",
)

_DOMAIN_LABELS: tuple[str, ...] = (
    "c2-panel",
    "c2-relay",
    "beacon",
    "update-svc",
    "cdn-edge",
    "mail-gw",
    "login-verify",
    "secure-portal",
    "doc-share",
    "invoice-portal",
    "payload-host",
    "staging",
    "auth-check",
    "vpn-gateway",
)

_FILE_NAMES: tuple[str, ...] = (
    "invoice.exe",
    "update.bin",
    "report.doc",
    "setup.msi",
    "final.exe",
    "loader.dll",
    "shipping-notice.pdf",
    "payload.dat",
)


@dataclass(frozen=True)
class Indicator:
    """A single simulated indicator of compromise."""

    kind: str  # ip | ipv6 | domain | url | sha256 | md5 | sha1 | email | cve
    value: str
    role: str  # c2 | dropper | phishing | staging | payload | exploit | contact
    shared: bool = False  # part of cross-campaign shared infrastructure

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "value": self.value, "role": self.role, "shared": self.shared}


@dataclass
class Campaign:
    """One simulated threat-actor campaign."""

    name: str
    actor: str
    malware_family: str
    first_seen: str
    indicators: list[Indicator] = field(default_factory=list)
    cves: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "actor": self.actor,
            "malware_family": self.malware_family,
            "first_seen": self.first_seen,
            "cves": list(self.cves),
            "indicators": [i.to_dict() for i in self.indicators],
        }


@dataclass
class SimulationConfig:
    """Parameters controlling generation. All output is deterministic in ``seed``."""

    seed: int = 1337
    campaigns: int = 3
    indicators_per_campaign: int = 8
    overlap: float = 0.35  # probability a campaign reuses shared infrastructure
    ipv6: bool = False  # also emit IPv6 (RFC 3849) C2 addresses

    def __post_init__(self) -> None:
        if self.campaigns < 1:
            raise ValueError("campaigns must be >= 1")
        if self.indicators_per_campaign < 3:
            raise ValueError("indicators_per_campaign must be >= 3")
        if not 0.0 <= self.overlap <= 1.0:
            raise ValueError("overlap must be between 0.0 and 1.0")


@dataclass
class Simulation:
    """A generated simulation: campaigns plus rendering helpers."""

    config: SimulationConfig
    generated_at: str
    campaigns: list[Campaign]

    @property
    def indicator_count(self) -> int:
        return sum(len(c.indicators) for c in self.campaigns)

    @property
    def shared_indicators(self) -> list[Indicator]:
        seen: dict[str, Indicator] = {}
        for c in self.campaigns:
            for ind in c.indicators:
                if ind.shared:
                    seen[ind.value] = ind
        return list(seen.values())

    def to_manifest(self) -> dict[str, object]:
        return {
            "kind": "intelgraph.simulation/network",
            "synthetic": True,
            "generated_at": self.generated_at,
            "config": {
                "seed": self.config.seed,
                "campaigns": self.config.campaigns,
                "indicators_per_campaign": self.config.indicators_per_campaign,
                "overlap": self.config.overlap,
                "ipv6": self.config.ipv6,
            },
            "indicator_count": self.indicator_count,
            "shared_indicator_count": len(self.shared_indicators),
            "campaigns": [c.to_dict() for c in self.campaigns],
        }

    def render_text(self) -> str:
        """Render the simulation as narrative threat-intel report text.

        The output is designed to be fed to the IntelGraph pipeline via
        ``intelgraph pipeline run --file <path>`` (or the ``--feed`` option on
        ``intelgraph simulate network``).
        """
        lines: list[str] = []
        lines.append(_HEADER.format(seed=self.config.seed, generated_at=self.generated_at))
        for camp in self.campaigns:
            lines.append("")
            lines.append(_render_campaign(camp))
        return "\n".join(lines).rstrip() + "\n"


_HEADER = """\
# SYNTHETIC threat-intelligence simulation for IntelGraph testing.
#
# Generated by `intelgraph simulate network` (seed={seed}) at {generated_at}.
#
# Every IP, domain, URL, and email below uses address space reserved for
# documentation/testing (RFC 5737, RFC 3849, RFC 2606/6761); hashes are
# random hex. NONE of it resolves to or identifies real infrastructure.
# CVE IDs reference real, already-fixed, publicly documented issues purely
# so CVE extraction has something to match. This file describes no real
# incident and is safe to ingest for detection/analytics testing."""


def _render_campaign(camp: Campaign) -> str:
    by_role: dict[str, list[Indicator]] = {}
    for ind in camp.indicators:
        by_role.setdefault(ind.role, []).append(ind)

    def first(role: str) -> Indicator | None:
        items = by_role.get(role)
        return items[0] if items else None

    sentences: list[str] = []
    sentences.append(
        f"## Campaign {camp.name} (tracked actor {camp.actor}), first observed "
        f"{camp.first_seen}."
    )

    phishing = first("phishing")
    dropper = first("dropper")
    payload_hash = next((i for i in camp.indicators if i.kind in ("sha256", "md5", "sha1")), None)
    c2 = first("c2")
    staging = first("staging")
    contact = first("contact")

    if phishing:
        sentences.append(
            f"A phishing campaign lured victims to {phishing.value} to harvest credentials "
            f"before redirecting them onward."
        )
    if dropper:
        drop = f"The {camp.malware_family} was delivered from {dropper.value}"
        if payload_hash:
            drop += f" (payload {payload_hash.kind.upper()}: {payload_hash.value})"
        drop += "."
        sentences.append(drop)
    if c2:
        c2_sentence = f"The implant beacons to a command-and-control endpoint at {c2.value}"
        extra_c2 = [i for i in by_role.get("c2", []) if i is not c2]
        if extra_c2:
            c2_sentence += " and falls back to " + ", ".join(i.value for i in extra_c2)
        c2_sentence += "."
        sentences.append(c2_sentence)
    if staging:
        sentences.append(f"A secondary stage was hosted at {staging.value}.")
    if camp.cves:
        sentences.append(
            "Operators attempted exploitation of "
            + ", ".join(camp.cves)
            + " for initial access."
        )
    if contact:
        sentences.append(f"Registration and control traffic referenced the address {contact.value}.")

    shared = [i for i in camp.indicators if i.shared]
    if shared:
        sentences.append(
            "Shared infrastructure overlaps with other tracked activity via "
            + ", ".join(i.value for i in shared)
            + ", suggesting a common operator or toolkit."
        )

    return "\n".join(sentences)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _rand_ipv4(rng: random.Random) -> str:
    block = ipaddress.ip_network(rng.choice(DOC_IPV4_BLOCKS))
    # host octet 1..254 within the /24
    host = rng.randint(1, 254)
    return str(ipaddress.ip_address(int(block.network_address) + host))


def _rand_ipv6(rng: random.Random) -> str:
    net = ipaddress.ip_network(DOC_IPV6_BLOCK)
    # place the host in the low 64 bits so it stays inside 2001:db8::/32
    host = rng.getrandbits(48)
    return str(ipaddress.ip_address(int(net.network_address) + host))


def _rand_domain(rng: random.Random) -> str:
    label = rng.choice(_DOMAIN_LABELS)
    suffix = rng.randint(1, 999)
    if rng.random() < 0.7:
        base = rng.choice(RESERVED_DOMAINS)
    else:
        base = f"{rng.choice(_DOMAIN_LABELS)}.{rng.choice(RESERVED_TLDS)}"
    return f"{label}-{suffix}.{base}"


def _rand_url(rng: random.Random, domain: str) -> str:
    scheme = "https" if rng.random() < 0.5 else "http"
    port = "" if rng.random() < 0.6 else f":{rng.choice((8080, 8443, 4443, 9001))}"
    path = rng.choice(_FILE_NAMES)
    return f"{scheme}://{domain}{port}/{path}"


def _rand_hex(rng: random.Random, length: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(length))


def _actor_name(rng: random.Random) -> str:
    return f"{rng.choice(_CODEWORDS_A)} {rng.choice(_CODEWORDS_B)}"


def _family_name(rng: random.Random) -> str:
    return f"{rng.choice(_CODEWORDS_A).upper()}{rng.choice(_CODEWORDS_B).lower()} {rng.choice(_MALWARE_KEYWORDS)}"


def _make_shared_pool(rng: random.Random, size: int) -> list[Indicator]:
    pool: list[Indicator] = []
    for _ in range(size):
        if rng.random() < 0.6:
            pool.append(Indicator(kind="ip", value=_rand_ipv4(rng), role="c2", shared=True))
        else:
            pool.append(Indicator(kind="domain", value=_rand_domain(rng), role="c2", shared=True))
    return pool


def _build_campaign(
    rng: random.Random,
    index: int,
    cfg: SimulationConfig,
    shared_pool: list[Indicator],
) -> Campaign:
    actor = _actor_name(rng)
    family = _family_name(rng)
    name = f"OP-{rng.choice(_CODEWORDS_B).upper()}-{index + 1:02d}"
    first_seen = (
        datetime.now(UTC) - timedelta(days=rng.randint(7, 400))
    ).date().isoformat()

    indicators: list[Indicator] = []

    # phishing domain + credential-harvest URL
    phish_domain = _rand_domain(rng)
    indicators.append(Indicator("domain", phish_domain, "phishing"))
    indicators.append(Indicator("url", _rand_url(rng, phish_domain), "phishing"))

    # dropper host + payload hash
    drop_domain = _rand_domain(rng)
    indicators.append(Indicator("url", _rand_url(rng, drop_domain), "dropper"))
    hash_kind, hash_len = rng.choice((("sha256", 64), ("md5", 32), ("sha1", 40)))
    indicators.append(Indicator(hash_kind, _rand_hex(rng, hash_len), "payload"))

    # C2: at least one, sometimes shared
    if shared_pool and rng.random() < cfg.overlap:
        indicators.append(rng.choice(shared_pool))
    else:
        indicators.append(Indicator("ip", _rand_ipv4(rng), "c2"))
    if cfg.ipv6:
        indicators.append(Indicator("ipv6", _rand_ipv6(rng), "c2"))

    # contact email on reserved domain
    handle = rng.choice(("admin", "billing", "support", "noreply", "ops"))
    indicators.append(Indicator("email", f"{handle}@{_rand_domain(rng)}", "contact"))

    # top up to the requested indicator budget with extra infra
    while len(indicators) < cfg.indicators_per_campaign:
        roll = rng.random()
        if roll < 0.4:
            indicators.append(Indicator("ip", _rand_ipv4(rng), "c2"))
        elif roll < 0.7:
            d = _rand_domain(rng)
            indicators.append(Indicator("domain", d, "staging"))
            indicators.append(Indicator("url", _rand_url(rng, d), "staging"))
        else:
            k, ln = rng.choice((("sha256", 64), ("md5", 32)))
            indicators.append(Indicator(k, _rand_hex(rng, ln), "payload"))

    indicators = indicators[: cfg.indicators_per_campaign]

    n_cves = rng.randint(1, 3)
    cves = rng.sample(CURATED_CVES, min(n_cves, len(CURATED_CVES)))

    return Campaign(
        name=name,
        actor=actor,
        malware_family=family,
        first_seen=first_seen,
        indicators=indicators,
        cves=cves,
    )


def _finalize_shared(campaigns: list[Campaign]) -> None:
    """Recompute each indicator's ``shared`` flag from actual cross-campaign use.

    An indicator is only truly shared infrastructure when the same value
    appears in more than one campaign; the initial flag set during generation
    is a hint, not ground truth.
    """
    counts: Counter[str] = Counter()
    for camp in campaigns:
        for value in {ind.value for ind in camp.indicators}:
            counts[value] += 1
    for camp in campaigns:
        camp.indicators = [
            Indicator(ind.kind, ind.value, ind.role, shared=counts[ind.value] > 1)
            for ind in camp.indicators
        ]


def generate_simulation(config: SimulationConfig | None = None) -> Simulation:
    """Generate a deterministic synthetic adversary-network simulation."""
    cfg = config or SimulationConfig()
    rng = random.Random(cfg.seed)

    # Shared infrastructure pool sized so overlaps are possible but not certain.
    pool_size = max(1, cfg.campaigns // 2)
    shared_pool = _make_shared_pool(rng, pool_size) if cfg.campaigns > 1 else []

    campaigns = [_build_campaign(rng, i, cfg, shared_pool) for i in range(cfg.campaigns)]
    _finalize_shared(campaigns)

    return Simulation(
        config=cfg,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        campaigns=campaigns,
    )
