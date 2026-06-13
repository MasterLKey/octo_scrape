# Octo Scrape

Automated monitor for the Octopus Energy Café Nero free drink offer.
Watches the offer page with headless Chromium, automatically accepts the
free drink when it appears, and stores every scrape result in PostgreSQL.
A browser-based GUI lets you configure the schedule, manage authentication,
and review history.

---

## Architecture

```
FastAPI + APScheduler (backend)
  └─ PostgreSQL 16 (store scrape records + config)
  └─ Playwright / Chromium (headless browser)
       └─ Authenticates via browser session cookies
       └─ Navigates to offer URL
       └─ Detects & clicks the "claim" button
Infisical (secrets — never stored in repo)
Docker Compose (local dev)
Proxmox LXC + Terraform (home-lab deployment)
```

---

## Local Development

### Prerequisites

- Docker Desktop
- [Infisical CLI](https://infisical.com/docs/cli/overview) — `infisical login` before first run

### 1. Copy the env template

```bash
cp .env.example .env
```

`.env` holds only non-sensitive config (offer URL, DB connection details).
All secrets are fetched from Infisical at startup.

### 2. Start the stack (Windows)

```powershell
.\start.ps1
```

Or manually with Infisical injecting secrets:

```bash
infisical run --env=dev -- docker compose up --build
```

The first start:
- Pulls PostgreSQL 16
- Builds the backend image (installs Playwright + Chromium — takes a few minutes)
- Runs database migrations automatically
- Starts FastAPI on **http://localhost:8000**

### 3. Stop

```powershell
.\stop.ps1
```

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop and wipe the database
```

---

## Secrets (Infisical)

Secrets are **never** stored in the repo or `.env`. They live in an
[Infisical](https://infisical.com) project and are injected at runtime.

| Secret | Description |
|---|---|
| `OCTOPUS_EMAIL` | Octopus Energy login email |
| `OCTOPUS_PASSWORD` | Octopus Energy login password |
| `OCTOPUS_API_KEY` | API key from Account → Personal details |
| `POSTGRES_PASSWORD` | Database password |
| `SECRET_KEY` | Internal signing key (any strong random string) |

---

## Authentication — Session Cookies

Octopus Energy's dashboard is protected by OAuth 2.0 + hCAPTCHA, so the
scraper cannot log in programmatically with a username and password.
Instead it reuses a real browser session exported as cookies.

### How to set up cookies

1. Open **http://localhost:8000/session** (or the server URL)
2. Follow the on-screen instructions:
   - Install the [Cookie Editor](https://cookie-editor.com) browser extension
   - Log in to Octopus Energy in your browser
   - Export all cookies as JSON
   - Paste the JSON into the textarea and click **Save**
3. The scraper will load those cookies into Playwright on every run

### When cookies expire

The dashboard shows a **Session Expired** banner and scrape records show
`session_expired` status. Return to `/session`, export fresh cookies from
your browser, and save them again. Cookies typically last several weeks.

---

## Web UI

| Page | Path | Description |
|---|---|---|
| Dashboard | `/` | Scrape history, manual trigger, HTML diff viewer |
| Schedule | `/schedule` | Set interval, daily time window, enable/disable |
| Session | `/session` | Manage browser session cookies |

---

## Environment Variables (non-secret)

Stored in `.env` (safe to commit — no credentials):

| Variable | Default | Description |
|---|---|---|
| `OFFER_URL` | *(your offer URL)* | Full URL of the offer page |
| `POSTGRES_HOST` | `db` | DB host (Docker service name) |
| `POSTGRES_PORT` | `5432` | DB port |
| `POSTGRES_DB` | `octoscrape` | Database name |
| `POSTGRES_USER` | `octoscrape` | Database user |

---

## Home-Lab Deployment (Proxmox LXC via Terraform)

The `terraform/` directory provisions an Ubuntu 24.04 LXC container on Proxmox.

### Prerequisites on your workstation

- [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.6
- A Proxmox API token with sufficient permissions
- SSH key pair for the container

### 1. Configure variables

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Edit `terraform.tfvars` with your Proxmox host, API token, SSH public key, etc.

### 2. Apply

```bash
cd terraform
terraform init
terraform apply
```

Terraform will:
- Download the Ubuntu 24.04 LXC template from the Proxmox mirror
- Create an unprivileged LXC container (2 CPU, 2 GB RAM, 20 GB disk)
- Configure DHCP networking and inject your SSH key

### 3. Provision the container

SSH in and run the provision script:

```bash
ssh root@<container-ip>
bash /opt/octo_scrape/scripts/provision.sh
```

The script installs Docker, Infisical CLI, clones this repo, creates a
systemd service (`octo-scrape`), and starts the app automatically.

The app will be available at **http://\<container-ip\>:8000**.

---

## How It Works

```
Scheduler fires every N minutes (configured in /schedule)
  └─ Is current time within the configured window?
       ├─ No  → skip
       └─ Yes → launch headless Chromium
                 ├─ Load session cookies into browser context
                 ├─ Navigate directly to offer URL
                 ├─ Detect login-page redirect
                 │    └─ cookies expired → log warning, mark session_expired
                 ├─ Capture full page HTML → store in PostgreSQL
                 ├─ Detect Café Nero "claim" button
                 │    ├─ Found → click it → mark offer_accepted=true
                 │    └─ Not found → mark offer_detected=false
                 └─ Compare HTML to previous snapshot → set page_changed flag
```

## Updating the Offer Button Selector

If the scraper stops detecting the offer, check `app/scraper.py` and
update `OFFER_BUTTON_TEXTS` to match the current button label on the page.
