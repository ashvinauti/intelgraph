<#
.SYNOPSIS
  IntelGraph — one-stop setup & launcher for Windows 11.

.DESCRIPTION
  Installs the dependencies you need and starts IntelGraph, either:
    * LOCAL  — runs on this laptop with Python (via uv). No Docker, no cloud,
               no cost. Best for a quick look.
    * AWS    — deploys the full isolated adversary-emulation lab to AWS.
               (Needs an AWS account; incurs hourly cost while running.)

  Run it with no arguments for an interactive menu:

      powershell -ExecutionPolicy Bypass -File .\start.ps1

.PARAMETER Mode
  "local" or "aws" to skip the menu.

.PARAMETER Port
  Local web port (default 8000).

.NOTES
  Run from the repository root (the folder containing pyproject.toml).
  If scripts are blocked, launch with:  powershell -ExecutionPolicy Bypass -File .\start.ps1
#>
[CmdletBinding()]
param(
  [ValidateSet("local","aws","")]
  [string]$Mode = "",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Head($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [ok]   $m" -ForegroundColor Green }
function Info($m) { Write-Host "  [info] $m" -ForegroundColor Gray }
function Warn($m) { Write-Host "  [warn] $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "  [FAIL] $m" -ForegroundColor Red; exit 1 }

function Refresh-Path {
  $m = [System.Environment]::GetEnvironmentVariable("Path","Machine")
  $u = [System.Environment]::GetEnvironmentVariable("Path","User")
  $env:Path = "$m;$u"
}

function Ensure-Tool {
  param([string]$Cmd, [string]$WingetId, [string]$Friendly)
  if (Get-Command $Cmd -ErrorAction SilentlyContinue) { Ok "$Friendly already installed"; return $true }
  Info "Installing $Friendly (winget: $WingetId) ..."
  winget install --id $WingetId -e --source winget --accept-package-agreements --accept-source-agreements --silent 2>$null
  Refresh-Path
  if (Get-Command $Cmd -ErrorAction SilentlyContinue) { Ok "$Friendly installed"; return $true }
  Warn "$Friendly installed but not visible yet — you may need to reopen PowerShell."
  return $false
}

# --- sanity: run from repo root --------------------------------------------
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
  Die "Run this from the IntelGraph repo root (the folder with pyproject.toml). Current: $Root"
}

# --- winget present? --------------------------------------------------------
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  Die "winget not found. Install 'App Installer' from the Microsoft Store, then re-run this script."
}

Write-Host ""
Write-Host "  IntelGraph - Threat Intelligence Lab" -ForegroundColor Blue
Write-Host "  ------------------------------------" -ForegroundColor Blue

# --- choose mode ------------------------------------------------------------
if (-not $Mode) {
  Write-Host "`nWhat would you like to do?" -ForegroundColor White
  Write-Host "  [1] Run LOCALLY on this laptop   (Python via uv - no Docker, no cost)  <- recommended"
  Write-Host "  [2] Deploy to AWS                (full isolated cloud lab - hourly cost)"
  Write-Host "  [Q] Quit"
  $choice = Read-Host "`nEnter 1, 2, or Q"
  switch ($choice.Trim().ToUpper()) {
    "1" { $Mode = "local" }
    "2" { $Mode = "aws" }
    "Q" { Write-Host "Bye."; exit 0 }
    default { Die "Unrecognized choice '$choice'." }
  }
}

# ===========================================================================
# LOCAL MODE
# ===========================================================================
if ($Mode -eq "local") {
  Head "Local setup — installing Python toolchain (uv)"
  Ensure-Tool -Cmd "uv" -WingetId "astral-sh.uv" -Friendly "uv (Python manager)" | Out-Null
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Die "uv is not on PATH yet. Close PowerShell, reopen it, and run this script again."
  }

  Head "Provisioning Python 3.11 and dependencies"
  uv python install 3.11; if ($LASTEXITCODE -ne 0) { Die "uv python install failed." }
  Push-Location $Root
  uv sync --no-dev; if ($LASTEXITCODE -ne 0) { Pop-Location; Die "uv sync failed." }
  Pop-Location
  Ok "Dependencies installed"

  # Contain all app data under .\.localdata (auto-created by the app).
  $data = Join-Path $Root ".localdata"
  New-Item -ItemType Directory -Force -Path $data | Out-Null
  $env:INTELGRAPH_SECRET_KEY        = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
  $env:INTELGRAPH_DEPLOYMENT        = "local"
  $env:INTELGRAPH_STORAGE_PATH      = Join-Path $data "intelgraph.db"   # main graph SQLite file
  $env:INTELGRAPH_DB_PATH           = Join-Path $data "tenants.db"      # tenant registry SQLite file
  $env:INTELGRAPH_REPORT_DIR        = Join-Path $data "reports"
  $env:INTELGRAPH_TOTP_STATE        = Join-Path $data "totp_state.json"
  $env:INTELGRAPH_NOTIFICATION_STATE= Join-Path $data "notification_state.json"
  $env:INTELGRAPH_INVESTIGATION_STATE = Join-Path $data "investigations.json"

  Head "Starting the IntelGraph server"
  # Runs in its own window (inherits the env vars set above) so this script can
  # continue, seed data, and open the browser.
  $serverCmd = "cd '$Root'; Write-Host 'IntelGraph server - keep this window open (Ctrl+C to stop).' -ForegroundColor Cyan; uv run uvicorn intelgraph.api.main:app --host 127.0.0.1 --port $Port"
  Start-Process powershell -ArgumentList "-NoExit","-Command",$serverCmd

  Info "Waiting for the server to come up on http://127.0.0.1:$Port ..."
  $up = $false
  foreach ($i in 1..40) {
    Start-Sleep -Seconds 2
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 3 -MaximumRedirection 0 -ErrorAction Stop
      $up = $true; break
    } catch {
      # Any HTTP response (even 3xx/4xx) means it's listening.
      if ($_.Exception.Response) { $up = $true; break }
    }
  }
  if (-not $up) { Die "Server did not respond in time. Check the server window for errors." }
  Ok "Server is up"

  Head "Seeding synthetic threat-intel data"
  Push-Location $Root
  uv run intelgraph simulate network --seed 4242 --campaigns 8 --overlap 0.5 --ipv6 --feed --base-url "http://127.0.0.1:$Port"
  Pop-Location
  if ($LASTEXITCODE -ne 0) { Warn "Seeding hit an issue, but the server is running — you can still open the UI." }

  Start-Process "http://localhost:$Port/"
  Write-Host "`n============================================================" -ForegroundColor Green
  Write-Host " IntelGraph is running LOCALLY" -ForegroundColor Green
  Write-Host "   Dashboard : http://localhost:$Port/" -ForegroundColor Green
  Write-Host "   Server    : running in a separate PowerShell window" -ForegroundColor Green
  Write-Host "   Data dir  : $data" -ForegroundColor Green
  Write-Host "`n Add more synthetic data any time:" -ForegroundColor Yellow
  Write-Host "   uv run intelgraph simulate network --seed 7 --campaigns 10 --feed --base-url http://127.0.0.1:$Port" -ForegroundColor Yellow
  Write-Host " Stop it: close the server window (Ctrl+C)." -ForegroundColor Yellow
  Write-Host "============================================================`n" -ForegroundColor Green
  exit 0
}

