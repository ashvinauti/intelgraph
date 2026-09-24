# IntelGraph — Retention Policy

## Purpose

Define how long different types of data are retained, how they are archived, and how they are disposed.

## Data Classification

IntelGraph classifies data into the following categories:

| Class | Examples | Sensitivity |
|-------|----------|-------------|
| Investigation | Entities, relationships, evidence chains | User-confidential |
| Raw Collection | Collector output, HTTP responses | Low |
| Audit Logs | Operation records, provenance entries | Medium |
| Configuration | User settings, collector configs | Low |
| Cache | DNS cache, WHOIS cache | Low |
| Logs | Runtime logs, error logs | Low |

## Retention Periods

### Investigation Data
| Type | Active | Archive | Delete |
|------|--------|---------|--------|
| Entities | Until investigation closed | 90 days after close | After archive period |
| Relationships | Until investigation closed | 90 days after close | After archive period |
| Evidence chains | Until investigation closed | 365 days after close | After archive period |
| Raw collector data | Until investigation closed | 30 days after close | After archive period |

### System Data
| Type | Retention | Action |
|------|-----------|--------|
| Audit logs | 365 days | Compressed archive, then delete |
| Runtime logs | 90 days | Rotate and delete |
| Cache data | 24 hours | Auto-expire |
| Configuration | Until explicitly changed | Keep current version, archive previous 5 |

### Default Global Retention
- All investigation data: 365 days from last access
- After 365 days: notification to user, then auto-archive
- After 730 days: auto-delete if not accessed

## Retention Enforcement

- Retention is enforced at the storage layer
- Automated cleanup jobs run daily
- Cleanup jobs are logged in audit trail
- Cleanup can be paused by investigation hold

## Legal Holds

- Investigations under legal hold are exempt from deletion
- Legal hold is set via configuration
- Legal hold is logged in audit trail
- Legal hold requires explicit human action to release

## Archival Format

Archived data is:
- Compressed (gzip)
- Encrypted (AES-256-GCM, user-provided key)
- Indexed by investigation ID and date range
- Stored in configurable archive directory
- Verifiable via SHA-256 manifest

## Deletion Procedure

### Soft Delete
1. Mark record as deleted
2. Remove from active queries
3. Preserve in storage for configurable grace period
4. Log deletion in audit trail

### Hard Delete
1. Verify grace period expired
2. Remove from storage
3. Verify removal via checksum
4. Log permanent deletion in audit trail

Default grace period: 30 days

## User Notification

- 30 days before retention expiry: warning log
- 7 days before deletion: notification (if configured)
- Upon deletion: audit trail entry
- No notification for routine cache/runtime log cleanup

## Policy Override

Retention periods can be overridden:
- Per investigation
- Per entity type
- Globally
- All overrides are logged
- Overrides require explicit configuration
