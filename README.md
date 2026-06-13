# Octo Scrape

Automated scraper for the Octopus Energy Cafe Nero free drink offer.
Logs in to your Octopus account, watches the offer page, automatically
accepts the free drink when available, and stores every scrape in PostgreSQL.
A browser-based GUI lets you configure the schedule and review history.

## Quick Start

### 1. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in your Octopus Energy email, password, and a strong
`POSTGRES_PASSWORD`. The `OFFER_URL` is pre-filled with your account's offer page.

### 2. Start the stack

```bash
docker compose up --build
```

The first start will:
- Pull PostgreSQL 16
- Build the backend image (installs Playwright + Chromium — takes a few minutes)
- Run database migrations automatically
- Start the FastAPI server on **http://localhost:8000**

### 3. Open the GUI

Navigate to **http://localhost:8000** in your browser.

- **Dashboard** — scrape history, manual trigger, HTML snapshots, diff viewer
- **Schedule** (`/schedule`) — set interval, daily time window, enable/disable

## How It Works

```
Scheduler fires every N minutes
  └─ Is current time within the configured window?
       ├─ No  → skip
       └─ Yes → launch headless Chromium
                 ├─ Log in to Octopus Energy
                 ├─ Navigate to offer URL
                 ├─ Capture full page HTML → store in PostgreSQL
                 ├─ Detect Cafe Nero "claim" button
                 │    ├─ Found → click it → mark offer_accepted=true
                 │    └─ Not found → mark offer_detected=false
                 └─ Compare HTML to previous snapshot → set page_changed flag
```

## Environment Variables

| Variable | Description |
|---|---|
| `OCTOPUS_EMAIL` | Your Octopus Energy login email |
| `OCTOPUS_PASSWORD` | Your Octopus Energy password |
| `OFFER_URL` | Full URL of the offer page |
| `POSTGRES_HOST` | DB host (`db` inside Docker) |
| `POSTGRES_PORT` | DB port (default `5432`) |
| `POSTGRES_DB` | Database name |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `SECRET_KEY` | App secret key |

## Updating the Offer Button Selector

Octopus Energy may change their page markup. If the offer stops being detected,
check `app/scraper.py` and update `OFFER_BUTTON_TEXTS` with text matching the
current button label on the offer page.

## Stopping

```bash
docker compose down          # stop containers, keep data
docker compose down -v       # stop and delete the database volume
```
