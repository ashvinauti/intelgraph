variable "region" {
  description = "AWS region to deploy the isolated lab network into."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix applied to all resource names/tags. Keep it identifiable as a lab."
  type        = string
  default     = "intelgraph-lab"
}

variable "vpc_cidr" {
  description = "CIDR block for the isolated lab VPC. Use a private (RFC 1918) range."
  type        = string
  default     = "10.100.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid CIDR block."
  }
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across (2 recommended)."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 1 && var.az_count <= 3
    error_message = "az_count must be between 1 and 3."
  }
}

variable "single_nat_gateway" {
  description = "Use one NAT gateway (cheaper, fine for a lab) instead of one per AZ."
  type        = bool
  default     = true
}

variable "enable_egress_firewall" {
  description = <<-EOT
    Deploy AWS Network Firewall in front of NAT so egress is default-deny and
    only the domains in allowed_egress_domains are reachable. This is the
    'tight allowlist' that keeps the range's simulated traffic contained.
    When false, egress is controlled only by security groups (any HTTPS out
    via NAT), which is weaker containment.
  EOT
  type        = bool
  default     = true
}

variable "allowed_egress_domains" {
  description = <<-EOT
    Exact-match domains the range is permitted to reach when the egress
    firewall is enabled. Default covers OS/package/container-image pulls only.
    Do NOT add broad domains; the point is to keep the lab contained.
  EOT
  type        = list(string)
  default = [
    ".amazonaws.com", # ECR, S3, SSM (also covered by VPC endpoints)
    ".docker.io",     # Docker Hub
    ".docker.com",    # Docker Hub CDN
    "production.cloudflare.docker.com",
    ".ghcr.io",  # GitHub Container Registry
    ".pypi.org", # Python packages
    ".pythonhosted.org",
    ".ubuntu.com", # apt (Ubuntu)
    ".debian.org", # apt (Debian)
  ]
}

variable "flow_log_retention_days" {
  description = "CloudWatch Logs retention for VPC flow logs (the lab's traffic record)."
  type        = number
  default     = 30
}

variable "extra_tags" {
  description = "Additional tags merged onto every resource."
  type        = map(string)
  default     = {}
}
