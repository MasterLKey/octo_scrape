# start.ps1 — fetch secrets from Infisical and start the containers
# Run this from the octo_scrape folder: .\start.ps1

$env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + [System.Environment]::GetEnvironmentVariable('PATH', 'User')

$projectId = "7d764c71-0e3a-47ab-914c-40e4767a67d8"

Write-Host "Fetching secrets from Infisical..."
$env:OCTOPUS_API_KEY   = (infisical secrets get OCTOPUS_API_KEY   --projectId=$projectId --plain --silent 2>$null).Trim()
$env:OCTOPUS_EMAIL     = (infisical secrets get OCTOPUS_EMAIL     --projectId=$projectId --plain --silent 2>$null).Trim()
$env:OCTOPUS_PASSWORD  = (infisical secrets get OCTOPUS_PASSWORD  --projectId=$projectId --plain --silent 2>$null).Trim()
$env:POSTGRES_PASSWORD = (infisical secrets get POSTGRES_PASSWORD --projectId=$projectId --plain --silent 2>$null).Trim()
$env:SECRET_KEY        = (infisical secrets get SECRET_KEY        --projectId=$projectId --plain --silent 2>$null).Trim()

if (-not $env:POSTGRES_PASSWORD) {
    Write-Error "Failed to fetch secrets from Infisical. Are you logged in? Run: infisical login"
    exit 1
}

Write-Host "Secrets loaded. Starting containers..."
docker compose up -d

Write-Host ""
Write-Host "Done! Open http://localhost:8000 to access the dashboard."
