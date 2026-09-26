# Layer 2: the adversary-emulation range. Private EC2 hosts in the isolated
# network run IntelGraph (detection) plus BENIGN emulation:
#   * analytics : IntelGraph API + graph (the thing under test)
#   * c2        : a harmless in-VPC "C2 panel" listener + a timer that pushes
#                 synthetic IOC campaigns into IntelGraph via `simulate network`
#   * victim    : beacons to the c2 node on an interval (intra-VPC traffic only)
#
# There is no real malware, no exploits, and no traffic to anything outside the
# lab VPC. Egress remains default-deny behind the network layer's firewall.

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  ami_id = data.aws_ssm_parameter.al2023.value
  # Place emulation nodes in the first workload subnet; analytics too, so all
  # intra-lab traffic stays within one AZ (simple + cheap for a lab).
  subnet_id = var.workload_subnet_ids[0]
}

# --- IAM: SSM-managed instances (no SSH keys) -------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${var.name_prefix}-node"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "node" {
  name = "${var.name_prefix}-node"
  role = aws_iam_role.node.name
}

# --- Instances --------------------------------------------------------------

resource "aws_instance" "analytics" {
  ami                    = local.ami_id
  instance_type          = var.analytics_instance_type
  subnet_id              = local.subnet_id
  vpc_security_group_ids = [var.workload_security_group_id]
  iam_instance_profile   = aws_iam_instance_profile.node.name

  user_data = templatefile("${path.module}/templates/analytics.sh.tftpl", {
    intelgraph_image = var.intelgraph_image
    secret_key       = var.intelgraph_secret_key
  })

  metadata_options {
    http_tokens   = "required" # IMDSv2 only
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = 30
    encrypted   = true
  }

  tags = {
    Name = "${var.name_prefix}-analytics"
    Role = "analytics"
  }
}

resource "aws_instance" "c2" {
  count                  = var.enable_c2_node ? 1 : 0
  ami                    = local.ami_id
  instance_type          = var.emulation_instance_type
  subnet_id              = local.subnet_id
  vpc_security_group_ids = [var.workload_security_group_id]
  iam_instance_profile   = aws_iam_instance_profile.node.name

  user_data = templatefile("${path.module}/templates/c2.sh.tftpl", {
    intelgraph_image = var.intelgraph_image
    analytics_ip     = aws_instance.analytics.private_ip
    sim_campaigns    = var.sim_campaigns
    sim_interval_min = var.sim_interval_minutes
  })

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = 20
    encrypted   = true
  }

  tags = {
    Name = "${var.name_prefix}-c2"
    Role = "c2-emulation"
  }
}

resource "aws_instance" "victim" {
  count                  = var.enable_victim_node && var.enable_c2_node ? 1 : 0
  ami                    = local.ami_id
  instance_type          = var.emulation_instance_type
  subnet_id              = local.subnet_id
  vpc_security_group_ids = [var.workload_security_group_id]
  iam_instance_profile   = aws_iam_instance_profile.node.name

  user_data = templatefile("${path.module}/templates/victim.sh.tftpl", {
    c2_ip           = aws_instance.c2[0].private_ip
    beacon_interval = var.beacon_interval_seconds
  })

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = 20
    encrypted   = true
  }

  tags = {
    Name = "${var.name_prefix}-victim"
    Role = "victim-emulation"
  }
}
