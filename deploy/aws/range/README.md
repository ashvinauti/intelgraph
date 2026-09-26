# IntelGraph Lab — Adversary-Emulation Range (Layer 2)

Deploys the range **inside** the isolated network from
[`../network`](../network/). Three private EC2 hosts, managed by SSM (no SSH,
no public IPs), run IntelGraph plus **benign adversary emulation**.

> **What "malicious" means here.** This range emulates adversary *behaviour* to
> exercise detection — it does **not** run real malware, exploits, or any
> traffic to systems outside the lab. The "C2" node is a static HTTP listener
> plus a timer that feeds IntelGraph synthetic, documentation-space IOC
> campaigns (`intelgraph simulate network`). The "victim" node beacons only to
> the C2 node's private IP. Egress stays default-deny behind the network layer's
> firewall. Keep it that way; don't point it at anything real.

## Topology

```
        (all private, intra-VPC only, egress allowlisted)

  victim  ──beacon:8080──►  c2 (emulation)  ──simulate --feed──►  analytics
   node                       │  static HTTP panel                  │ IntelGraph
                              └─ every N min: synthetic IOC feed ───►  API :8000
```

- **analytics** — IntelGraph API + graph on `:8000` (the system under test).
- **c2** — harmless `python -m http.server` "panel" on `:8080`, and a systemd
  timer running `intelgraph simulate network --feed` at `sim_interval_minutes`.
- **victim** — systemd service curling the C2 panel every `beacon_interval_seconds`.

## Prerequisites

1. **Deploy Layer 1 first** (`../network`) and note its outputs.
2. **Build & push the image** (registry host must be in the network layer's
   `allowed_egress_domains` — `.amazonaws.com` for ECR is allowed by default):
   ```bash
   aws ecr create-repository --repository-name intelgraph
   ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
   REGION=us-east-1
   REPO="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/intelgraph"
   aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
   docker build -t "$REPO:latest" .          # from repo root
   docker push "$REPO:latest"
   ```

## Apply

```bash
cd deploy/aws/range
cp terraform.tfvars.example terraform.tfvars   # fill vpc_id/subnets/sg/image/secret

terraform init && terraform validate
terraform plan -out tf.plan
terraform apply tf.plan
```

Wiring the network outputs in automatically (instead of copy/paste) — add to a
`remote_state.tf`:

```hcl
data "terraform_remote_state" "network" {
  backend = "local"
  config  = { path = "../network/terraform.tfstate" }
}
# then reference:
#   vpc_id                     = data.terraform_remote_state.network.outputs.vpc_id
#   workload_subnet_ids        = data.terraform_remote_state.network.outputs.workload_subnet_ids
#   workload_security_group_id = data.terraform_remote_state.network.outputs.workload_security_group_id
```

## Use it

Open the IntelGraph UI over an SSM port-forward (no inbound exposure):

```bash
aws ssm start-session --target <analytics_instance_id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["8000"],"localPortNumber":["8000"]}'
# then browse http://localhost:8000/
```

The graph fills automatically as the C2 node's timer pushes synthetic campaigns.
Trigger one immediately from the C2 host:

```bash
aws ssm start-session --target <c2_instance_id>
sudo /usr/local/bin/ig-simulate
```

Inspect the emulated callbacks in the VPC Flow Logs group from Layer 1.

## Teardown

```bash
terraform destroy          # this layer first
cd ../network && terraform destroy
```
