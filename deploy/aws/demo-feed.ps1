<#
.SYNOPSIS
  Push another synthetic threat-intel feed into the running IntelGraph lab.
.DESCRIPTION
  Use during the demo to show live ingestion: each run generates a fresh set of
  synthetic campaigns (new random seed) and feeds them into the analytics node.
  The dashboard updates when you refresh it.
.EXAMPLE
  .\demo-feed.ps1
  .\demo-feed.ps1 -Campaigns 12
#>
[CmdletBinding()]
param(
  [string]$Region    = "eu-west-2",
  [int]   $Campaigns = 8
)
$ErrorActionPreference = "Stop"
$Range = Join-Path $PSScriptRoot "range"

function Die($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red; exit 1 }

$Account = (aws sts get-caller-identity --query Account --output text); if ($LASTEXITCODE -ne 0) { Die "AWS credentials not set." }
$Image   = "$Account.dkr.ecr.$Region.amazonaws.com/intelgraph:latest"

$rng = terraform -chdir="$Range" output -json | ConvertFrom-Json
if (-not $rng.c2_instance_id.value) { Die "No range outputs found. Run demo-up.ps1 first." }
$C2Id        = $rng.c2_instance_id.value
$AnalyticsIp = $rng.analytics_private_ip.value

$seed = Get-Random -Maximum 99999
Write-Host "Feeding IntelGraph: seed $seed, $Campaigns campaigns -> $AnalyticsIp" -ForegroundColor Cyan

$cmds = @(
  "set -e",
  "aws ecr get-login-password --region $Region | sudo docker login --username AWS --password-stdin $Account.dkr.ecr.$Region.amazonaws.com",
  "sudo docker run --rm $Image uv run intelgraph simulate network --seed $seed --campaigns $Campaigns --overlap 0.5 --ipv6 --feed --base-url http://$AnalyticsIp`:8000"
)
$pf = New-TemporaryFile
@{ commands = @($cmds) } | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii $pf
$fileArg = "file://" + ($pf.FullName -replace '\\','/')
$cmdId = (aws ssm send-command --region $Region --instance-ids $C2Id --document-name "AWS-RunShellScript" --comment "intelgraph-demo-feed" --parameters $fileArg --query "Command.CommandId" --output text)
Remove-Item $pf -Force
if (-not $cmdId) { Die "send-command failed." }

do {
  Start-Sleep -Seconds 6
  $status = (aws ssm get-command-invocation --region $Region --command-id $cmdId --instance-id $C2Id --query "Status" --output text 2>$null)
} while ($status -in @("Pending","InProgress","Delayed",""))

if ($status -eq "Success") {
  Write-Host "Feed delivered. Refresh the dashboard to see the new campaigns." -ForegroundColor Green
} else {
  $err = (aws ssm get-command-invocation --region $Region --command-id $cmdId --instance-id $C2Id --query "StandardErrorContent" --output text 2>$null)
  Write-Host $err -ForegroundColor Yellow
  Die "Feed failed (status $status)."
}
