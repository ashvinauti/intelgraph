# IntelGraph — Data Policy

## Purpose

Define how IntelGraph handles data throughout its lifecycle — collection, storage, processing, output, and deletion.

## Data Collection Principles

1. **Public only** — IntelGraph collects only publicly available data from legally accessible sources.
2. **Minimal collection** — Collect only what is needed for the investigation. No bulk harvesting.
3. **Source transparency** — Every data point is tagged with its source URL and collection timestamp.
4. **No data enrichment from private sources** — IntelGraph will never integrate private, leaked, or stolen data.

## Data Storage

### What We Store
- Raw collector output (immutable)
- Normalized entity records
- Relationship records
- Evidence chains
- Audit logs
- Configuration files

### Storage Format
- Raw data: JSON
- Entities: SQL rows with JSON fields
- Evidence: SQL rows with JSON fields
- Audit logs: Structured JSON logs

### Data Retention
- By default, all data persists until explicitly deleted
- Users may configure retention policies per investigation
- Audit logs are subject to RETENTION_POLICY.md

## Data Processing

### Normalization
- Raw data is normalized into entity records
- Original raw data is preserved and linked to normalized records
- No irreversible transformations

### Deduplication
- Duplicate entities are merged according to entity merging rules
- Original records are preserved in the audit trail
- Merge operations are logged with full provenance

### Canonicalization
- Values are normalized to canonical forms
- Original values are preserved as aliases
- Canonicalization mapping is stored for auditability

## Data Access

- IntelGraph is a local-first tool
- Data never leaves the user's machine unless explicitly exported
- No telemetry, no analytics, no phone-home
- No cloud sync (unless user explicitly configures it)

## Data Deletion

### Manual Deletion
- Users may delete individual entities, relationships, or entire investigations
- Deletion is logged in audit trail
- Deleted data is soft-deleted with configurable hard-delete window

### Automated Deletion
- Configurable retention policies
- Automated cleanup of expired investigations
- Automated log rotation

## Data Portability

- All data can be exported as JSON
- All data can be exported as CSV (tabular entities)
- All data can be exported as GraphML
- No proprietary formats
- No vendor lock-in

## Compliance

IntelGraph is designed to support:
- GDPR compliance (right to deletion, data portability)
- SOX compliance (audit trails)
- Internal compliance policies (configurable retention)

IntelGraph does NOT:
- Process personal data on behalf of users
- Store user data on third-party servers
- Share data with third parties
- Use data for training or analytics