# ===========================================================================
# AWS MODE
# ===========================================================================
if ($Mode -eq "aws") {
  Head "AWS setup — installing the cloud toolchain"
  Ensure-Tool -Cmd "terraform" -WingetId "Hashicorp.Terraform" -Friendly "Terraform" | Out-Null
  Ensure-Tool -Cmd "aws"       -WingetId "Amazon.AWSCLI"       -Friendly "AWS CLI"   | Out-Null
  Ensure-Tool -Cmd "docker"    -WingetId "Docker.DockerDesktop" -Friendly "Docker Desktop" | Out-Null

  # Session Manager plugin (no winget package — install from AWS if missing).
  $pluginExe = "C:\Program Files\Amazon\SessionManagerPlugin\bin\session-manager-plugin.exe"
  if (-not (Test-Path $pluginExe)) {
    Info "Installing AWS Session Manager plugin ..."
    $tmp = Join-Path $env:TEMP "SSMPluginSetup.exe"
    Invoke-WebRequest -Uri "https://session-manager-downloads.s3.amazonaws.com/plugin/latest/windows/SessionManagerPluginSetup.exe" -OutFile $tmp
    Start-Process $tmp -Wait
  }
  if (Test-Path $pluginExe) { Ok "Session Manager plugin present" } else { Warn "Session Manager plugin not detected." }
  Refresh-Path

  Head "Checking Docker and AWS credentials"
  $dockerOk = $false
  if (Get-Command docker -ErrorAction SilentlyContinue) { docker info *> $null; if ($LASTEXITCODE -eq 0) { $dockerOk = $true } }
  if (-not $dockerOk) {
    Warn "Docker Desktop is installed but not running (or needs a first-time setup/reboot)."
    Warn "Start Docker Desktop, wait until it says 'Engine running', then re-run:  .\start.ps1 -Mode aws"
    exit 1
  }
  Ok "Docker is running"

  $acct = $null
  if (Get-Command aws -ErrorAction SilentlyContinue) { $acct = (aws sts get-caller-identity --query Account --output text 2>$null) }
  if (-not $acct) {
    Warn "AWS credentials are not configured."
    Warn "Run:  aws configure   (enter Access Key, Secret Key, region e.g. eu-west-2)"
    Warn "Then re-run:  .\start.ps1 -Mode aws"
    exit 1
  }
  Ok "AWS account $acct"

  $region = Read-Host "AWS region to deploy into [eu-west-2]"
  if (-not $region) { $region = "eu-west-2" }

  Head "Launching the AWS lab (this takes ~12-15 minutes)"
  Info "The AWS Network Firewall alone takes ~8 min to create — this is normal."
  $demo = Join-Path $Root "deploy\aws\demo-up.ps1"
  if (-not (Test-Path $demo)) { Die "Could not find deploy\aws\demo-up.ps1 — is this the full repo?" }
  & $demo -Region $region
  exit $LASTEXITCODE
}
