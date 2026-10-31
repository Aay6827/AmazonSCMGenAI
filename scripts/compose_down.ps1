Set-Location (Split-Path -Parent $PSScriptRoot)
docker compose -f docker-compose.yml -f docker-compose.test.yml down