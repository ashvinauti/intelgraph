# IntelGraph

> IntelGraph is an **open-source threat intelligence platform** that helps SOC analysts and incident responders investigate threats by correlating indicators across multiple intelligence sources and explaining every alert with an evidence-based reasoning chain.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 1,580+](https://img.shields.io/badge/Tests-1580%2B-brightgreen.svg)](#testing)
[![Status: Active Development](https://img.shields.io/badge/Status-Active%20Development-yellow.svg)](#)

> This repository is based on the original [IntelGraph](https://github.com/Berkayy123-h/intelgraph) project by Berkay Altıntaş (MIT licensed). See [CHANGELOG.md](CHANGELOG.md) for what's new in this fork.

---

## Built With

✔ **1,580+** automated tests
✔ **3** live CTI source clients (OTX, Shodan, VirusTotal) + URLhaus CSV import
✔ **STIX 2.1** export compatible
✔ **Knowledge Graph** engine with temporal tracking (in-memory)
✔ **Real-time** enrichment & correlation  

---

## Use Cases

- **Investigate threats** - Suspicious IPs, domains, URLs, hashes, and CVEs from multiple intelligence sources
- **Correlate indicators** - Link related IOCs into an interactive knowledge graph
- **Reduce false positives** - Validate indicators across multiple trusted sources
- **Support investigations** - Explainable evidence chains for every alert
- **Share intelligence** - Export investigations as STIX 2.1 bundles for MISP, OpenCTI, or other platforms

---

## Why IntelGraph?

Unlike traditional threat intelligence platforms that only aggregate indicators, **IntelGraph explains WHY an IOC is malicious**.

| Feature | Description |
|---------|-------------|
| 🔗 **Multi-source Correlation** | Correlates data from multiple threat sources |
| 📋 **Evidence Chains** | Tracks provenance and reasoning |
| 📊 **Knowledge Graph** | Visualizes threat relationships |
| 🚨 **Contradiction Detection** | Identifies conflicting intelligence |
| 📤 **STIX Export** | Standards-compliant sharing |

### Positioning

IntelGraph complements existing CTI platforms by focusing on:

- **Explainable intelligence** - See why an indicator is malicious
- **Evidence-driven correlation** - Track the reasoning chain
- **Knowledge graph analysis** - Visualize threat relationships
- **Automated enrichment workflows** - Real-time data integration

**Compared with:**
- **OpenCTI** - Extensive CTI management platform
- **MISP** - Collaborative IOC sharing platform  
- **Commercial TIPs** - Enterprise intelligence suites

---

## 📸 Screenshots

### Pipeline Dashboard

![IntelGraph Pipeline Dashboard](screenshots/dashboard.jpg)

*IntelGraph Pipeline Dashboard — 131 nodes, 219 entities, live threat correlation*

---

## ✨ Core Features

### 📊 Multi-Source Pipeline
```
Active CTI source clients (REST APIs):
- OTX             # AlienVault community intelligence
- Shodan          # Internet-connected device data
- VirusTotal      # File / URL / domain reputation

CSV import:
- URLhaus         # Malicious URL feed (read from CSV)

Planned (not yet implemented):
- CISA KEV        # Known exploited vulnerabilities
```

### 🧠 Entity Processing
- **Custom NER** - Extracts threats from raw text
- **Deduplication** - O(n) hash-index matching
- **Confidence Scoring** - Evidence-based reliability
- **Contradiction Detection** - Conflicting intelligence alerts

### 📈 Temporal Knowledge Graph
- Timeline tracking of threat evolution
- Attack path visualization
- Relationship mapping
- Historical trend analysis

### ⚡ Real-Time Enrichment
```python
POST /api/v1/enrichment/ip
{"ip": "192.0.2.1"}
# Returns: Shodan data + reputation + CVEs
```

### 🔗 GraphQL API
```
POST /graphql   # entities, relationships, search — queries and mutations
```
An interactive GraphiQL IDE is served at the same path. See `intelgraph/api/graphql_schema.py`.

### 🤖 Automated Playbooks
- Event-driven response rules
- Alert enrichment workflows
- Webhook integration
- Custom automation framework

### 📱 Real-Time Dashboard
- D3.js force graph visualization
- Live data streaming (SSE)
- Full-text search
- Interactive threat correlation

### 🔐 Security Features
- JWT authentication
- Role-based access control
- Sliding-window rate limiting
- Audit logging

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- SQLite (default) or PostgreSQL

### Installation

```bash
git clone https://github.com/ashvinauti/intelgraph.git
cd intelgraph

uv sync
cp .env.example .env
```

### Configuration

Edit `.env`:
```env
DATABASE_URL=postgresql://user:pass@localhost/intelgraph
JWT_SECRET_KEY=your-secret-key
SHODAN_API_KEY=your-key
VIRUSTOTAL_API_KEY=your-key
```

### Run

```bash
# Local development
uv run uvicorn intelgraph.api.main:app --reload
# Open http://localhost:8000

# Docker
docker build -t intelgraph .
docker run -p 8000:8000 --env-file .env intelgraph

# Kubernetes (Helm)
helm install intelgraph ./deploy/helm/intelgraph \
  --set image.repository=<your-registry>/intelgraph \
  --set secrets.INTELGRAPH_SECRET_KEY=$(openssl rand -hex 32)
```

### Populate the dashboard with live data

A fresh install starts with an empty knowledge graph, so the Dashboard/Graph views show
zeros until you run the pipeline at least once. With the server running:

```bash
uv run intelgraph pipeline run
```

This pulls the live URLhaus "recent" feed (no API key needed), runs it through the
NLP/entity-extraction/graph pipeline, and feeds the result to the running server's
dashboard. Set `OTX_API_KEY` first to also include OTX pulses:

```bash
export OTX_API_KEY=your-otx-key   # optional
uv run intelgraph pipeline run --base-url http://localhost:8000
```

Use `--no-feed` to just see the extraction summary without updating the dashboard.

To feed it synthetic/sample IOC data instead of (or alongside) live feeds — useful
offline, for demos, or for testing entity extraction without touching real threat
feeds — use `--file` with `--skip-urlhaus`:

```bash
uv run intelgraph pipeline run --skip-urlhaus --file samples/synthetic_iocs.txt
```

`samples/synthetic_iocs.txt` uses only RFC 5737 documentation IP ranges and
`example.com`/`.org`/`.net` domains, so nothing in it resolves to real
infrastructure — safe to run, inspect, or extend with your own fake IOCs.
`--file` can be passed multiple times to combine several sources.

### Test

```bash
uv run pytest tests/ -v --cov=intelgraph
```

---

## 📊 Architecture

```
Threat Feeds (3 API clients + URLhaus CSV)
       │
       ▼
   Collectors
       │
       ▼
  Normalization
       │
       ▼
 Knowledge Graph
       │
   ┌───┴────┐
   ▼        ▼
Alerts  Investigation
   │        │
   └────┬───┘
        ▼
  STIX/TAXII Export
```

**Project Structure:**
```
intelgraph/
├── api/                  # FastAPI app, routers, auth, middleware
│   └── routers/          # REST endpoints (dashboard, metrics, export, etc.)
├── cli/                  # Click commands (18 subcommands)
├── core/                 # Core engine
│   ├── collection/        # Collector framework (HTTP, RSS, file, API)
│   ├── entity/           # Entity models (IP, domain, CVE, person, etc.)
│   ├── evidence_chain/   # Evidence construction & confidence scoring
│   ├── export/           # STIX 2.1 export
│   ├── graph/            # In-memory knowledge graph + algorithms
│   ├── multitenant/       # Tenant isolation & API key management
│   ├── notification/     # Webhook, email, Slack dispatch
│   ├── pipeline/         # Multi-phase pipeline engine
│   ├── playbook/         # Rule-based response engine
│   ├── reporting/        # Jinja2 HTML report generation
│   ├── scoring/          # Threat scoring (5-component, 0-100)
│   ├── source/           # CTI source clients (OTX, Shodan, VirusTotal)
│   └── storage/          # SQLite + PostgreSQL backends
├── web/                  # Dashboard HTML (single-page app)
└── output/               # Output formatters (JSON, HTML, Markdown)

tests/                   # 1,580+ tests
docs/                    # Landing page + deployment config
```

---

## 🔌 API Examples

### Search Threats
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/threats/search?q=ransomware"
```

### Enrich IP Address
```bash
curl -X POST http://localhost:8000/api/v1/enrichment/ip \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.0.2.1"}'

# Response:
# {
#   "ip": "192.0.2.1",
#   "shodan": {...},
#   "reputation": "malicious",
#   "cves": [...]
# }
```

### Export as STIX
```bash
curl http://localhost:8000/api/v1/export/stix?threat_id=threat_123
# Returns STIX 2.1 formatted JSON
```

### Knowledge Graph
```bash
curl http://localhost:8000/api/v1/graph/relationships?entity_id=malware_456
# Returns: Related entities, attack paths, timeline
```

---

## 🧪 Testing

```bash
# Run all tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=intelgraph --cov-report=html

# Specific module
uv run pytest tests/test_pipeline.py -v
```

**Coverage Target**: 100%  
**Current**: 95%+  
**Total Tests**: 1,580+

---

## 📚 Documentation

- **[Architecture](./Architecture.md)** - System design & components
- **[Deployment](./deploy/helm/intelgraph/README.md)** - Docker and Kubernetes (Helm) deployment
- **[API Reference](./README.md#-api-examples)** - Endpoint documentation
- **[Contributing](./CONTRIBUTING.md)** - Development guide
- **[Security Policy](./SECURITY.md)** - Responsible disclosure

---

## 🛣️ Roadmap

### v1.1 (Q3 2026)
- [ ] ML-based threat scoring
- [ ] Advanced anomaly detection
- [ ] Threat actor attribution
- [ ] Custom connector framework

### v1.2 (Q4 2026)
- [x] GraphQL API — see [CHANGELOG.md](./CHANGELOG.md)
- [x] Kubernetes Helm charts — see [deploy/helm/intelgraph](./deploy/helm/intelgraph)
- [ ] SIEM integrations (Splunk, ELK)

### v2.0 (2027)
- [ ] Distributed architecture
- [ ] Collaborative analysis features
- [ ] Decentralized intelligence sharing

**Note**: Roadmap items marked as planned (not yet implemented).

---

## 🔒 Security

⚠️ **For security issues**, please refer to [SECURITY.md](./SECURITY.md) - **Do NOT open public issues**.

### Security Features
- JWT-based authentication
- Role-based access control (RBAC)
- Rate limiting & DDoS protection
- Input validation & sanitization
- Audit logging

---

## 📞 Contact & Support

- **GitHub**: [ashvinauti/intelgraph](https://github.com/ashvinauti/intelgraph)
- **Issues**: [GitHub Issues](https://github.com/ashvinauti/intelgraph/issues)
- **Questions**: [GitHub Discussions](https://github.com/ashvinauti/intelgraph/discussions)
- **Original project**: [Berkayy123-h/intelgraph](https://github.com/Berkayy123-h/intelgraph)

---

## 📜 License

MIT License - See [LICENSE](./LICENSE) for details.

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for:
- Code of conduct
- Development setup
- Testing requirements
- Pull request process

---

## 📚 Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI, Uvicorn |
| API | REST, GraphQL (Strawberry) |
| Database | SQLite, PostgreSQL |
| Frontend | D3.js, Chart.js |
| Testing | pytest, 1,580+ tests |
| Standards | STIX 2.1 |
| Deployment | Docker, Kubernetes (Helm) |

---

**Questions?** Open an [issue](https://github.com/ashvinauti/intelgraph/issues) or start a [discussion](https://github.com/ashvinauti/intelgraph/discussions). This fork is based on the original [Berkayy123-h/intelgraph](https://github.com/Berkayy123-h/intelgraph).

⭐ If this project helps you, please consider starring it!
