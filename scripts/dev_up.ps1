$root = Split-Path -Parent $PSScriptRoot
$env:ENABLE_TEST_ENDPOINTS = "1"
$ports = [ordered]@{ "ingest-service" = 40000; "retrieval-service" = 40001; "llm-gateway" = 40002; "ops-tools-service" = 40003; "agent-service" = 40004; "eval-service" = 40005 }
foreach ($name in $ports.Keys) {
  $port = $ports[$name]
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
  $dir = Join-Path $root "services\$name"
  if (-not (Test-Path (Join-Path $dir "app\main.py"))) { continue }
  Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$dir'; & '$root\.venv\Scripts\Activate.ps1'; uvicorn app.main:app --port $port"
}
Start-Sleep -Seconds 8
try { Invoke-RestMethod -Uri http://localhost:40000/v1/ingest -Method Post | Out-Null; Write-Host "ingested corpus" } catch { Write-Host "ingest failed: $_" }