variable "region" {
  description = "AWS region (must match the network layer)."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for range resource names/tags."
  type        = string
  default     = "intelgraph-lab"
}

# --- Wiring from the network layer (Layer 1) --------------------------------

variable "vpc_id" {
  description = "Lab VPC id (network layer output vpc_id)."
  type        = string
}

variable "workload_subnet_ids" {
  description = "Private workload subnet ids (network layer output workload_subnet_ids)."
  type        = list(string)
}

variable "workload_security_group_id" {
  description = <<-EOT
    Baseline workload SG from the network layer. It already permits intra-VPC
    traffic (so range nodes talk to each other) and allowlisted egress only.
    All range hosts attach to it; that is the containment boundary.
  EOT
  type        = string
}

# --- Application ------------------------------------------------------------

variable "intelgraph_image" {
  description = <<-EOT
    Container image for IntelGraph (build from the repo Dockerfile and push to
    ECR or GHCR). Example:
      <acct>.dkr.ecr.<region>.amazonaws.com/intelgraph:latest
    The same image provides the `intelgraph simulate network` generator used by
    the C2 emulation node. The registry host must be in the network layer's
    allowed_egress_domains.
  EOT
  type        = string
}

variable "intelgraph_secret_key" {
  description = "INTELGRAPH_SECRET_KEY for the API node (generate with: openssl rand -hex 32)."
  type        = string
  sensitive   = true
}

# --- Instances --------------------------------------------------------------

variable "analytics_instance_type" {
  description = "Instance type for the IntelGraph analytics/detection node."
  type        = string
  default     = "t3.medium"
}

variable "emulation_instance_type" {
  description = "Instance type for the C2 and victim emulation nodes."
  type        = string
  default     = "t3.small"
}

# --- Emulation behaviour ----------------------------------------------------

variable "enable_c2_node" {
  description = "Deploy the benign C2-emulation + telemetry-generator node."
  type        = bool
  default     = true
}

variable "enable_victim_node" {
  description = "Deploy the victim node that beacons to the C2 node (intra-VPC only)."
  type        = bool
  default     = true
}

variable "beacon_interval_seconds" {
  description = "How often the victim node beacons to the C2 node (seconds)."
  type        = number
  default     = 60
}

variable "sim_campaigns" {
  description = "Campaigns per synthetic-simulation feed pushed into IntelGraph."
  type        = number
  default     = 6
}

variable "sim_interval_minutes" {
  description = "How often the C2 node pushes a fresh synthetic simulation to IntelGraph."
  type        = number
  default     = 10
}
