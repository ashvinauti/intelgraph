output "vpc_id" {
  description = "ID of the isolated lab VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "CIDR block of the lab VPC."
  value       = aws_vpc.this.cidr_block
}

output "workload_subnet_ids" {
  description = "Private workload subnets where range hosts are launched."
  value       = aws_subnet.workload[*].id
}

output "public_subnet_ids" {
  description = "Public subnets (NAT gateways only; no workloads)."
  value       = aws_subnet.public[*].id
}

output "workload_security_group_id" {
  description = "Baseline SG for range workloads (intra-VPC + allowlisted egress)."
  value       = aws_security_group.lab_workload.id
}

output "availability_zones" {
  description = "AZs the network spans."
  value       = local.azs
}

output "egress_firewall_enabled" {
  description = "Whether Network Firewall egress allowlisting is active."
  value       = var.enable_egress_firewall
}

output "allowed_egress_domains" {
  description = "Domains the range may reach (empty guarantee unless firewall enabled)."
  value       = var.enable_egress_firewall ? var.allowed_egress_domains : ["<any via NAT: firewall disabled>"]
}

output "flow_log_group" {
  description = "CloudWatch Logs group containing VPC flow logs."
  value       = aws_cloudwatch_log_group.flow.name
}
