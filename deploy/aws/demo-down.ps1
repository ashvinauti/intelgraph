<#
.SYNOPSIS
  Tear down the IntelGraph lab (both layers) to stop AWS billing.
.DESCRIPTION
  Destroys Layer 2 (range) then Layer 1 (network). Optionally deletes the ECR
  repository/image. Run this after the demo -- NAT + Network Firewall + EC2
  bill continuously.
.EXAMPLE
  .\demo-down.ps1
  .\demo-down.ps1 -DeleteImage      # also remove the ECR repo/image
#>
[CmdletBinding()]
param(
  [string]$Region = "eu-west-2",
  [switch]$DeleteImage
)
$ErrorActionPreference = "Stop"
$Network = Join-Path $PSScriptRoot "network"
$Range   = Join-Path $PSScriptRoot "range"

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }

Step "Destroying Layer 2: emulation range"
if (Test-Path (Join-Path $Range "terraform.tfstate")) {
  terraform -chdir="$Range" destroy -auto-approve -input=false
} else {
  Write-Host "  (no range state found, skipping)"
}

Step "Destroying Layer 1: isolated network"
if (Test-Path (Join-Path $Network "terraform.tfstate")) {
  terraform -chdir="$Network" destroy -auto-approve -input=false
} else {
  Write-Host "  (no network state found, skipping)"
}

if ($DeleteImage) {
  Step "Deleting ECR repository"
  aws ecr delete-repository --repository-name intelgraph --region $Region --force 2>$null
}

Write-Host "`nTeardown complete. Verify in the AWS console that no NAT gateway or" -ForegroundColor Green
Write-Host "Network Firewall remains (those are the main hourly charges)." -ForegroundColor Green
