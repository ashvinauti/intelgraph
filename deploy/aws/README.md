# IntelGraph on AWS — Isolated Adversary-Emulation Lab

Terraform for a **contained cyber-range** on AWS that runs IntelGraph against
**benign adversary emulation** — synthetic IOC telemetry and beacon-style
traffic used to exercise detection and graph analytics. It is a defensive
testing environment.

Built in two layers, applied in order:

| Layer | Directory | What it is |
|-------|-----------|------------|
| 1 | [`network/`](network/) | Isolated VPC: private workload subnets, controlled egress via NAT behind a **Network Firewall default-deny allowlist**, SSM management (no SSH), VPC Flow Logs. |
| 2 | [`range/`](range/) | EC2 hosts in that VPC: IntelGraph (analytics) + a benign C2-emulation node that feeds synthetic campaigns + a victim node that beacons intra-VPC. |

## Safety model (read before deploying)

- **Emulation, not attack.** No real malware, exploits, or scanning. The "C2"
  is a static HTTP listener plus IntelGraph's documentation-space simulator
  (`intelgraph simulate network`); the "victim" beacons only to the C2 node's
  private IP. All indicators use reserved ranges (RFC 5737 / 3849 / 2606).
- **Containment is the design.** Workloads have no public IPs. Egress is
  default-deny; only an explicit domain allowlist (OS/package/image registries)
  is permitted, enforced by AWS Network Firewall. Simulated traffic cannot reach
  the public internet or third parties.
- **Isolate the account.** Deploy into a dedicated non-production AWS account
  with no real assets. Run `terraform destroy` when idle (NAT + Network Firewall
  bill hourly).
- **Don't widen it.** Reaching, scanning, or attacking anything outside the lab
  is out of scope for this tooling — keep the allowlist tight and the routes
  private.

## Quick start

```bash
# Layer 1 — the isolated network
cd deploy/aws/network
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply

# Build & push the IntelGraph image (see range/README.md), then:
# Layer 2 — the emulation range
cd ../range
cp terraform.tfvars.example terraform.tfvars   # paste Layer 1 outputs + image
terraform init && terraform apply

# Reach the UI without exposing anything (SSM port-forward)
aws ssm start-session --target <analytics_instance_id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8000"],"localPortNumber":["8000"]}'
```

See each layer's README for details and teardown.

## One-command demo (Windows PowerShell)

For a hands-off demo, the scripts in this folder do everything end to end:

```powershell
# Bring the whole lab up: both layers, build+push image, feed data, open the UI.
# Run it ~20 min before the demo so it's warm. Idempotent; safe to re-run.
.\demo-up.ps1                      # or: .\demo-up.ps1 -Region eu-west-2 -Campaigns 10
.\demo-up.ps1 -SkipBuild           # reuse an image already in ECR (faster)

# During the demo: push more synthetic campaigns to show live ingestion.
.\demo-feed.ps1                    # refresh the dashboard afterwards

# After the demo: tear everything down to stop billing.
.\demo-down.ps1                    # add -DeleteImage to also remove the ECR repo
```

Prereqs (install once, then reopen PowerShell): `terraform`, `aws` CLI,
Docker Desktop (running), and the AWS Session Manager plugin, with credentials
configured via `aws configure`. `demo-up.ps1` checks all of these before it
starts and prints the dashboard URL when ready.
