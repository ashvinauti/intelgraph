# IntelGraph Lab — Isolated Network (Layer 1)

Terraform for a **contained AWS lab network** that hosts the adversary-emulation
range. This is the foundation you build *before* adding any "malicious"
emulation: get the containment boundary right first.

> **Safety model.** This network is for **defensive testing** — running benign
> adversary *emulation* (synthetic IOC telemetry, beacon-style traffic patterns)
> to exercise IntelGraph's detection. It is designed so that emulated traffic
> **cannot escape to the public internet or third parties**: workloads have no
> public IPs, and all egress is default-deny behind an AWS Network Firewall
> allowlist that permits only OS/package/container-image registries. Do not use
> it to reach, scan, or attack anything outside the lab.

## What it creates

```
                          Internet
                             │
                        [ IGW ]  public subnets ── NAT gateway(s)
                             │
                     [ Network Firewall ]  firewall subnets
                       (egress allowlist)
                             │
                     workload subnets  ── range hosts (no public IP)
                             │
     VPC endpoints: SSM / SSMMessages / EC2Messages / ECR / Logs / S3(gw)
     VPC Flow Logs ─► CloudWatch    Firewall ALERT logs ─► CloudWatch
```

- **VPC** (`10.100.0.0/16` by default) across `az_count` AZs, three subnet
  tiers per AZ: `public` (NAT only), `firewall` (Network Firewall endpoints),
  `workload` (private hosts).
- **Controlled egress**: workload default route → Network Firewall endpoint →
  NAT → IGW. The firewall's stateful policy is **default-drop**, passing only
  `allowed_egress_domains` (TLS SNI / HTTP Host). Toggle with
  `enable_egress_firewall`.
- **No inbound** from the internet to workloads; management is via **SSM
  Session Manager** through interface VPC endpoints (no SSH, no bastion).
- **Observability**: VPC Flow Logs (ALL) and firewall ALERT logs to CloudWatch —
  the record of the range's simulated traffic, and a feed source for IntelGraph.

## Prerequisites

- Terraform >= 1.6, AWS provider ~> 5.40
- AWS credentials for a **non-production, isolated account** (strongly
  recommended — keep the range out of any account with real assets)
- Permissions for VPC, EC2, Network Firewall, IAM (flow-log role), CloudWatch Logs

## Apply

```bash
cd deploy/aws/network
cp terraform.tfvars.example terraform.tfvars   # edit region / prefix / domains

terraform init
terraform fmt -check
terraform validate
terraform plan -out tf.plan
terraform apply tf.plan
```

Outputs (`vpc_id`, `workload_subnet_ids`, `workload_security_group_id`, …) are
consumed by **Layer 2** (the emulation range) via `terraform_remote_state` or by
passing them in as variables.

## Verifying containment

After apply, from a workload host (opened with `aws ssm start-session`):

```bash
curl -m 5 https://registry.npmjs.org        # should TIME OUT / be blocked
curl -m 5 https://<an-allowlisted-domain>    # should succeed
```

Blocked attempts appear in the firewall ALERT log group. Adjust the allowlist
only by editing `allowed_egress_domains` — never by widening routes or SGs.

## Cost note

NAT gateways and AWS Network Firewall are billed hourly plus data processing.
Run `terraform destroy` when the lab is idle. `single_nat_gateway = true`
(default) keeps a lab to one NAT.

## Teardown

```bash
terraform destroy
```
