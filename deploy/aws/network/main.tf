data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  common_tags = merge(
    {
      Project     = "intelgraph"
      Environment = "lab"
      Purpose     = "isolated-adversary-emulation-range"
      ManagedBy   = "terraform"
      Isolation   = var.enable_egress_firewall ? "egress-allowlist" : "nat-egress"
    },
    var.extra_tags,
  )

  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # Subnet tiers. Public hosts the NAT gateway(s); firewall hosts the Network
  # Firewall endpoints; workload hosts the (private, no public IP) range hosts.
  public_subnets   = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i)]
  firewall_subnets = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 10)]
  workload_subnets = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 20)]

  nat_count = var.single_nat_gateway ? 1 : var.az_count
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

# --- Subnets -----------------------------------------------------------------

resource "aws_subnet" "public" {
  count                   = var.az_count
  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.public_subnets[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.name_prefix}-public-${local.azs[count.index]}"
    Tier = "public"
  }
}

resource "aws_subnet" "firewall" {
  count             = var.enable_egress_firewall ? var.az_count : 0
  vpc_id            = aws_vpc.this.id
  cidr_block        = local.firewall_subnets[count.index]
  availability_zone = local.azs[count.index]

  tags = {
    Name = "${var.name_prefix}-firewall-${local.azs[count.index]}"
    Tier = "firewall"
  }
}

resource "aws_subnet" "workload" {
  count                   = var.az_count
  vpc_id                  = aws_vpc.this.id
  cidr_block              = local.workload_subnets[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.name_prefix}-workload-${local.azs[count.index]}"
    Tier = "workload"
  }
}

# --- NAT ---------------------------------------------------------------------

resource "aws_eip" "nat" {
  count  = local.nat_count
  domain = "vpc"
  tags   = { Name = "${var.name_prefix}-nat-eip-${count.index}" }
}

resource "aws_nat_gateway" "this" {
  count         = local.nat_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = { Name = "${var.name_prefix}-nat-${count.index}" }

  depends_on = [aws_internet_gateway.this]
}

# --- Route tables ------------------------------------------------------------

# Public subnets reach the internet directly via the IGW (NAT lives here).
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-rt-public" }
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count          = var.az_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Firewall subnets egress to the internet via NAT (post-inspection).
resource "aws_route_table" "firewall" {
  count  = var.enable_egress_firewall ? var.az_count : 0
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-rt-firewall-${local.azs[count.index]}" }
}

resource "aws_route" "firewall_default" {
  count                  = var.enable_egress_firewall ? var.az_count : 0
  route_table_id         = aws_route_table.firewall[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[var.single_nat_gateway ? 0 : count.index].id
}

resource "aws_route_table_association" "firewall" {
  count          = var.enable_egress_firewall ? var.az_count : 0
  subnet_id      = aws_subnet.firewall[count.index].id
  route_table_id = aws_route_table.firewall[count.index].id
}

# Workload subnets: default route goes to the Network Firewall endpoint (when
# enabled) so all egress is inspected/allowlisted, otherwise straight to NAT.
resource "aws_route_table" "workload" {
  count  = var.az_count
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.name_prefix}-rt-workload-${local.azs[count.index]}" }
}

resource "aws_route" "workload_default_firewall" {
  count                  = var.enable_egress_firewall ? var.az_count : 0
  route_table_id         = aws_route_table.workload[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  vpc_endpoint_id        = local.firewall_endpoints[local.azs[count.index]]
}

resource "aws_route" "workload_default_nat" {
  count                  = var.enable_egress_firewall ? 0 : var.az_count
  route_table_id         = aws_route_table.workload[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[var.single_nat_gateway ? 0 : count.index].id
}

resource "aws_route_table_association" "workload" {
  count          = var.az_count
  subnet_id      = aws_subnet.workload[count.index].id
  route_table_id = aws_route_table.workload[count.index].id
}
