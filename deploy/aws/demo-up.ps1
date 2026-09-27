<#
.SYNOPSIS
  One-command bring-up of the IntelGraph isolated adversary-emulation lab on AWS.

.DESCRIPTION
  Provisions Layer 1 (isolated network) and Layer 2 (emulation range), builds and
  pushes the IntelGraph container image to ECR, ensures the analytics node is
  serving, pushes a synthetic threat-intel feed, and opens the dashboard.

  Safe to re-run: Terraform is declarative and the container/feed steps are
  idempotent. Run it ~20 minutes before your demo so everything is warm.

.EXAMPLE
  .\demo-up.ps1
  .\demo-up.ps1 -Region eu-west-2 -Campaigns 10 -LocalPort 8001
  .\demo-up.ps1 -SkipBuild          # reuse an image already in ECR

.NOTES
  Prereqs (install once): terraform, aws CLI, docker desktop (running),
  AWS Session Manager plugin. AWS creds configured (aws configure).
#>
[CmdletBinding()]
param(
  [string]$Region      = "eu-west-2",
  [string]$NamePrefix  = "intelgraph-lab",
  [int]   $Campaigns   = 8,
  [int]   $LocalPort   = 8001,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$PluginBin = "C:\Program Files\Amazon\SessionManagerPlugin\bin"
if (Test-Path $PluginBin) { $env:Path = "$PluginBin;$env:Path" }

$Aws      = $PSScriptRoot                              # deploy/aws
$Network  = Join-Path $Aws "network"
$Range    = Join-Path $Aws "range"
$RepoRoot = (Resolve-Path (Join-Path $Aws "..\..")).Path

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [ok] $m"    -ForegroundColor Green }
function Die($m)  { Write-Host "  [FAIL] $m"  -ForegroundColor Red; exit 1 }
function Assert-Exit($what) { if ($LASTEXITCODE -ne 0) { Die "$what (exit $LASTEXITCODE)" } }

# --- Prereqs ----------------------------------------------------------------
Step "Checking prerequisites"
foreach ($t in "terraform","aws","docker") {
  if (-not (Get-Command $t -ErrorAction SilentlyContinue)) { Die "'$t' not found on PATH. Install it and reopen PowerShell." }
}
if (-not (Test-Path (Join-Path $PluginBin "session-manager-plugin.exe"))) {
  Die "Session Manager plugin not found. Install from https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html"
}
docker info *> $null; if ($LASTEXITCODE -ne 0) { Die "Docker is not running. Start Docker Desktop and retry." }
$Account = (aws sts get-caller-identity --query Account --output text); Assert-Exit "aws sts get-caller-identity (are your credentials set?)"
Ok "AWS account $Account, region $Region"
$Image = "$Account.dkr.ecr.$Region.amazonaws.com/intelgraph:latest"

# --- SSM RunCommand helper --------------------------------------------------
function Invoke-SSM {
  param([Parameter(Mandatory)][string]$InstanceId,
        [Parameter(Mandatory)][string[]]$Commands,
        [int]$TimeoutSec = 600)
  $pf = New-TemporaryFile
  @{ commands = @($Commands) } | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii $pf
  $fileArg = "file://" + ($pf.FullName -replace '\\','/')
  $cmdId = (aws ssm send-command --region $Region --instance-ids $InstanceId `
              --document-name "AWS-RunShellScript" --comment "intelgraph-demo" `
              --parameters $fileArg --query "Command.CommandId" --output text)
  Remove-Item $pf -Force
  if (-not $cmdId -or $LASTEXITCODE -ne 0) { Die "SSM send-command failed on $InstanceId" }
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  do {
    Start-Sleep -Seconds 6
    $status = (aws ssm get-command-invocation --region $Region --command-id $cmdId --instance-id $InstanceId --query "Status" --output text 2>$null)
  } while (($status -in @("Pending","InProgress","Delayed","")) -and ((Get-Date) -lt $deadline))
  $out = (aws ssm get-command-invocation --region $Region --command-id $cmdId --instance-id $InstanceId --query "StandardOutputContent" --output text 2>$null)
  $err = (aws ssm get-command-invocation --region $Region --command-id $cmdId --instance-id $InstanceId --query "StandardErrorContent" --output text 2>$null)
  return [pscustomobject]@{ Status = $status; Out = $out; Err = $err }
}

# --- Layer 1: isolated network ---------------------------------------------
Step "Layer 1: isolated network (VPC + firewall + endpoints)"
"region      = ""$Region""`nname_prefix = ""$NamePrefix""" | Set-Content -Encoding ascii (Join-Path $Network "terraform.tfvars")
terraform -chdir="$Network" init -input=false; Assert-Exit "terraform init (network)"
terraform -chdir="$Network" apply -auto-approve -input=false; Assert-Exit "terraform apply (network)"
$net = terraform -chdir="$Network" output -json | ConvertFrom-Json
$VpcId   = $net.vpc_id.value
$Subnets = $net.workload_subnet_ids.value
$SgId    = $net.workload_security_group_id.value
$SubnetsHcl = '["' + ($Subnets -join '","') + '"]'
Ok "VPC $VpcId, workload SG $SgId"

# --- Image: build & push to ECR --------------------------------------------
if ($SkipBuild) {
  Step "Image: skipping build (-SkipBuild); using $Image"
} else {
  Step "Image: build & push to ECR"
  aws ecr describe-repositories --repository-names intelgraph --region $Region *> $null
  if ($LASTEXITCODE -ne 0) { aws ecr create-repository --repository-name intelgraph --region $Region *> $null; Assert-Exit "ecr create-repository" }
  (aws ecr get-login-password --region $Region) | docker login --username AWS --password-stdin "$Account.dkr.ecr.$Region.amazonaws.com"; Assert-Exit "docker login to ECR"
  docker build -t $Image $RepoRoot; Assert-Exit "docker build"
  docker push $Image; Assert-Exit "docker push"
  Ok "Pushed $Image"
}

# --- Layer 2: emulation range ----------------------------------------------
Step "Layer 2: emulation range (analytics + c2 + victim)"
$Secret = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
@"
region      = "$Region"
name_prefix = "$NamePrefix"

vpc_id                     = "$VpcId"
workload_subnet_ids        = $SubnetsHcl
workload_security_group_id = "$SgId"

intelgraph_image      = "$Image"
intelgraph_secret_key = "$Secret"

enable_c2_node          = true
enable_victim_node      = true
beacon_interval_seconds = 60
sim_campaigns           = $Campaigns
sim_interval_minutes    = 10
"@ | Set-Content -Encoding ascii (Join-Path $Range "terraform.tfvars")
terraform -chdir="$Range" init -input=false; Assert-Exit "terraform init (range)"
terraform -chdir="$Range" apply -auto-approve -input=false; Assert-Exit "terraform apply (range)"
$rng = terraform -chdir="$Range" output -json | ConvertFrom-Json
$AnalyticsId = $rng.analytics_instance_id.value
$AnalyticsIp = $rng.analytics_private_ip.value
$C2Id        = $rng.c2_instance_id.value
Ok "analytics $AnalyticsId ($AnalyticsIp), c2 $C2Id"

# --- Wait for SSM to register the nodes ------------------------------------
Step "Waiting for nodes to come online (SSM)"
$deadline = (Get-Date).AddMinutes(6)
do {
  Start-Sleep -Seconds 10
  $online = (aws ssm describe-instance-information --region $Region `
              --filters "Key=InstanceIds,Values=$AnalyticsId,$C2Id" `
              --query "length(InstanceInformationList[?PingStatus=='Online'])" --output text 2>$null)
  Write-Host "  online nodes: $online / 2"
} while (($online -ne "2") -and ((Get-Date) -lt $deadline))
if ($online -ne "2") { Die "Nodes did not register with SSM in time. Check the console." }
Ok "Nodes online"

# --- Ensure IntelGraph is serving (idempotent) -----------------------------
Step "Ensuring IntelGraph is running on the analytics node"
$ensure = @(
  "set -e",
  "sudo systemctl enable --now docker",
  "aws ecr get-login-password --region $Region | sudo docker login --username AWS --password-stdin $Account.dkr.ecr.$Region.amazonaws.com",
  "sudo docker pull $Image",
  "sudo docker rm -f intelgraph >/dev/null 2>&1 || true",
  "sudo docker run -d --restart unless-stopped --name intelgraph -p 8000:8000 -e INTELGRAPH_SECRET_KEY='$Secret' -e INTELGRAPH_DEPLOYMENT=lab $Image",
  "for i in `$(seq 1 30); do c=`$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/ || true); if [ -n `"`$c`" ] && [ `"`$c`" != '000' ]; then echo serving=`$c; exit 0; fi; sleep 5; done; echo 'not-serving'; exit 1"
)
$r = Invoke-SSM -InstanceId $AnalyticsId -Commands $ensure -TimeoutSec 600
if ($r.Status -ne "Success") { Write-Host $r.Out; Write-Host $r.Err -ForegroundColor Yellow; Die "IntelGraph did not come up on analytics node." }
Ok "IntelGraph serving ($($r.Out.Trim()))"

# --- Push a synthetic feed from the c2 node --------------------------------
Step "Pushing a synthetic threat-intel feed from the c2 node"
$seed = Get-Random -Maximum 99999
$feed = @(
  "set -e",
  "aws ecr get-login-password --region $Region | sudo docker login --username AWS --password-stdin $Account.dkr.ecr.$Region.amazonaws.com",
  "sudo docker pull $Image",
  "sudo docker run --rm $Image uv run intelgraph simulate network --seed $seed --campaigns $Campaigns --overlap 0.5 --ipv6 --feed --base-url http://$AnalyticsIp`:8000"
)
$r2 = Invoke-SSM -InstanceId $C2Id -Commands $feed -TimeoutSec 600
if ($r2.Status -ne "Success") { Write-Host $r2.Out; Write-Host $r2.Err -ForegroundColor Yellow; Die "Feed run failed on c2 node." }
Ok "Feed delivered (seed $seed, $Campaigns campaigns)"

# --- Open the dashboard ----------------------------------------------------
Step "Opening the dashboard"
$fwd = "`$env:Path='$PluginBin;'+`$env:Path; Write-Host 'IntelGraph tunnel - keep this window open. Ctrl+C to stop.' -ForegroundColor Cyan; aws ssm start-session --region $Region --target $AnalyticsId --document-name AWS-StartPortForwardingSession --parameters 'portNumber=8000,localPortNumber=$LocalPort'"
Start-Process powershell -ArgumentList "-NoExit","-Command",$fwd
Start-Sleep -Seconds 8
Start-Process "http://localhost:$LocalPort/"

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " IntelGraph lab is READY for the demo" -ForegroundColor Green
Write-Host "   Dashboard : http://localhost:$LocalPort/" -ForegroundColor Green
Write-Host "   Analytics : $AnalyticsId ($AnalyticsIp)" -ForegroundColor Green
Write-Host "   C2 node   : $C2Id" -ForegroundColor Green
Write-Host "   Tunnel    : running in a separate window (leave it open)" -ForegroundColor Green
Write-Host "`n Show more live data during the demo:  .\demo-feed.ps1" -ForegroundColor Yellow
Write-Host " Tear everything down afterwards:      .\demo-down.ps1" -ForegroundColor Yellow
Write-Host "============================================================`n" -ForegroundColor Green
