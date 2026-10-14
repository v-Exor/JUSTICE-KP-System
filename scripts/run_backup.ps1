param(
  [string]$ApiBase = "http://127.0.0.1:8000",
  [string]$Username = "admin",
  [string]$Password
)

if (-not $Password) {
  throw "Pass -Password or use a secure scheduled-task secret store."
}

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$login = Invoke-RestMethod -Uri "$ApiBase/api/auth/login" -Method Post -WebSession $session -ContentType "application/json" -Body (@{
  username = $Username
  password = $Password
} | ConvertTo-Json)

$headers = @{ "X-CSRF-Token" = $login.csrf_token }
Invoke-RestMethod -Uri "$ApiBase/api/admin/backups/run" -Method Post -WebSession $session -Headers $headers
