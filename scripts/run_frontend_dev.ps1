$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $projectRoot "frontend"

Set-Location $frontendDir

function Get-FrontendPortOwners {
  $owners = @(Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
  if ($owners.Count -eq 0) {
    $owners = @(netstat -ano -p tcp |
      Select-String -Pattern "(?:\[[^\]]+\]|\S+):3000\s+\S+\s+LISTENING\s+(\d+)\s*$" |
      ForEach-Object { [int]$_.Matches[0].Groups[1].Value } |
      Select-Object -Unique)
  }
  return $owners
}

$processIds = @(Get-FrontendPortOwners)
if ($processIds.Count -gt 0) {
  $processList = $processIds -join ", "
  Write-Host "Port 3000 is already in use by process ID(s): $processList" -ForegroundColor Yellow
  Write-Host "Stop that process first, then run this script again." -ForegroundColor Yellow
  exit 1
}

Write-Host "Starting JUSTICE-KP frontend at http://127.0.0.1:3000"
npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
