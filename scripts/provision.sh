#!/usr/bin/env bash
# =============================================================================
# provision.sh  —  one-time setup for the octo-scrape LXC container
#
# Run this ONCE after Terraform creates the container:
#   scp -i ~/.ssh/octo_scrape_deploy scripts/provision.sh root@<IP>:/root/
#   ssh -i ~/.ssh/octo_scrape_deploy root@<IP>
#   bash /root/provision.sh
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/jelbies/octo_scrape.git"   # updated by CI
APP_DIR="/opt/octo_scrape"
SERVICE_FILE="/etc/systemd/system/octo-scrape.service"
ENV_FILE="/etc/octo-scrape.env"

echo ""
echo "================================================================"
echo "  Octo Scrape — Container Provisioning"
echo "================================================================"
echo ""

# ── 1. System updates ────────────────────────────────────────────────────────
echo ">>> Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl git ca-certificates gnupg lsb-release

# ── 2. Docker ────────────────────────────────────────────────────────────────
echo ">>> Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "Docker installed."
else
    echo "Docker already installed."
fi

# ── 3. Infisical CLI ─────────────────────────────────────────────────────────
echo ">>> Installing Infisical CLI..."
if ! command -v infisical &>/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' | bash
    apt-get install -y infisical
    echo "Infisical installed."
else
    echo "Infisical already installed."
fi

# ── 4. Clone the repo ────────────────────────────────────────────────────────
echo ">>> Cloning octo_scrape repo..."
if [ -d "$APP_DIR" ]; then
    echo "App directory already exists, pulling latest..."
    git -C "$APP_DIR" pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi

# ── 5. Infisical service token ───────────────────────────────────────────────
echo ""
echo ">>> Infisical setup"
echo ""
echo "You need an Infisical SERVICE TOKEN so the app can fetch secrets"
echo "automatically without interactive login."
echo ""
echo "Steps:"
echo "  1. Open https://app.infisical.com"
echo "  2. Go to your 'octopus' project"
echo "  3. Project Settings → Service Tokens → Add Token"
echo "  4. Give it a name (e.g. 'octo-scrape-server'), select 'dev' environment"
echo "  5. Copy the token (starts with st.)"
echo ""
read -rp "Paste your Infisical service token here: " INFISICAL_TOKEN

if [ -z "$INFISICAL_TOKEN" ]; then
    echo "WARNING: No token provided. You will need to edit $ENV_FILE manually."
fi

# Write the env file (contains the service token — readable only by root)
cat > "$ENV_FILE" <<EOF
# Infisical service token — injected at container start
# Do not commit or share this file.
INFISICAL_TOKEN=${INFISICAL_TOKEN}
INFISICAL_PROJECT_ID=7d764c71-0e3a-47ab-914c-40e4767a67d8
EOF
chmod 600 "$ENV_FILE"
echo "Service token saved to $ENV_FILE"

# ── 6. start.sh (Linux version) ──────────────────────────────────────────────
echo ">>> Writing /opt/octo_scrape/start.sh..."
cat > "$APP_DIR/start.sh" <<'STARTSH'
#!/usr/bin/env bash
# Fetch secrets from Infisical and start Docker Compose.
set -euo pipefail

# Load service token
if [ -f /etc/octo-scrape.env ]; then
    set -a; source /etc/octo-scrape.env; set +a
fi

PROJECT_ID="${INFISICAL_PROJECT_ID:-7d764c71-0e3a-47ab-914c-40e4767a67d8}"

echo "Fetching secrets from Infisical..."
export OCTOPUS_API_KEY=$(infisical secrets get OCTOPUS_API_KEY   --projectId="$PROJECT_ID" --plain --silent 2>/dev/null | tr -d '[:space:]')
export OCTOPUS_EMAIL=$(infisical secrets get OCTOPUS_EMAIL     --projectId="$PROJECT_ID" --plain --silent 2>/dev/null | tr -d '[:space:]')
export OCTOPUS_PASSWORD=$(infisical secrets get OCTOPUS_PASSWORD  --projectId="$PROJECT_ID" --plain --silent 2>/dev/null | tr -d '[:space:]')
export POSTGRES_PASSWORD=$(infisical secrets get POSTGRES_PASSWORD --projectId="$PROJECT_ID" --plain --silent 2>/dev/null | tr -d '[:space:]')
export SECRET_KEY=$(infisical secrets get SECRET_KEY        --projectId="$PROJECT_ID" --plain --silent 2>/dev/null | tr -d '[:space:]')

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo "ERROR: Failed to fetch secrets from Infisical. Check your service token."
    exit 1
fi

echo "Secrets loaded. Starting containers..."
cd "$(dirname "$0")"
docker compose up -d --build
echo ""
echo "Done! App is running at http://$(hostname -I | awk '{print $1}'):8000"
STARTSH
chmod +x "$APP_DIR/start.sh"

# ── 7. Systemd service ───────────────────────────────────────────────────────
echo ">>> Creating systemd service..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Octo Scrape
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/start.sh
ExecStop=docker compose -f $APP_DIR/docker-compose.yml down
WorkingDirectory=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable octo-scrape.service
echo "Systemd service enabled (starts automatically on boot)."

# ── 8. First run ─────────────────────────────────────────────────────────────
echo ""
echo ">>> Starting the app for the first time..."
bash "$APP_DIR/start.sh"

# ── Done ─────────────────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "================================================================"
echo "  ✓ Provisioning complete!"
echo ""
echo "  Web UI:   http://${IP}:8000"
echo ""
echo "  Next: go to http://${IP}:8000/session and paste your"
echo "        Octopus Energy browser cookies to enable scraping."
echo "================================================================"
