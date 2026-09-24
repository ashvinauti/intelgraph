# IntelGraph — Security Policy

## Scope

This security policy applies to the IntelGraph platform, its source code, dependencies, build pipeline, and all official distributions.

## Threat Model

### Assets to Protect
- Source code and build integrity
- User investigation data (entities, relationships, evidence)
- Configuration files (may contain API keys for public data sources)
- Audit logs (integrity and non-repudiation)

### Trust Boundaries
1. **User workstation** — IntelGraph CLI runs on the user's machine. The user is responsible for workstation security.
2. **Data source boundary** — IntelGraph only contacts public data sources via public APIs. No authentication secrets for private systems.
3. **Storage boundary** — Local SQLite or PostgreSQL. User controls access.

### Assumptions
- The user's operating system is trusted
- The user's network is trusted
- Public data sources may return malicious data (must be sanitized)
- Plugin collectors may be third-party code (must be sandboxed)

## Security Requirements

### Code Security
- No hardcoded credentials, tokens, or secrets
- No command injection vulnerabilities
- No eval() or dynamic code execution from untrusted input
- All input from data sources must be sanitized before storage
- All file paths must be validated to prevent path traversal

### Dependency Security
- All dependencies must be pinned to specific versions
- Automated Dependabot or equivalent scanning required
- All dependencies must be audited before major releases
- Minimum dependency count philosophy

### Output Security
- HTML reports must not include inline JavaScript
- No executable content in any output format
- All output must be safe to serve via HTTP

### Build Security
- CI/CD pipelines must use pinned action versions
- Build artifacts must be checksummed
- Releases must be signed

## Vulnerability Reporting

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Email the maintainers at security@intelgraph.io
3. Include: description, impact, reproduction steps, suggested fix (if any)
4. Allow 72 hours for initial response
5. Allow 30 days for fix before public disclosure

## Responsible Disclosure

We follow coordinated disclosure:
1. Report received and acknowledged (72h)
2. Investigation and fix (14-30 days)
3. Patch release
4. Public disclosure after patch

## Out of Scope

- The user's own data or investigations
- Attacks requiring physical access
- Social engineering of project maintainers
- Denial of service against public data sources
