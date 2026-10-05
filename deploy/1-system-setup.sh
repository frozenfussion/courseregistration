#!/usr/bin/env bash
# STEP 1 of 3. Run this yourself with sudo (it needs your password), from the project folder:
#
#     sudo ./deploy/1-system-setup.sh
#
# It installs system packages, Caddy and the GitHub CLI, puts the Caddyfile and the systemd units in
# place, and opens ports 80 and 443 if the Ubuntu firewall (ufw) is on. It does NOT start the site.
# It is safe to run more than once.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run this with sudo:  sudo ./deploy/1-system-setup.sh" >&2
  exit 1
fi

APP_USER="${SUDO_USER:-}"
if [[ -z "$APP_USER" || "$APP_USER" == "root" ]]; then
  echo "Run it as your normal user with sudo (not as root directly), so the service runs as you." >&2
  exit 1
fi
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "App user: $APP_USER"
echo "App folder: $APP_DIR"

export DEBIAN_FRONTEND=noninteractive

echo "==> Installing system packages"
apt-get update -y
apt-get install -y python3-venv python3-pip git curl gnupg sqlite3 unzip \
  debian-keyring debian-archive-keyring apt-transport-https \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 libffi-dev libjpeg-dev libopenjp2-7-dev

if ! command -v caddy >/dev/null 2>&1; then
  echo "==> Installing Caddy (official apt repository)"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
else
  echo "==> Caddy already installed: $(caddy version | head -1)"
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "==> Installing the GitHub CLI (official apt repository)"
  mkdir -p -m 755 /etc/apt/keyrings
  out="$(mktemp)"
  curl -fsSL -o "$out" https://cli.github.com/packages/githubcli-archive-keyring.gpg
  tee /etc/apt/keyrings/githubcli-archive-keyring.gpg < "$out" >/dev/null
  chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  mkdir -p -m 755 /etc/apt/sources.list.d
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  apt-get update -y
  apt-get install -y gh
  rm -f "$out"
else
  echo "==> GitHub CLI already installed: $(gh --version | head -1)"
fi

echo "==> Installing the Caddyfile"
caddy validate --config "$APP_DIR/deploy/Caddyfile" --adapter caddyfile >/dev/null
if [[ -f /etc/caddy/Caddyfile ]] && ! cmp -s "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile; then
  cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date +%Y%m%d%H%M%S)"
fi
install -m 644 "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile

echo "==> Installing the systemd units"
mkdir -p "$APP_DIR/data/cache"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/data"
for unit in regsite regsite-backup; do
  sed -e "s#__USER__#$APP_USER#g" -e "s#__APP_DIR__#$APP_DIR#g" \
    "$APP_DIR/deploy/$unit.service.template" > "/etc/systemd/system/$unit.service"
done
install -m 644 "$APP_DIR/deploy/regsite-backup.timer" /etc/systemd/system/regsite-backup.timer
systemctl daemon-reload

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  echo "==> ufw is active: allowing HTTP and HTTPS"
  ufw allow 80/tcp
  ufw allow 443/tcp
else
  echo "==> ufw is not active, nothing to open on this machine."
  echo "    If you use a DigitalOcean Cloud Firewall, make sure it allows TCP 80 and 443."
fi

echo
echo "Step 1 done. Next (no sudo):  ./deploy/2-app-setup.sh"
