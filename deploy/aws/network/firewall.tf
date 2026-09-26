# AWS Network Firewall enforcing a default-deny egress allowlist. This is the
# containment boundary for the range: workloads can only reach the exact
# domains in var.allowed_egress_domains; everything else is dropped.

locals {
  # Map AZ name -> firewall VPC endpoint id, used by the workload default routes.
  firewall_endpoints = var.enable_egress_firewall ? {
    for ss in tolist(aws_networkfirewall_firewall.this[0].firewall_status[0].sync_states) :
    ss.availability_zone => one(ss.attachment).endpoint_id
  } : {}
}

resource "aws_networkfirewall_rule_group" "egress_allowlist" {
  count    = var.enable_egress_firewall ? 1 : 0
  capacity = 128
  name     = "${var.name_prefix}-egress-allowlist"
  type     = "STATEFUL"

  rule_group {
    rules_source {
      rules_source_list {
        generated_rules_type = "ALLOWLIST"
        target_types         = ["TLS_SNI", "HTTP_HOST"]
        targets              = var.allowed_egress_domains
      }
    }

    stateful_rule_options {
      rule_order = "STRICT_ORDER"
    }
  }

  tags = { Name = "${var.name_prefix}-egress-allowlist" }
}

resource "aws_networkfirewall_firewall_policy" "this" {
  count = var.enable_egress_firewall ? 1 : 0
  name  = "${var.name_prefix}-policy"

  firewall_policy {
    stateless_default_actions          = ["aws:forward_to_sfe"]
    stateless_fragment_default_actions = ["aws:forward_to_sfe"]

    # Default-deny for stateful traffic; only the allowlist rule group passes.
    stateful_default_actions = ["aws:drop_established", "aws:alert_established"]

    stateful_engine_options {
      rule_order = "STRICT_ORDER"
    }

    stateful_rule_group_reference {
      priority     = 1
      resource_arn = aws_networkfirewall_rule_group.egress_allowlist[0].arn
    }
  }

  tags = { Name = "${var.name_prefix}-policy" }
}

resource "aws_networkfirewall_firewall" "this" {
  count               = var.enable_egress_firewall ? 1 : 0
  name                = "${var.name_prefix}-fw"
  firewall_policy_arn = aws_networkfirewall_firewall_policy.this[0].arn
  vpc_id              = aws_vpc.this.id

  dynamic "subnet_mapping" {
    for_each = aws_subnet.firewall
    content {
      subnet_id = subnet_mapping.value.id
    }
  }

  tags = { Name = "${var.name_prefix}-fw" }
}

# Firewall alert/flow logs to CloudWatch for visibility into blocked egress.
resource "aws_cloudwatch_log_group" "firewall_alert" {
  count             = var.enable_egress_firewall ? 1 : 0
  name              = "/${var.name_prefix}/networkfirewall/alert"
  retention_in_days = var.flow_log_retention_days
}

resource "aws_networkfirewall_logging_configuration" "this" {
  count        = var.enable_egress_firewall ? 1 : 0
  firewall_arn = aws_networkfirewall_firewall.this[0].arn

  logging_configuration {
    log_destination_config {
      log_destination = {
        logGroup = aws_cloudwatch_log_group.firewall_alert[0].name
      }
      log_destination_type = "CloudWatchLogs"
      log_type             = "ALERT"
    }
  }
}
