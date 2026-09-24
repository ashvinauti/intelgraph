# IntelGraph — Source Trust Model

## Overview

The Source Trust Model provides a consistent, auditable framework for assigning trust and reliability scores to data sources. Every piece of data in IntelGraph inherits the trust characteristics of its source.

## Trust Score (0-100)

Trust score measures **how much we trust that the source provides accurate information**.

### Tier 1 — High Trust (75-100)

Official, authoritative, or verified sources.

| Source Type | Base Trust | Rationale |
|-------------|-----------|-----------|
| Official company website | 95 | Company controls its own domain |
| Government registry | 95 | Legal authority, verified records |
| Certificate Transparency log | 90 | Cryptographic proof, public audit |
| Official press release | 85 | Company-authorized communication |
| RFC/Standards body | 95 | Technical authority |

### Tier 2 — Medium Trust (40-74)

Semi-official, curated, or professionally maintained sources.

| Source Type | Base Trust | Rationale |
|-------------|-----------|-----------|
| Public staff directory | 70 | Organization-maintained but may be stale |
| Conference biography | 65 | Self-submitted, may be curated |
| Author page (publisher) | 60 | Publisher-verified but not primary |
| Public repository (official org) | 65 | Organization-controlled, but open to PRs |
| LinkedIn profile | 55 | Self-reported, some verification |
| Crunchbase | 50 | Crowd-sourced with curation |
| WHOIS data | 60 | Registrar data, but privacy services exist |

### Tier 3 — Low Trust (0-39)

Community, user-generated, or unverified sources.

| Source Type | Base Trust | Rationale |
|-------------|-----------|-----------|
| Forum post | 20 | Anonymous, unverified |
| Social media mention | 15 | Unverified, potential misinformation |
| Blog comment | 10 | Anonymous, unmoderated |
| Wiki (open) | 35 | Community-edited, variable quality |
| Pastebin / ephemeral content | 5 | Anonymous, no guarantees |

## Reliability Score (0-100)

Reliability score measures **the historical reliability of the source based on past accuracy**.

### Calculation Method

```
reliability_score = base_reliability + verified_corrections_delta
```

Where:
- `base_reliability` = starting score for the source type
- `verified_corrections_delta` = adjustments based on verified accuracy history

### Initial Values

| Tier | Base Reliability |
|------|-----------------|
| Tier 1 | 90 |
| Tier 2 | 60 |
| Tier 3 | 20 |

## Source Classification

Each source in the Source Registry includes:

```json
{
  "source_id": "whois_verisign_com",
  "name": "Verisign WHOIS",
  "type": "whois",
  "tier": 1,
  "trust_score": 90,
  "reliability_score": 95,
  "last_validated": "2026-06-16T00:00:00Z",
  "validation_method": "cross_reference",
  "url": "https://whois.verisign.com/",
  "notes": "Authoritative .com/.net WHOIS provider"
}
```

## Score Aggregation

When an entity is supported by multiple sources, the entity's trust score is:

```
entity_trust = weighted_average(source_trust × source_weight)
```

Where source weight depends on:
- Source tier (Tier 1 = 3x, Tier 2 = 2x, Tier 3 = 1x)
- Source recency (more recent = higher weight)
- Source independence (independent sources = higher weight)

## Score Decay

Trust and reliability scores decay over time:

| Time Since Validation | Decay Factor |
|----------------------|--------------|
| < 30 days | 0% |
| 30-90 days | -10% |
| 90-180 days | -25% |
| 180-365 days | -50% |
| > 365 days | -75% |

## Manual Override

Trust scores can be manually overridden by:
- Human reviewer with appropriate authority
- Override is logged with reason
- Original score preserved in audit trail
- Override expires after configurable period
