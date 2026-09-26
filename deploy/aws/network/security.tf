# Baseline security group for range workloads. It permits free traffic WITHIN
# the lab (so emulated adversary/victim/C2 nodes can talk to each other and to
# the IntelGraph analytics node) and HTTPS egress (for image/package pulls,
# still subject to the Network Firewall allowlist). It has no ingress from
# outside the VPC. The range module attaches to this and adds specific rules.

resource "aws_security_group" "lab_workload" {
  name        = "${var.name_prefix}-workload"
  description = "Baseline lab workload SG: intra-VPC any, HTTPS egress only"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "All traffic within the lab VPC (intra-range communication)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "All traffic within the lab VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "HTTPS egress (allowlisted by Network Firewall when enabled)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTP egress for package mirrors (allowlisted by firewall)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name_prefix}-workload" }
}
