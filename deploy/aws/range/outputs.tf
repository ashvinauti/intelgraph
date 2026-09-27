output "analytics_private_ip" {
  description = "Private IP of the IntelGraph analytics node (API on :8000, VPC-internal)."
  value       = aws_instance.analytics.private_ip
}

output "analytics_instance_id" {
  description = "Instance id for `aws ssm start-session --target <id>`."
  value       = aws_instance.analytics.id
}

output "c2_private_ip" {
  description = "Private IP of the C2 emulation node (panel on :8080)."
  value       = try(aws_instance.c2[0].private_ip, null)
}

output "c2_instance_id" {
  description = "C2 emulation node instance id (null if disabled)."
  value       = try(aws_instance.c2[0].id, null)
}

output "victim_instance_id" {
  description = "Victim emulation node instance id (null if disabled)."
  value       = try(aws_instance.victim[0].id, null)
}

output "open_analytics_ui" {
  description = "How to reach the IntelGraph UI from your workstation."
  value       = "aws ssm start-session --target ${aws_instance.analytics.id} --document-name AWS-StartPortForwardingSession --parameters '{\"portNumber\":[\"8000\"],\"localPortNumber\":[\"8000\"]}' then open http://localhost:8000/"
}
