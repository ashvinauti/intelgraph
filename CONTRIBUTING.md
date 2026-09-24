# IntelGraph — Contributing

## Welcome

IntelGraph is an open-source project. Contributions are welcome — but quality is non-negotiable.

## Core Principles for Contributors

1. **Evidence over opinion** — Every claim in code, docs, or comments must be backed by evidence
2. **Reliability over speed** — We prioritize correct, tested, auditable code over fast delivery
3. **Architecture first** — No implementation without design review
4. **Determinism** — All collectors must be deterministic (same input → same output)
5. **Auditability** — Every change must be traceable to a reason

## Getting Started

1. Read Vision.md, Mission.md, and Architecture.md
2. Understand the entity model and trust model
3. Check ROADMAP.md for current phase
4. Look for open issues tagged with the current phase

## Development Setup

```bash
git clone https://github.com/intelgraph/intelgraph
cd intelgraph
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Coding Standards

### Python
- Target Python 3.11+
- Type annotations required on all public functions
- Docstrings required on all modules, classes, and public methods
- Maximum line length: 100 characters
- Follow PEP 8 with these exceptions:
  - Line length: 100 (not 79)
  - Naming: descriptive over short

### Testing
- All new code must have tests
- Minimum coverage: 90% for core, 80% for collectors
- Tests must be deterministic
- Tests must not require network access (mock external services)
- Use pytest exclusively

### Commit Messages
```
<type>(<scope>): <short description>

<optional body>

<evidence or motivation>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

Example:
```
feat(collectors): add WHOIS domain collector

Implements RFC 3912 compliant WHOIS query with
timeout, retry, and response parsing.

Evidence: WHOIS protocol documented at
https://tools.ietf.org/html/rfc3912
```

## Pull Request Process

1. PR must reference an issue
2. PR must pass all CI checks
3. PR must include tests
4. PR must include documentation updates
5. PR must be reviewed by at least one maintainer
6. PR must not reduce test coverage

## Code of Conduct

- Be professional
- Attack ideas, not people
- Assume good faith
- Provide evidence for claims
- Respect maintainer decisions

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
