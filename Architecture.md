# IntelGraph — Architecture

> **Note:** This document describes the current implementation. For the original design intent, see [Vision.md](./Vision.md) and [Mission.md](./Mission.md).

## High-Level Architecture Diagram (Text)

```
┌─────────────────────────────────────────────────────────┐
│                        CLI Layer                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ collect  │  │  graph   │  │  verify  │  │ report │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───┬────┘  │
└───────┼──────────────┼──────────────┼────────────┼──────┘
        │              │              │            │
┌───────┴──────────────┴──────────────┴────────────┴──────┐
│                    Orchestration Layer                    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Task Queue │  │  Source Mgr  │  │  Pipeline Exec │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
└─────────┼─────────────────┼──────────────────┼──────────┘
          │                 │                  │
┌─────────┴─────────────────┴──────────────────┴──────────┐
│                    Collection Layer                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │   OTX    │ │  Shodan  │ │ VirusTotal│ | URLhaus │    │
│  │ (REST)   │ │ (REST)   │ │ (REST)    │ | (CSV)   │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘    │
└───────┼──────────────┼──────────────┼───────────┼───────┘
        │              │              │           │
┌───────┴──────────────┴──────────────┴───────────┴───────┐
│                   Entity + Evidence Layer                 │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐      │
│  │ Entities │  │ EvidenceChain│  │  Confidence   │      │
│  │ (ULID)   │  │ (per alert)  │  │  Scoring      │      │
│  └────┬─────┘  └──────┬───────┘  └───────┬───────┘      │
└───────┼──────────────┼──────────────────┼──────────────┘
        │              │                  │
┌───────┴──────────────┴──────────────────┴──────────────┐
│              In-Memory Knowledge Graph                    │
│  ┌────────────┐  ┌────────────┐  ┌─────────────────┐     │
│  │  Nodes     │  │   Edges    │  │ Graph Algorithms│     │
│  │ (entities) │  │(relations) │  │(centrality, etc)│     │
│  └─────┬──────┘  └─────┬──────┘  └────────┬────────┘     │
└────────┼───────────────┼───────────────────┼──────────────┘
         │               │                   │
┌────────┴───────────────┴───────────────────┴──────────────┐
│                     Storage Layer                           │
│  ┌────────────┐  ┌────────────────┐  ┌─────────────────┐   │
│  │ SQLite     │  │  PostgreSQL    │  │  Evidence Store │   │
│  │ (default)  │  │  (prod/optional)│  │  + Audit Trail  │   │
│  └────────────┘  └────────────────┘  └─────────────────┘   │
└────────────────────────────────────────────────────────────┘
                           │
┌───────────────────────────┴───────────────────────────────┐
│                     Output Layer                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ STIX 2.1 │  │ GraphML │  │   JSON   │  │   CSV    │  │
│  │ /TAXII   │  │  /GEXF  │  │  Export  │  │  Export  │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└────────────────────────────────────────────────────────────┘
```

## Layered Architecture Principles

### 1. Strict Separation of Concerns
Each layer has exactly one responsibility. No layer crosses boundaries.

### 2. Dependency Direction
Dependencies flow downward. CLI depends on Core. Core depends on Storage. No upward dependencies.

### 3. In-Memory Graph
The knowledge graph is an in-memory adjacency-list structure (`IntelligenceGraph` in `core/graph/graph.py`). Nodes and edges are loaded from the storage layer into memory for analysis. Algorithms (centrality, anomaly, attack path, prediction) operate on the in-memory graph directly. Persistence is handled by the storage layer.

### 4. Event-Driven Pipeline
Each phase emits events. Downstream phases subscribe. Phases can be added, removed, or reordered without changing other phases.

