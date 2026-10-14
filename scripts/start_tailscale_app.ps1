param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$serviceLauncher = Join-Path $PSScriptRoot "run_tailscale_app.ps1"
$tailscaleExe = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"

try {
    foreach ($requiredPath in @(
        $tailscaleExe,
        $serviceLauncher,
        (Join-Path $PSScriptRoot "run_backend_dev.ps1"),
        (Join-Path $PSScriptRoot "run_frontend_dev.ps1"),
        (Join-Path $projectRoot ".venv\Scripts\python.exe"),
        (Join-Path $projectRoot "frontend\node_modules\next\package.json")
    )) {
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "Required file is missing: $requiredPath. Complete the local app/Tailscale installation first."
        }
    }
    Get-Command node.exe, npm.cmd -ErrorAction Stop | Out-Null

    $statusJson = & $tailscaleExe status --json
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot read Tailscale status. If access was denied, right-click Start JUSTICE-KP.cmd and choose Run as administrator."
    }
    $status = $statusJson | ConvertFrom-Json
    if ($status.BackendState -ne "Running" -or -not $status.Self.DNSName) {
        throw "Tailscale is disconnected. Open Tailscale, sign in/connect, then double-click the launcher again."
    }
    $tailscaleHostname = $status.Self.DNSName.TrimEnd(".")
    if ($tailscaleHostname -notmatch '^[a-zA-Z0-9.-]+\.ts\.net$') {
        throw "Tailscale did not return a valid HTTPS hostname."
    }

    $serveJson = & $tailscaleExe serve status --json
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot read Tailscale Serve settings. Check Tailscale before starting the app."
    }
    $serve = $serveJson | ConvertFrom-Json
    foreach ($route in @(
        @{ Port = "443"; Target = "http://127.0.0.1:3000" },
        @{ Port = "8443"; Target = "http://127.0.0.1:8000" }
    )) {
        $endpoint = "${tailscaleHostname}:$($route.Port)"
        $proxy = $serve.Web.$endpoint.Handlers.'/'.Proxy
        if (-not $serve.TCP.($route.Port).HTTPS -or $proxy -ne $route.Target) {
            throw "The HTTPS route on port $($route.Port) is missing or points elsewhere. Follow docs\Tailscale_Setup.md to configure it."
        }
    }

    # Check both ports before launching either server. Existing processes are
    # never stopped automatically because they might be handling a recording.
    $listeners = @(netstat -ano -p tcp | Select-String -Pattern ':(3000|8000)\s+\S+\s+LISTENING\s+')
    if ($listeners.Count -gt 0) {
        throw "Port 3000 or 8000 is already in use. If JUSTICE-KP is already running, use its existing windows. To restart, press Ctrl+C in both old server windows, then try again."
    }

    Write-Host "Startup checks passed."
    Write-Host "Website: https://$tailscaleHostname"
    if ($CheckOnly) {
        return
    }

    $powershellExe = Join-Path $PSHOME "powershell.exe"
    foreach ($service in @("Backend", "Frontend")) {
        # -File plus a quoted path supports project folders containing spaces.
        # These visible terminals are the user's controls for logs and Ctrl+C.
        $arguments = '-NoLogo -NoProfile -NoExit -ExecutionPolicy Bypass -File "{0}" -Service {1}' -f $serviceLauncher, $service
        Start-Process -FilePath $powershellExe -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Normal | Out-Null
    }
    Write-Host "Opened the backend and frontend terminals. Leave both running."
} catch {
    Write-Host "Startup stopped: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
