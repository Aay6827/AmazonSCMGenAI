$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
docker version --format "{{.Server.Version}}" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "Docker is not running. Start Docker Desktop and try again."; exit 1 }
# free the ports used by the local (non-container) dev stack
foreach ($port in 40000..40006) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force } }
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "created .env from .env.example (local dev keys)" }
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait
if ($LASTEXITCODE -ne 0) { Write-Host "compose up failed. Try: docker compose logs --tail 40"; exit 1 }
docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T ingest-service python -c "import urllib.request as u; r = u.urlopen(u.Request('http://127.0.0.1:40000/v1/ingest', method='POST'), timeout=30); print('ingest status', r.status)"