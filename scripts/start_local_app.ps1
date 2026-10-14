param(
    [ValidateSet("Backend", "Frontend")]
    [string]$Service,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

try {
    if ($Service) {
        $Host.UI.RawUI.WindowTitle = "JUSTICE-KP Local $Service - keep this window open"
        # These process settings also override inherited Tailscale launch values.
        # Saved .env files and the Windows environment are not modified.
        $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
        $env:ALLOWED_ORIGINS = "http://127.0.0.1:3000,http://localhost:3000"
        Remove-Item Env:TAILSCALE_HOSTNAME -ErrorAction SilentlyContinue
        Write-Host "Local website: http://127.0.0.1:3000"
        Write-Host "Leave this window open. Press Ctrl+C to stop the $Service."
        if ($Service -eq "Backend") {
            & (Join-Path $PSScriptRoot "run_backend_dev.ps1")
        } else {
            & (Join-Path $PSScriptRoot "run_frontend_dev.ps1")
        }
        return
    }

    foreach ($requiredPath in @(
        (Join-Path $projectRoot ".venv\Scripts\python.exe"),
        (Join-Path $projectRoot "frontend\node_modules\next\package.json"),
        (Join-Path $PSScriptRoot "run_backend_dev.ps1"),
        (Join-Path $PSScriptRoot "run_frontend_dev.ps1")
    )) {
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "Required file is missing: $requiredPath. Complete the local app installation first."
        }
    }
    Get-Command node.exe, npm.cmd -ErrorAction Stop | Out-Null

    $listeners = @(netstat -ano -p tcp | Select-String -Pattern ':(3000|8000)\s+\S+\s+LISTENING\s+')
    if ($listeners.Count -gt 0) {
        throw "Port 3000 or 8000 is already in use. Stop both existing JUSTICE-KP server windows with Ctrl+C before switching to local mode."
    }
    Write-Host "Local startup checks passed. Website: http://127.0.0.1:3000"
    if ($CheckOnly) {
        return
    }

    $powershellExe = Join-Path $PSHOME "powershell.exe"
    foreach ($serviceName in @("Backend", "Frontend")) {
        $arguments = '-NoLogo -NoProfile -NoExit -ExecutionPolicy Bypass -File "{0}" -Service {1}' -f $PSCommandPath, $serviceName
        Start-Process -FilePath $powershellExe -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Normal | Out-Null
    }
    Write-Host "Opened both local server terminals. Wait for startup, then open the website."
} catch {
    Write-Host "Startup stopped: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
