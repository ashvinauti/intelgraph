# VPC endpoints so range hosts are manageable (SSM Session Manager, no SSH)
# and can pull container images/logs privately, without depending on the
# internet egress path. Interface endpoints live in the workload subnets.

locals {
  interface_endpoints = [
    "ssm",
    "ssmmessages",
    "ec2messages",
    "ecr.api",
    "ecr.dkr",
    "logs",
  ]
}

resource "aws_security_group" "endpoints" {
  name        = "${var.name_prefix}-vpce"
  description = "Allow HTTPS from the VPC to interface VPC endpoints"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTPS from within the lab VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "Endpoint responses within the VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  tags = { Name = "${var.name_prefix}-vpce" }
}

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(local.interface_endpoints)

  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = aws_subnet.workload[*].id
  security_group_ids  = [aws_security_group.endpoints.id]

  tags = { Name = "${var.name_prefix}-vpce-${each.value}" }
}

# S3 gateway endpoint (ECR layers and general S3) attached to workload routes.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.workload[*].id

  tags = { Name = "${var.name_prefix}-vpce-s3" }
}
