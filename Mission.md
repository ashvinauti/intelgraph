# IntelGraph — Mission

## Mission Statement

Build a production-grade, open-source threat intelligence platform that correlates indicators from multiple threat feeds into a structured knowledge graph with explainable, evidence-backed alerts — ready for SOC investigations and STIX-based sharing.

## Core Objectives

1. **Multi-Source Correlation** — Ingest and cross-reference IOCs from live CTI APIs (OTX, VirusTotal, Shodan), CSV feeds (URLhaus), and structured vulnerability data (CISA KEV).
2. **Evidence-Backed Intelligence** — Every entity and relationship carries source provenance, confidence scores, and traceable evidence chains.
3. **Knowledge Graph Engine** — In-memory temporal graph with full-text search, anomaly detection, threat scoring (0-100), and attack path analysis.
4. **SOC-Ready Integration** — REST API for IOC enrichment, STIX 2.1 / TAXII 2.1 export, investigation workspace with pivot engine, and automated playbook responses.
5. **Enterprise Security** — JWT + 2FA (TOTP) + OAuth2 authentication, tenant isolation with API key rotation, sliding-window rate limiting, and audit logging.

## Current State (Phase 42)

- **1580 tests passing**, 0 failures
- **5 threat sources**: OTX, VirusTotal, Shodan, URLhaus (CSV), CISA KEV
- **REST API**: 38 routers, FastAPI with SSE metrics streaming
- **Live dashboard**: Chart.js + D3.js interactive visualization
- **Landing page**: intelgraph.vercel.app

## Non-Goals

- Private data scraping or credential harvesting
- Active scanning without authorization
- Real-time streaming beyond SSE metrics
- Machine learning-based classification (threat scoring uses statistical models)