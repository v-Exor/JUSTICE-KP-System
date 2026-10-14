param(
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$logDir = Join-Path $backendDir "logs"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDir "uvicorn-dev-$timestamp.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-BackendPortAvailable {
    $listener = $null
    try {
        $endpoint = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 8000)
        $listener = [System.Net.Sockets.TcpListener]::new($endpoint)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Get-NetstatPortOwner {
    $match = netstat -ano -p tcp | Select-String -Pattern "127\.0\.0\.1:8000\s+.*LISTENING\s+(\d+)" | Select-Object -First 1
    if ($match -and $match.Matches[0].Groups.Count -gt 1) {
        return [int]$match.Matches[0].Groups[1].Value
    }
    return $null
}

$existingListener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existingListener) {
    $existingPid = $existingListener.OwningProcess

    if ($ForceRestart) {
        Write-Host "Port 8000 is already used by process $existingPid. Stopping it because -ForceRestart was specified..."
        Stop-Process -Id $existingPid -Force
        Start-Sleep -Seconds 2
    } else {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200 -and $response.Content -match "JUSTICE-KP") {
                Write-Host "JUSTICE-KP backend is already running at http://127.0.0.1:8000"
                Write-Host "To restart it, run: .\scripts\run_backend_dev.ps1 -ForceRestart"
                exit 0
            }
        } catch {
            Write-Host "Port 8000 is already occupied by process $existingPid."
            Write-Host "Close that process or run: .\scripts\run_backend_dev.ps1 -ForceRestart"
            exit 1
        }
    }
}

if (-not (Test-BackendPortAvailable)) {
    $existingPid = Get-NetstatPortOwner
    if ($ForceRestart -and $existingPid) {
        Write-Host "Port 8000 is already used by process $existingPid. Stopping it because -ForceRestart was specified..."
        Stop-Process -Id $existingPid -Force
        Start-Sleep -Seconds 2
    } else {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000" -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200 -and $response.Content -match "JUSTICE-KP") {
                Write-Host "JUSTICE-KP backend is already running at http://127.0.0.1:8000"
                Write-Host "To restart it, run: .\scripts\run_backend_dev.ps1 -ForceRestart"
                exit 0
            }
        } catch {
            if ($existingPid) {
                Write-Host "Port 8000 is occupied by process $existingPid, but it did not respond as JUSTICE-KP."
            } else {
                Write-Host "Port 8000 is temporarily busy or locked by Windows."
            }
            Write-Host "Wait a few seconds and run again, or run: .\scripts\run_backend_dev.ps1 -ForceRestart"
            exit 1
        }
    }
}

Set-Location $backendDir
Write-Host "Starting JUSTICE-KP backend at http://127.0.0.1:8000"
Write-Host "Backend log: $logPath"
Start-Transcript -Path $logPath -Append | Out-Null
try {
    & $pythonExe -u dev_server.py
} finally {
    Stop-Transcript | Out-Null
}
