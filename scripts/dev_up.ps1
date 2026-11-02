$root = Split-Path -Parent $PSScriptRoot
$env:ENABLE_TEST_ENDPOINTS = "1"
# local development keys only (never reuse outside this machine)
$env:API_KEYS = "dev-l1-key-01:ops.alice:L1,dev-lead-key-1:lead.bob:TEAM_LEAD,dev-mgr-key-01:mgr.carol:MANAGER"
$ports = [ordered]@{ "ingest-service" = 40000; "retrieval-service" = 40001; "llm-gateway" = 40002; "ops-tools-service" = 40003; "agent-service" = 40004; "eval-service" = 40005; "api-gateway" = 40006 }
foreach ($name in $ports.Keys) {
  $port = $ports[$name]
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($proc -and $proc.ProcessName -like "python*") { Stop-Process -Id $proc.Id -Force } elseif ($proc) { Write-Host "port $port is held by $($proc.ProcessName) (pid $($proc.Id)); leaving it alone" } }
  $dir = Join-Path $root "services\$name"
  if (-not (Test-Path (Join-Path $dir "app\main.py"))) { continue }
  Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$dir'; & '$root\.venv\Scripts\Activate.ps1'; uvicorn app.main:app --port $port"
}
Start-Sleep -Seconds 10
try { Invoke-RestMethod -Uri http://127.0.0.1:40000/v1/ingest -Method Post | Out-Null; Write-Host "ingested corpus" } catch { Write-Host "ingest failed: $_" }