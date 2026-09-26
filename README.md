# IntelGraph

> An **open-source threat intelligence platform** that correlates indicators of compromise (IOCs) from multiple sources in a knowledge graph and explains every alert with an evidence-based reasoning chain.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 1,600+](https://img.shields.io/badge/Tests-1600%2B-brightgreen.svg)](#-testing)
[![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-yellow.svg)](#)

**Maintained by [Ashvin Auti](https://github.com/ashvinauti)** · **Originally created by [Berkay Altıntaş](https://github.com/Berkayy123-h)**

---

## 👥 Authors & Credits

| Role | Person | Links |
|------|--------|-------|
| **Original author & creator** | **Berkay Altıntaş** | [Berkayy123-h/intelgraph](https://github.com/Berkayy123-h/intelgraph) |
| **Fork maintainer** | **Ashvin Auti** | [ashvinauti/intelgraph](https://github.com/ashvinauti/intelgraph) |

IntelGraph was designed and built by **Berkay Altıntaş**. The core architecture, knowledge-graph engine, evidence-chain model, NLP pipeline and most of the codebase are their work, released under the MIT License. Full credit for the original project goes to them. Please star and support the [original repository](https://github.com/Berkayy123-h/intelgraph).

This repository is a fork maintained by **Ashvin Auti**. It builds on the original with:

- **GraphQL API** (`/graphql`) with a GraphiQL IDE, alongside the REST API
- **Kubernetes Helm chart** in [`deploy/helm/intelgraph`](./deploy/helm/intelgraph)
- **`intelgraph pipeline run`** command to populate the dashboard from live URLhaus/OTX feeds, a local URLhaus CSV, or synthetic sample data
- **SOC integrations**: IOC enrichment endpoint and STIX 2.1 bundle export
- **Bug fixes**: dashboard date-filter crashes, enrichment threat score always returning `null`, Technology entity updates failing, `intelgraph ops backup` crashing after a successful backup, and more, with regression tests

See [CHANGELOG.md](./CHANGELOG.md) for the full list of changes in this fork.

---

## 🎯 Use Cases

- **Investigate threats**: look up suspicious IPs, domains, URLs, hashes and CVEs across multiple intelligence sources
- **Correlate indicators**: link related IOCs into an interactive knowledge graph
- **Reduce false positives**: validate indicators against multiple trusted sources
- **Explain alerts**: every alert comes with an evidence chain showing *why* it fired
- **Share intelligence**: export as STIX 2.1 bundles for MISP, OpenCTI or other platforms

---

## 💡 Why IntelGraph?

Most threat intelligence platforms aggregate indicators. **IntelGraph also explains why an IOC is considered malicious.**

| Feature | Description |
|---------|-------------|
| 🔗 **Multi-source correlation** | Correlates data from multiple threat sources |
| 📋 **Evidence chains** | Tracks provenance and reasoning for every conclusion |
| 📊 **Knowledge graph** | Visualizes relationships between threats |
| 🚨 **Contradiction detection** | Flags conflicting intelligence between sources |
| 📤 **STIX 2.1 export** | Standards-compliant intelligence sharing |

IntelGraph is meant to **complement** platforms like OpenCTI, MISP and commercial TIPs by focusing on explainable, evidence-driven correlation.

---

## 📸 Screenshots

![IntelGraph Pipeline Dashboard](screenshots/dashboard.jpg)

*Pipeline dashboard: knowledge graph with live threat correlation*

---

## ✨ Features

### Data sources
- **OTX** (AlienVault community intelligence), API client
- **Shodan** (internet-connected device data), API client
- **VirusTotal** (file / URL / domain reputation), API client
- **URLhaus** (malicious URL feed), live fetch or CSV import
- *Planned:* CISA KEV (known exploited vulnerabilities)

### Entity processing
- Custom NER that extracts IOCs from raw text
- Hash-index deduplication
- Evidence-based confidence and threat scoring (0–100)
- Contradiction detection

### Knowledge graph
- Temporal tracking of threat evolution
- Attack-path analysis, anomaly detection, influence and reasoning engines
- Relationship mapping and export (JSON, STIX 2.1)

### APIs & dashboard
- REST API (FastAPI) with interactive docs at `/docs`
- GraphQL API with GraphiQL at `/graphql`
- Single-page dashboard with a D3.js force graph and live updates (SSE)

### Security
- JWT authentication, optional 2FA, API keys
- Role-based access control
- Sliding-window rate limiting
- Audit logging

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- SQLite (default) or PostgreSQL

### Install

```bash
git clone https://github.com/ashvinauti/intelgraph.git
cd intelgraph
uv sync
cp .env.example .env
```

### Configure

Edit `.env` (see `.env.example` for every option). The main settings:

```env
INTELGRAPH_SECRET_KEY=a-random-secret-at-least-32-chars   # required
INTELGRAPH_DB_PATH=intelgraph.db                          # SQLite (default)
# DATABASE_URL=postgresql://user:pass@localhost:5432/intelgraph

# Optional: leave empty to disable that source
OTX_API_KEY=
VIRUSTOTAL_API_KEY=
SHODAN_API_KEY=
```

### Run

```bash
# Local development
uv run uvicorn intelgraph.api.main:app --reload
# Dashboard: http://localhost:8000   API docs: http://localhost:8000/docs

# Docker
docker build -t intelgraph .
docker run -p 8000:8000 --env-file .env intelgraph

# Kubernetes (Helm)
helm install intelgraph ./deploy/helm/intelgraph \
  --set image.repository=<your-registry>/intelgraph \
  --set secrets.INTELGRAPH_SECRET_KEY=$(openssl rand -hex 32)
```

### Populate the dashboard

A fresh install starts with an empty graph. With the server running:

```bash
# Live URLhaus feed (no API key needed); also uses OTX if OTX_API_KEY is set
uv run intelgraph pipeline run

# Offline / demo: synthetic IOCs only (RFC 5737 IPs and example.* domains, safe to use)
uv run intelgraph pipeline run --skip-urlhaus --file samples/synthetic_iocs.txt

# Larger synthetic datasets on demand: multiple linked campaigns, tunable, seeded
uv run intelgraph simulate network --seed 42 --campaigns 8 --overlap 0.5 --feed

# A URLhaus CSV you downloaded from https://urlhaus.abuse.ch/downloads/csv_recent/
uv run intelgraph pipeline run --urlhaus-csv path/to/urlhaus_recent.csv
```

The network simulator generates richly-connected synthetic campaigns
(shared-infrastructure pivots, malware hashes, exploited CVEs) using only
reserved/documentation address space. See
[`docs/malicious-network-simulation.md`](docs/malicious-network-simulation.md)
for the full option list, the safety model, and how to feed a deployment
running on AWS/EKS.

Useful flags:
- `--no-feed`: print the extraction summary without updating the dashboard
- `--base-url`: point at a server that isn't on `http://localhost:8000`
- `--file`: may be passed several times to combine sources

`--urlhaus-csv` and `--skip-urlhaus` cannot be used together.

---

## 🔌 API Examples

Get a token first:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "analyst", "password": "change-me-123", "role": "admin"}'
# → {"access_token": "...", ...}

export TOKEN=<access_token>
```

**Enrich an indicator** (`ioc_type` is one of `ip_address`, `domain`, `cve`, `url`, `hash`):

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/enrichment/ip_address/192.0.2.1
# → entity details, related entities, confidence/trust and threat_score
```

**Search the graph:**

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/search?q=ransomware"
```

**Create an entity:**

```bash
curl -X POST http://localhost:8000/entities \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_type": "ipaddress", "attributes": {"ip": "192.0.2.1", "confidence_score": 80}}'
```

**Export as STIX 2.1** (optionally only data since a timestamp):

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/export/stix?since=2026-01-01T00:00:00Z"
```

**Dashboard graph data** (`since` accepts an ISO date or a relative value like `7d`):

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/dashboard/graph?since=7d"
```

See `http://localhost:8000/docs` for the full endpoint list.

---

## 🖥️ CLI

The `intelgraph` command groups include:

| Command | Purpose |
|---------|---------|
| `pipeline` | Run the collection → NLP → graph pipeline |
| `collect`, `source`, `datasources` | Manage and collect from intelligence sources |
| `graph`, `attack-path`, `anomaly` | Query and analyze the knowledge graph |
| `evidence`, `verify`, `review` | Evidence chains, verification, human review |
| `nlp`, `reasoning`, `prediction` | Extraction, causal reasoning, forecasting |
| `report` | Generate investigation reports |
| `ops` | Health, metrics, backup, log rotation |

Run `uv run intelgraph --help` or `uv run intelgraph <command> --help` for details.

---

## 📊 Architecture

```
Threat feeds (OTX, Shodan, VirusTotal, URLhaus)
        │
        ▼
    Collectors
        │
        ▼
  NLP & normalization
        │
        ▼
  Knowledge graph ──► Evidence chains & scoring
        │
   ┌────┴─────┐
   ▼          ▼
 Alerts   Investigations
   │          │
   └────┬─────┘
        ▼
REST / GraphQL / STIX export
```

```
intelgraph/
├── api/            # FastAPI app, routers, auth, middleware, GraphQL schema
├── cli/            # Click commands
├── core/
│   ├── collection/     # Collector framework (HTTP, RSS, file, API)
│   ├── entity/         # Entity models (IP, domain, CVE, technology, …)
│   ├── evidence_chain/ # Evidence construction & confidence scoring
│   ├── export/         # STIX 2.1 export
│   ├── graph/          # In-memory knowledge graph + algorithms
│   ├── notification/   # Webhook, email, Slack dispatch
│   ├── pipeline/       # Multi-phase pipeline engine
│   ├── playbook/       # Rule-based response engine
│   ├── scoring/        # Threat scoring (0–100)
│   ├── source/         # CTI source clients
│   └── storage/        # SQLite + PostgreSQL backends
├── web/            # Dashboard (single-page app)
└── output/         # JSON, HTML, Markdown formatters

tests/              # 1,600+ tests
deploy/helm/        # Kubernetes Helm chart
samples/            # Synthetic IOC sample data
```

More detail: [Architecture.md](./Architecture.md).

---

## 🧪 Testing

```bash
# All tests
uv run pytest -q

# With coverage report
uv run pytest --cov=intelgraph --cov-report=html

# A single file
uv run pytest tests/cli/test_pipeline.py -v
```

---

## 📚 Documentation

- [Architecture](./Architecture.md): system design and components
- [Deployment](./deploy/helm/intelgraph/README.md): Docker and Kubernetes
- [Changelog](./CHANGELOG.md): what's changed in this fork
- [Roadmap](./ROADMAP.md): planned work
- [Limitations](./LIMITATIONS.md): known limitations
- [Contributing](./CONTRIBUTING.md): development guide
- [Security Policy](./SECURITY.md): responsible disclosure

---

## 🔒 Security

⚠️ **Please do not report security issues in public GitHub issues.** Follow [SECURITY.md](./SECURITY.md) instead.

---

## 🤝 Contributing

Contributions are welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md) for setup, testing requirements and the pull request process.

For improvements to the core platform, also consider contributing upstream to the [original project](https://github.com/Berkayy123-h/intelgraph).

---

## 📜 License

Released under the **MIT License**. See [LICENSE](./LICENSE).

Copyright © 2026 **Berkay Altıntaş** (original work).
Fork modifications by **Ashvin Auti**, also under the MIT License.

---

## 📞 Contact

- **This fork:** [ashvinauti/intelgraph](https://github.com/ashvinauti/intelgraph), maintained by Ashvin Auti ([issues](https://github.com/ashvinauti/intelgraph/issues))
- **Original project:** [Berkayy123-h/intelgraph](https://github.com/Berkayy123-h/intelgraph), by Berkay Altıntaş

⭐ If this project helps you, please star both this fork and the [original repository](https://github.com/Berkayy123-h/intelgraph).
