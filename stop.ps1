# stop.ps1 — stop all containers
# Run this from the octo_scrape folder: .\stop.ps1

docker compose down
Write-Host "Containers stopped."
