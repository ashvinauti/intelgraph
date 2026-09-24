# Changelog

## [0.2.0] - Unreleased

Builds on the upstream [IntelGraph v0.1.0](https://github.com/Berkayy123-h/intelgraph)
by delivering two items from its own `ROADMAP.md` "Planned (v1.1+)" list.

### Added

- **GraphQL API** (`/graphql`, GraphiQL IDE included) alongside the existing REST API.
  Backed by the same `ServiceContainer` and storage layer, so data is shared between
  both APIs.
  - Queries: `entity`, `entities`, `relationship`, `relationships`, `search`.
  - Mutations: `createEntity`, `createRelationship` (audit-logged, same as REST).
  - Mutations require the same JWT bearer / API key authentication as REST writes.
  - See `intelgraph/api/graphql_schema.py` and `tests/api/test_graphql.py`.
- **Kubernetes Helm chart** (`deploy/helm/intelgraph/`) for deploying the API:
  Deployment, Service, Ingress, ConfigMap, Secret, PVC (SQLite mode),
  HorizontalPodAutoscaler, ServiceAccount, liveness/readiness probes wired to
  `/health/live` and `/health/ready`. See `deploy/helm/intelgraph/README.md`.
- **`intelgraph pipeline run` CLI command** that fetches the live URLhaus feed
  (and OTX pulses, if `OTX_API_KEY` is set), runs the collection/NLP/graph
  pipeline, and feeds the result to a running server's dashboard via
  `POST /dashboard/feed`. See `intelgraph/cli/pipeline.py` and
  `tests/cli/test_pipeline.py`.

### Fixed

- Removed a hardcoded OTX API key that was committed in plaintext across three
  dev scripts (`scripts/phase7_dashboard_run.py`, `phase18_pipeline_test.py`,
  `phase18_otx_cross_source.py`), inherited from the upstream import. They now
  require `OTX_API_KEY` to be set in the environment.

### Remaining from upstream roadmap (not in this release)

- SIEM integrations (Splunk, ELK)
- SAML/LDAP/SSO enterprise auth
- DB-backed user store for TOTP secrets

## [0.1.0] - Upstream baseline

Imported from [Berkayy123-h/intelgraph](https://github.com/Berkayy123-h/intelgraph)
(MIT licensed). See that project's `README.md`, `Architecture.md`, and
`FINAL_STATUS.md` for the full feature set at this baseline (1,580+ tests,
multi-source CTI pipeline, knowledge graph, STIX 2.1/TAXII export, investigation
workspace, 2FA/OAuth2, playbook automation, and more).
