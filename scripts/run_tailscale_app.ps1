param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Backend", "Frontend")]
    [string]$Service
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "JUSTICE-KP $Service - keep this window open"
$tailscaleExe = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
if (-not (Test-Path -LiteralPath $tailscaleExe)) {
    throw "Install Tailscale for Windows and sign in first."
}
$statusJson = & $tailscaleExe status --json
if ($LASTEXITCODE -ne 0) {
    throw "Cannot read Tailscale status. Try an Administrator PowerShell terminal."
}
$status = $statusJson | ConvertFrom-Json
if ($status.BackendState -ne "Running" -or -not $status.Self.DNSName) {
    throw "Connect this PC to Tailscale before starting the app."
}
$tailscaleHostname = $status.Self.DNSName.TrimEnd(".")
if ($tailscaleHostname -notmatch '^[a-zA-Z0-9.-]+\.ts\.net$') {
    throw "Tailscale did not return a valid HTTPS hostname."
}
$appUrl = "https://$tailscaleHostname"

# These settings apply only to this process and its child server. No .env files
# or Tailscale sharing settings are changed by this launcher.
if ($Service -eq "Backend") {
    $port = 8000
    $settings = @{
        ALLOWED_ORIGINS = "$appUrl,http://127.0.0.1:3000,http://localhost:3000"
        ALLOW_LOCAL_SHUTDOWN = "false"
    }
    $launcher = Join-Path $PSScriptRoot "run_backend_dev.ps1"
} else {
    $port = 3000
    $settings = @{
        NEXT_PUBLIC_API_BASE_URL = "${appUrl}:8443"
        TAILSCALE_HOSTNAME = $tailscaleHostname
    }
    $launcher = Join-Path $PSScriptRoot "run_frontend_dev.ps1"
}

$listeners = @(netstat -ano -p tcp | Select-String -Pattern ":$port\s+\S+\s+LISTENING\s+")
if ($listeners.Count -gt 0) {
    throw "Port $port is already in use. Stop the existing $Service terminal first so the Tailscale settings can take effect."
}

$savedSettings = @{}
$originalLocation = Get-Location
try {
    foreach ($name in $settings.Keys) {
        $savedSettings[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $settings[$name], "Process")
    }
    Write-Host "JUSTICE-KP private app URL: $appUrl"
    Write-Host "Wait for both servers to finish starting, then open the URL above."
    Write-Host "Leave this window open. Press Ctrl+C here to stop the $Service."
    Write-Host "Requires Tailscale Serve: HTTPS 443 -> localhost:3000; HTTPS 8443 -> localhost:8000."
    & $launcher
} finally {
    foreach ($name in $savedSettings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedSettings[$name], "Process")
    }
    Set-Location $originalLocation
}
