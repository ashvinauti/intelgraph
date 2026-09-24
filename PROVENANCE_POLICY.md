# IntelGraph — Provenance Policy

## Definition

Provenance is the complete, auditable record of where a piece of data came from, how it was obtained, and how it was transformed.

## Mandatory Requirements

Every entity, relationship, and evidence item MUST include:

### 1. Source Identification
- Source URL or API endpoint
- Source tier (1, 2, or 3)
- Source trust score (0-100)
- Source reliability score (0-100)

### 2. Collection Metadata
- Collector name and version
- Collection timestamp (UTC, ISO 8601)
- Correlation ID
- Collector run ID
- Raw data reference (pointer to stored raw data)

### 3. Transformation History
- Every normalization step
- Every alias resolution
- Every deduplication merge
- Timestamp of each transformation
- Responsible component for each transformation

### 4. Confidence Attribution
- Base confidence from collector
- Confidence modifiers (deduplication, cross-referencing)
- Confidence calculation method
- Final confidence score breakdown

## Provenance Record Format

```json
{
  "entity_id": "01HXYZ...",
  "provenance": {
    "sources": [
      {
        "url": "https://example.com/",
        "tier": 1,
        "trust_score": 95,
        "reliability_score": 90,
        "collected_at": "2026-06-16T10:30:00Z",
        "collector": "whois_domain",
        "collector_version": "1.0.0"
      }
    ],
    "transformations": [
      {
        "type": "normalization",
        "from": "Example, Inc.",
        "to": "Example Inc.",
        "component": "canonicalizer.company_name",
        "timestamp": "2026-06-16T10:30:01Z"
      }
    ],
    "confidence": {
      "base": 85,
      "modifiers": [
        {
          "type": "cross_reference",
          "source": "ct_log_domain",
          "delta": 5
        }
      ],
      "final": 90,
      "method": "weighted_average"
    }
  }
}
```

## Immutability

- Provenance records are append-only
- Once written, provenance data cannot be modified
- Corrections add new provenance entries (do not delete old ones)
- Full history is always preserved

## Audit Trail Requirements

Every provenance-aware operation MUST log:
- Operation type (collect, normalize, merge, resolve, verify)
- Input entity/evidence references
- Output entity/evidence references
- Operator (component or user)
- Timestamp
- Correlation ID
- Rationale/explanation

## Proof of Collection

Where possible, collectors SHOULD capture:
- HTTP response headers
- Response body hash (SHA-256)
- TLS certificate details
- DNS resolution path

This enables third-party verification that collection was performed as claimed.

## Non-Repudiation

Provenance records serve as non-repudiation evidence:
- An entity was collected from a specific source at a specific time
- The collector was configured in a specific way
- The data was transformed through a specific pipeline

This is critical for:
- Legal admissibility
- Investigation reproducibility
- Peer review of intelligence products
