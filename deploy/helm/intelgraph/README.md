# IntelGraph Helm Chart

Deploys the IntelGraph API (FastAPI + Uvicorn) to Kubernetes.

## Install

```bash
# Build and push the image referenced by values.image.repository/tag first,
# or override it inline:
helm install intelgraph ./deploy/helm/intelgraph \
  --set image.repository=ghcr.io/your-org/intelgraph \
  --set image.tag=0.2.0 \
  --set secrets.INTELGRAPH_SECRET_KEY=$(openssl rand -hex 32)
```

## Storage

- `storage.backend: sqlite` (default) provisions a `PersistentVolumeClaim` and is only
  safe with `replicaCount: 1` — SQLite does not support concurrent writers across pods.
- `storage.backend: postgres` expects an external Postgres reachable via
  `secrets.DATABASE_URL` (`postgresql://user:pass@host:5432/intelgraph`); no PVC is created.

## Secrets

`secrets.create: true` (default) renders a `Secret` from the `secrets.*` values —
`INTELGRAPH_SECRET_KEY` is required in that case. Set `secrets.create: false` and
`secrets.existingSecret: <name>` to reference a Secret managed outside this chart
(e.g. by an external-secrets operator) instead of passing raw values on the CLI.

## Values

See [`values.yaml`](values.yaml) for the full list of configurable parameters
(replica count, resources, ingress, autoscaling, probes, CTI source API keys, etc.).
