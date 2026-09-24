# IntelGraph REST API — Integration Guide

This document shows how to integrate IntelGraph with a SIEM, SOAR, or custom
scripting layer using only the public REST API.

## Base URL

Replace `${BASE}` everywhere with your IntelGraph deployment URL, e.g.
`http://localhost:8000`.

## Authentication

Two authentication mechanisms are supported and can be used interchangeably on
any protected endpoint.

### Option A — API key (recommended for automation)

Send the tenant API key in the `X-API-Key` header. No token exchange is
required.

```bash
curl -H "X-API-Key: ${INTELGRAPH_API_KEY}" \
     "${BASE}/enrichment/ip_address/107.172.135.60"
```

Issue an API key from the tenants API once; rotation with a 24h grace period
keeps the old key valid while clients migrate.

### Option B — JWT bearer (recommended for interactive dashboards)

Register or log in to get a JWT, then send it in `Authorization: Bearer`.

```bash
TOKEN=$(curl -s -X POST "${BASE}/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"soc-bot","password":"strong-pass","role":"admin"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer ${TOKEN}" \
     "${BASE}/enrichment/ip_address/107.172.135.60"
```

## Rate Limiting

Every response includes these headers:

| Header | Meaning |
|---|---|
| `X-RateLimit-Limit` | Requests allowed per window |
| `X-RateLimit-Remaining` | Requests remaining in current window |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |
| `X-RateLimit-Category` | Bucket category (`health`, `auth`, `read`, `write`) |

When the limit is exceeded, the API returns `429 Too Many Requests` with a
`Retry-After` header (seconds). Back off and retry.

## Core Endpoints for SOC Workflows

### 1. IOC enrichment — `/enrichment/{ioc_type}/{ioc_value}`

Returns entity attributes, related infrastructure, confidence/trust scores,
and threat score in one call. `ioc_type` ∈ `ip_address`, `domain`, `cve`,
`url`, `hash`.

```bash
curl -H "X-API-Key: ${INTELGRAPH_API_KEY}" \
     "${BASE}/enrichment/ip_address/107.172.135.60?max_neighbors=25"
```

Example response:

```json
{
  "ioc_type": "ip_address",
  "ioc_value": "107.172.135.60",
  "found": true,
  "entity": {
    "entity_id": "01JK...",
    "entity_type": "ip_address",
    "identifier": "107.172.135.60",
    "confidence_score": 94,
    "trust_score": 70,
    "first_seen": "2025-11-03T...",
    "last_seen": "2025-11-03T...",
    "source": "urlhaus",
    "evidence_count": 3
  },
  "related_entities": [
    {
      "entity_id": "01JK...",
      "entity_type": "domain",
      "identifier": "dgitaltrading.com",
      "confidence_score": 88,
      "relationships": [
        {
          "edge_id": "rel_...",
          "relationship_type": "resolves_to",
          "direction": "outgoing",
          "confidence": 90
        }
      ]
    }
  ],
  "related_count": 1,
  "threat_score": 87.5
}
```

### 2. Threat search — `/search`

```bash
curl -H "X-API-Key: ${INTELGRAPH_API_KEY}" \
     "${BASE}/search?q=mirai&type=ip_address&limit=20"
```

Returns matching entity IDs, types, identifiers, and relevance scores.

### 3. STIX 2.1 export — `/export/stix`

```bash
curl -H "X-API-Key: ${INTELGRAPH_API_KEY}" \
     "${BASE}/export/stix" > intelgraph_bundle.json
```

Optional `since` filter (ISO 8601):

```bash
curl -H "X-API-Key: ${INTELGRAPH_API_KEY}" \
     "${BASE}/export/stix?since=2026-01-01T00:00:00" > recent_bundle.json
```

The returned bundle is valid STIX 2.1 and can be ingested by MISP, OpenCTI,
or any TAXII 2.1 consumer.

### 4. Investigation workspace — `/investigations`

Create an investigation pivoting from an IOC:

```bash
INVID=$(curl -s -X POST "${BASE}/investigations" \
  -H "X-API-Key: ${INTELGRAPH_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Mirai C2 hunt","seed_ioc":"107.172.135.60","seed_ioc_type":"ip_address"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['investigation_id'])")

# Run the pivot from the seed IOC across the graph
curl -X POST "${BASE}/investigations/${INVID}/pivot" \
  -H "X-API-Key: ${INTELGRAPH_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"max_depth": 2}'
```

Add an analyst note:

```bash
curl -X POST "${BASE}/investigations/${INVID}/notes" \
  -H "X-API-Key: ${INTELGRAPH_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"author":"sanket","content":"Confirmed C2, blocking at firewall","pinned":true}'
```

## Python Example

```python
import os
import httpx

BASE = os.environ["INTELGRAPH_BASE_URL"]       # e.g. http://localhost:8000
API_KEY = os.environ["INTELGRAPH_API_KEY"]     # tenant API key (X-API-Key)

headers = {"X-API-Key": API_KEY}

def enrich(ioc_type: str, ioc_value: str) -> dict:
    """Look up an IOC and return enrichment + related entities."""
    resp = httpx.get(
        f"{BASE}/enrichment/{ioc_type}/{ioc_value}",
        headers=headers,
        params={"max_neighbors": 25},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()

def export_stix(since: str | None = None) -> dict:
    """Export the entire knowledge graph as a STIX 2.1 bundle."""
    params = {}
    if since:
        params["since"] = since
    resp = httpx.get(f"{BASE}/export/stix", headers=headers, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()

def create_investigation(name: str, seed_ioc: str, seed_ioc_type: str) -> dict:
    resp = httpx.post(
        f"{BASE}/investigations",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "name": name,
            "seed_ioc": seed_ioc,
            "seed_ioc_type": seed_ioc_type,
            "created_by": "soc-script",
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()

def pivot(investigation_id: str, max_depth: int = 2) -> dict:
    resp = httpx.post(
        f"{BASE}/investigations/{investigation_id}/pivot",
        headers={**headers, "Content-Type": "application/json"},
        json={"max_depth": max_depth},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    enriched = enrich("ip_address", "107.172.135.60")
    if enriched["found"]:
        print(f"Threat score: {enriched['threat_score']}")
        for nbr in enriched["related_entities"]:
            print(f"  related {nbr['entity_type']}: {nbr['identifier']}")
    # One-shot STIX export for ingestion into MISP/OpenCTI
    bundle = export_stix()
    print(f"Exported {len(bundle.get('objects', []))} STIX objects")
```

## Swagger / ReDoc

- **Swagger UI:** `${BASE}/docs`
- **ReDoc:** `${BASE}/redoc`
- **OpenAPI 3.1 schema:** `${BASE}/openapi.json`

The OpenAPI schema is the source of truth for request/response shapes. Use it
to auto-generate clients in any language (openapi-generator, etc.).