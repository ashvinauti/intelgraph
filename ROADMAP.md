# IntelGraph — Roadmap

> **Note:** The original roadmap below reflects the initial planning. The project has delivered far beyond the original scope (42 phases complete, 1580 tests). See [README.md](./README.md) for the current feature set.

## Completed (Phases 1–42)

All planned foundation, core platform, entity model, collection, evidence chain, and enterprise integration phases are complete.

Key delivered features:
- Multi-source CTI pipeline (OTX, Shodan, VirusTotal, URLhaus, CISA KEV)
- Knowledge graph with temporal tracking
- STIX 2.1 / TAXII 2.1 export and enrichment
- Threat scoring, anomaly detection, automated playbooks
- 2FA, OAuth2, API key management
- Investigation workspace with pivot engine
- Performance dashboard (SSE)
- Graph export (GEXF, CSV)
- Docker support

## Completed (v0.2.0)

- ✅ GraphQL API (`/graphql`) — see [CHANGELOG.md](./CHANGELOG.md)
- ✅ Kubernetes Helm chart — see [deploy/helm/intelgraph](./deploy/helm/intelgraph)

## Planned (v1.1+)

The following were part of the original Phase 0–17 roadmap and remain relevant:

- SECURITY.md, DATA_POLICY.md, PROVENANCE_POLICY.md
- SOURCE_TRUST_MODEL.md, RETENTION_POLICY.md
- SIEM integrations (Splunk, ELK)
- SAML/LDAP/SSO enterprise auth
- DB-backed user store for TOTP secrets

## Original Phase Plan (Historical)

| Phase | Name | Status |
|-------|------|--------|
| 0 | Foundation | ✅ COMPLETE |
| 1–17 | Core through v1.0 | ✅ COMPLETE (42 phases delivered) |