### 5. Immutable Data Flow
Once a collector produces data, that raw data is never modified. Normalization creates new normalized records. Original raw data is preserved for audit.

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python 3.11+ | Best OSINT ecosystem, wide library support |
| CLI Framework | Click | Battle-tested, composable, well-documented |
| Storage (default) | SQLite | Zero-config, portable, sufficient for development |
| Storage (prod) | PostgreSQL | Mature, reliable, excellent JSON support (optional) |
| Graph | In-memory | Fast analysis, algorithm-friendly, load from storage on demand |
| Output Format | JSON (canonical) | Universal, composable, machine-readable |
| Auth | JWT (HS256) + TOTP 2FA | Standard, portable, no external auth service needed |
| Export | STIX 2.1 / TAXII 2.1 | Industry standard for CTI sharing |
| Logging | structlog | Structured, JSON-serializable, correlation IDs |

## Project Structure (Actual)

```
intelgraph/
├── pyproject.toml
├── .env.example
├── README.md
├── intelgraph/
│   ├── __init__.py
│   ├── __main__.py              # CLI entry point (Click group)
│   ├── api/                     # FastAPI application
│   │   ├── main.py              # App factory, middleware, static files
│   │   ├── auth.py              # JWT, 2FA, OAuth2 login/register
│   │   ├── authz_middleware.py  # RBAC + multi-tenant middleware
│   │   ├── rate_limit.py         # Sliding-window rate limiter
│   │   ├── models.py            # Pydantic request/response models
│   │   ├── dependencies.py      # ServiceContainer (DI)
│   │   └── routers/             # REST endpoints
│   │       ├── dashboard.py     # /dashboard/ summary + SSE
│   │       ├── monitoring.py    # /metrics/ performance + health
│   │       ├── export_graph.py  # /export/graph GraphML/GEXF/JSON/CSV
│   │       ├── notifications.py # /notifications/channels + history
│   │       ├── reports.py       # /reports generate + list
│   │       ├── auth_2fa.py      # /auth/2fa/*
│   │       ├── oauth.py         # /oauth/token, register, refresh
│   │       ├── taxii.py         # /taxii/* STIX 2.1 / TAXII 2.1
│   │       ├── graph_anomaly.py # /graph/anomaly/*
│   │       ├── graph_analytics.py
│   │       ├── graph_attack_path.py
│   │       ├── graph_reasoning.py
│   │       ├── graph_prediction.py
│   │       ├── graph_nlp.py
│   │       └── ...
│   ├── cli/                     # 18 Click subcommands
│   │   ├── collect.py
│   │   ├── graph.py
│   │   ├── verify.py
│   │   ├── report.py
│   │   ├── source.py
│   │   ├── anomaly.py
│   │   ├── attack_path.py
│   │   ├── prediction.py
│   │   └── ...
│   ├── core/                    # Core intelligence engine
│   │   ├── config.py            # YAML config loader
│   │   ├── logging.py           # structlog setup
│   │   ├── correlation.py       # CorrelationID propagation
│   │   ├── collection/          # Collector framework
│   │   │   ├── base.py          # BaseCollector interface
│   │   │   ├── http_collector.py
│   │   │   ├── api_collector.py
│   │   │   ├── file_collector.py
│   │   │   ├── rss_collector.py
│   │   │   ├── web_scraper.py
│   │   │   ├── manager.py
│   │   │   └── retry.py
│   │   ├── entity/              # Entity models (ULID-based)
│   │   │   ├── base.py          # BaseEntity (id, provenance, confidence)
│   │   │   ├── ip_address.py
│   │   │   ├── domain.py
│   │   │   ├── cve.py
│   │   │   ├── certificate.py
│   │   │   ├── person.py
│   │   │   ├── company.py
│   │   │   ├── email.py
│   │   │   ├── username.py
│   │   │   └── technology.py
│   │   ├── evidence_chain/     # Evidence construction & confidence
│   │   ├── evidence/            # Evidence store
│   │   ├── export/              # Output formats
│   │   │   └── stix.py          # STIX 2.1 Bundle export (stix2 lib)
│   │   ├── graph/               # In-memory knowledge graph
│   │   │   ├── graph.py         # IntelligenceGraph (adjacency list)
│   │   │   ├── node.py
│   │   │   ├── edge.py
│   │   │   ├── algorithms.py    # Centrality, communities
│   │   │   ├── analytics.py
│   │   │   ├── anomaly.py       # AnomalyDetector
│   │   │   ├── attack_path.py
│   │   │   ├── influence.py
│   │   │   ├── prediction.py
│   │   │   ├── reasoning.py
│   │   │   ├── query.py
│   │   │   └── storage.py       # GraphStorage (FTS5 full-text search)
│   │   ├── source/              # CTI source clients
│   │   │   ├── otx.py           # AlienVault OTX (REST) + URLhaus CSV
│   │   │   ├── shodan.py        # Shodan (REST)
│   │   │   ├── virustotal.py    # VirusTotal (REST)
│   │   │   ├── manager.py
│   │   │   └── connector.py
│   │   ├── storage/             # Persistence backends
│   │   │   ├── backend.py       # BaseBackend interface
│   │   │   ├── sqlite_backend.py
│   │   │   ├── postgres_backend.py
│   │   │   ├── models.py
│   │   │   ├── migration.py
│   │   │   └── registry.py
│   │   ├── pipeline/            # Multi-phase pipeline
│   │   │   └── chain.py          # PipelineChain (orchestrates all phases)
│   │   ├── scoring/             # Threat scoring
│   │   │   └── threat_score.py  # 5-component score (0-100)
│   │   ├── playbook/            # Rule-based response engine
│   │   ├── notification/        # Webhook / email / Slack
│   │   ├── reporting/           # Jinja2 HTML reports
│   │   │   ├── reporters.py
│   │   │   ├── formatter.py
│   │   │   ├── scheduler.py
│   │   │   └── templates/
│   │   ├── auth/                # Authentication
│   │   │   └── totp.py          # TOTP 2FA (pyotp)
│   │   ├── multitenant/         # Tenant isolation & API keys
│   │   ├── enterprise/          # Observability & alerting
│   │   │   ├── observability.py # PerformanceCollector (psutil)
│   │   │   ├── alerting.py      # Threshold-based alerting
│   │   │   └── config_validator.py
│   │   ├── operations/          # Backup, health
│   │   ├── orchestrator/        # Task queue (Redis optional)
│   │   ├── human_review/        # Review queue
│   │   ├── verification/        # Verification manager
│   │   ├── explanation/         # Explainability engine
│   │   ├── explainability/      # Causal analysis
│   │   ├── safety/              # Safety governor
│   │   ├── governance/          # Governance
│   │   ├── kernel/              # Execution engine
│   │   ├── models/              # Shared data models
│   │   ├── features/            # Feature flags
│   │   ├── relationship/        # Relationship model
│   │   ├── source_registry/     # Source metadata registry
│   │   ├── nlp/                 # NLP processing
│   │   ├── cognitive/           # Cognitive reasoning
│   │   ├── agent/               # Autonomous agent
│   │   ├── metaintel/           # Meta-intelligence
│   │   └── ucos/                # Unified Cognitive OS
│   ├── web/                     # Dashboard
│   │   └── dashboard.html       # Single-page app (D3.js, Chart.js)
│   ├── output/                  # Output formatters
│   └── static/                  # Static assets (swagger)
├── tests/                       # 1,535+ tests
│   ├── api/
│   └── core/
├── docs/                        # Landing page + vercel.json
└── scripts/                     # Helper scripts
```

## Data Sources

| Source | Type | Module | API Key | Status |
|--------|------|--------|---------|--------|
| **AlienVault OTX** | REST API | `core/source/otx.py` | `OTX_API_KEY` | Active |
| **Shodan** | REST API | `core/source/shodan.py` | `SHODAN_API_KEY` | Active |
| **VirusTotal** | REST API | `core/source/virustotal.py` | `VIRUSTOTAL_API_KEY` | Active |
| **URLhaus** | CSV import | `core/source/otx.py` (`fetch_urlhaus_iocs`) | None | Active (CSV) |
| **CISA KEV** | — | — | — | Planned |

## Architectural Invariants

1. Every entity MUST have a globally unique ID (ULID)
2. Every relationship MUST reference two entity IDs
3. Every evidence item MUST reference an entity or relationship ID
4. Raw data is immutable once stored
5. All state changes MUST be logged
6. Every operation MUST carry a correlation ID
7. The knowledge graph is in-memory; persistence is delegated to the storage layer