# Synthetic Malicious-Network Simulation

IntelGraph ships a **synthetic adversary-network simulator** for exercising
ingestion, entity extraction, and graph link-analysis with realistic — but
entirely fabricated — threat data. It is a defensive testing aid: it
generates data, it does **not** perform any network activity.

## Safety model

Every indicator the simulator emits is drawn from address space reserved for
documentation and testing, so nothing it produces resolves to or identifies
real infrastructure:

| Indicator | Source | Reserved by |
|-----------|--------|-------------|
| IPv4 | `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` | RFC 5737 (TEST-NET) |
| IPv6 | `2001:db8::/32` | RFC 3849 |
| Domains / URLs / emails | `example.com/.net/.org`, `.test`, `.invalid`, `.example` | RFC 2606 / 6761 |
| File hashes | Random hex of correct length | — (not real samples) |
| CVE IDs | Real, publicly disclosed, already-fixed issues | Included only so CVE extraction matches |

This invariant is enforced by a test that sweeps 50 seeds
(`tests/core/test_simulation.py::TestReservedSpaceInvariant`).

## Generate a simulation

```bash
# Print a seeded simulation (deterministic in --seed) to stdout
uv run intelgraph simulate network --seed 42 --campaigns 5 --indicators 10

# Write narrative text + a JSON manifest
uv run intelgraph simulate network --seed 42 --campaigns 5 -o sim --format both
#   -> sim.txt (pipeline-ingestible), sim.json (structured manifest)
```

Key options:

| Option | Meaning |
|--------|---------|
| `--seed` | Deterministic seed (same seed → identical output) |
| `--campaigns` | Number of distinct threat-actor campaigns |
| `--indicators` | Approximate indicators per campaign (≥ 3) |
| `--overlap` | Probability (0–1) a campaign reuses shared C2 infrastructure — higher values create more cross-campaign pivots for link analysis |
| `--ipv6` | Also emit RFC 3849 IPv6 C2 addresses |
| `--feed` / `--base-url` | Run the data through the pipeline and POST it to a running server's dashboard |

## Feed it into IntelGraph

### Local server

```bash
# Terminal 1: start the API
uv run uvicorn intelgraph.api.main:app --reload

# Terminal 2: generate + feed in one step
uv run intelgraph simulate network --seed 42 --campaigns 5 --feed

# ...or via the existing pipeline command using a written file
uv run intelgraph simulate network --seed 42 -o sim.txt
uv run intelgraph pipeline run --skip-urlhaus --file sim.txt
```

Open `http://localhost:8000/` to view the resulting graph.

### A server deployed on AWS

IntelGraph deploys to Kubernetes (e.g. Amazon EKS) via the Helm chart in
[`deploy/helm/intelgraph`](../deploy/helm/intelgraph/README.md). Once the API
is reachable — through an ALB/NLB ingress, or a temporary
`kubectl port-forward` — point the simulator at it with `--base-url`:

```bash
# Example: deploy to EKS (see the chart README for image/secret setup)
helm install intelgraph ./deploy/helm/intelgraph \
  --set image.repository=<your-ecr-repo>/intelgraph \
  --set image.tag=<tag> \
  --set secrets.INTELGRAPH_SECRET_KEY=$(openssl rand -hex 32)

# Reach it directly...
export IG_URL="https://intelgraph.<your-domain>"      # ingress hostname
# ...or tunnel to it for a quick test
kubectl port-forward svc/intelgraph 8000:8000 &
export IG_URL="http://localhost:8000"

# Feed the simulation into the AWS-hosted server
uv run intelgraph simulate network --seed 42 --campaigns 8 --overlap 0.5 \
  --feed --base-url "$IG_URL"
```

Notes for the AWS path:

- The feed uses a single HTTPS `POST` to `<base-url>/dashboard/feed`. Because
  all payload indicators are documentation-space, no real hosts are contacted
  regardless of the cluster's egress policy.
- Front the ingress with the same authn/authz you use for any IntelGraph
  endpoint; the simulator sends the request as-is and does not manage auth.
- For scale/load testing, drive indicator volume with `--campaigns` and
  `--indicators` (e.g. `--campaigns 50 --indicators 20`) and vary `--seed` per
  run to produce distinct datasets.

## Structured manifest

`--format json` (or `both`) emits a manifest describing every campaign and
indicator, flagged `"synthetic": true`, suitable for asserting expected graph
contents in automated tests.
