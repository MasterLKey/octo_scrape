# Octo Scrape — Design & Roadmap

This document records why things were built the way they were, what the
known rough edges are, and where the project could go next.

---

## Design Decisions

### Why Playwright instead of plain HTTP?

Octopus Energy's dashboard is a Next.js single-page app. The offer page
content is rendered client-side by React after the initial HTML loads, so
simple HTTP requests (httpx, requests) return a mostly-empty shell with no
offer data. Playwright drives a real headless Chromium instance that waits
for React to finish rendering before capturing the page.

### Why session cookies instead of logging in with credentials?

Octopus Energy's login flow uses OAuth 2.0 hosted on `auth.octopus.energy`
and is protected by an invisible hCAPTCHA. Automated form submission is
reliably blocked — the CAPTCHA fires even when the form is submitted
programmatically without any mouse interaction. The only practical solution
without a CAPTCHA-solving service is to reuse a real authenticated browser
session by exporting its cookies and loading them into Playwright's context.

### Why Infisical instead of a secrets file?

Storing secrets in `.env` and committing (or accidentally committing) them
is a common risk. Infisical gives a central secrets store that is fetched at
runtime, meaning the repo and Docker images contain zero credentials.
The CLI is available for local dev (`infisical run --`) and service tokens
are used on the server so no interactive login is needed.

### Why APScheduler instead of a cron job?

APScheduler runs in-process with FastAPI, which means the schedule can be
read from the database and changed live through the web UI without restarting
the container or editing any files on the server. It also makes the time-window
logic (only run between 08:00 and 22:00) easy to enforce per-job.

### Why PostgreSQL instead of SQLite?

SQLite has concurrency limitations when multiple async writers are involved
(the scheduler and web requests can both write). PostgreSQL also makes it
straightforward to add multi-account support or query history across time
ranges later.

### Why Terraform + Proxmox LXC instead of a VM or bare metal?

LXC containers on Proxmox are lightweight (no guest kernel overhead),
start in seconds, and support Docker nesting. Terraform gives reproducible
infrastructure — the entire container can be destroyed and re-created from
scratch with one command, which is useful for testing the provision script.

---

## Known Limitations

### Cookie expiry
Browser session cookies typically last several weeks but will eventually
expire. When they do, every scrape lands on the Octopus login page and
records `session_expired` status. There is no automatic refresh — the user
must export fresh cookies from their browser and paste them into the
`/session` page.

### hCAPTCHA blocks programmatic login
There is no way to log in programmatically without a CAPTCHA-solving service
(e.g. 2captcha, Anti-Captcha). If cookie-based auth is ever removed by
Octopus Energy, the scraper will stop working until an alternative is found.

### Offer button selector may change
The scraper searches for known button labels (`OFFER_BUTTON_TEXTS` in
`app/scraper.py`). If Octopus Energy changes the button text or page
structure, the offer will not be detected. The HTML snapshot stored per
scrape makes it easy to inspect what the page actually contained.

### Single account only
The current schema and UI are built for one Octopus account. The offer URL
and credentials are global config, not per-user.

### No push notifications
When an offer is accepted the result is stored in the database and visible
on the dashboard, but there is no outbound notification (email, webhook,
ntfy, Pushover, etc.).

### Chromium startup time
Each scrape launches a full Chromium instance, which takes 5–15 seconds.
For a once-an-hour poll this is fine, but it would be slow if the interval
were set very short.

---

## Possible Future Improvements

### High value

- **Cookie expiry notification** — detect `session_expired` status and send
  a push notification (ntfy.sh, Pushover, or email) prompting the user to
  refresh their cookies before the next scrape window.

- **Persistent browser context** — reuse a single Chromium profile across
  scrapes rather than launching a fresh instance each time. Would reduce
  startup time and make cookie management automatic (the browser would
  maintain its own session).

- **Webhook / ntfy alert on offer accepted** — POST to a user-configured
  URL when `offer_accepted=true` so the user gets an instant notification.

### Medium value

- **Multi-account support** — allow multiple Octopus accounts, each with
  their own offer URL, cookie set, and schedule config.

- **Automatic offer URL detection** — query the Kraken GraphQL API for the
  current active offer group URL rather than requiring it to be hardcoded
  in `.env`. (The GraphQL schema has the endpoint but it is behind a feature
  flag; worth re-checking periodically.)

- **Dashboard charts** — show offer detection rate over time, scrape
  duration, and session health as simple charts on the dashboard.

### Low value / nice to have

- **Dark/light mode toggle** — the UI is dark-only at present.

- **Scrape log streaming** — stream Playwright logs live to the browser
  during a manual scrape trigger so the user can watch what is happening.

- **Terraform remote state** — move `terraform.tfstate` to an S3-compatible
  backend (e.g. MinIO on the home lab) so it is not stored only on the
  developer's workstation.

- **Renovate / Dependabot** — automated PRs for dependency updates
  (Python packages, Playwright browser, PostgreSQL image).

---

## Key File Map

| Path | Purpose |
|---|---|
| `app/scraper.py` | Playwright scrape logic, cookie loading, offer detection |
| `app/scheduler.py` | APScheduler setup, reads config from DB |
| `app/models.py` | SQLAlchemy models (`ScrapeRecord`, `ScheduleConfig`) |
| `app/routers/scrapes.py` | Dashboard and manual trigger endpoints |
| `app/routers/schedule.py` | Schedule configuration endpoints |
| `app/routers/session.py` | Session cookie management endpoints |
| `alembic/versions/` | Database migrations |
| `terraform/` | Proxmox LXC infrastructure |
| `scripts/provision.sh` | One-shot server setup script |
| `start.ps1` / `stop.ps1` | Windows local dev helpers |
