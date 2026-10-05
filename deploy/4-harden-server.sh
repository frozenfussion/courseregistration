#!/usr/bin/env bash
# OPTIONAL STEP 4. Run this yourself with sudo (it needs your password), from the project folder:
#
#     sudo ./deploy/4-harden-server.sh          # apply
#     sudo ./deploy/4-harden-server.sh --undo   # go back to the state before hardening
#
# What it does: turns on the firewall (ufw), installs fail2ban (bans repeated failed SSH logins),
# tightens four SSH settings, and makes sure security updates install automatically. It never reboots.
# It does NOT touch PermitRootLogin, PasswordAuthentication, AllowUsers, the SSH port, Caddy, the app,
# the database or .env. Safe to run more than once. See deploy/HARDENING.md.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run this with sudo:  sudo ./deploy/4-harden-server.sh" >&2
  exit 1
fi

SSH_DROPIN=/etc/ssh/sshd_config.d/10-hardening.conf
JAIL_FILE=/etc/fail2ban/jail.d/sshd-regsite.conf
UPGRADES_FILE=/etc/apt/apt.conf.d/52regsite-unattended.conf
BACKUP_ROOT=/var/backups/regsite-hardening
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"

reload_ssh() {
  # SSH is socket-activated on this server. Reload (never restart) so open sessions are not cut.
  if systemctl is-active --quiet ssh.service; then
    systemctl reload ssh.service
  fi
  systemctl is-active --quiet ssh.socket || systemctl is-active --quiet ssh.service || {
    echo "!!! SSH is not active after reload. Do not close your current session." >&2; exit 1; }
}

ssh_value() {  # ssh_value <keyword>  -> effective value from sshd -T (empty if it cannot be read)
  local out
  out="$(sshd -T 2>/dev/null)" || return 0
  awk -v k="$1" '$1 == k {print $2; exit}' <<<"$out" || true
}

# ---------------------------------------------------------------------------------------------
if [[ "${1:-}" == "--undo" ]]; then
  echo "==> Undo: removing the SSH drop-in"
  if [[ -f "$SSH_DROPIN" ]]; then
    mkdir -p "$BACKUP_DIR"; cp -a "$SSH_DROPIN" "$BACKUP_DIR/"
    rm -f "$SSH_DROPIN"
    sshd -t
    reload_ssh
    echo "    removed $SSH_DROPIN and reloaded ssh"
  else
    echo "    no drop-in present"
  fi
  echo "==> Undo: disabling the firewall (rules are kept, so re-running the script restores them)"
  ufw disable || true
  echo "==> Undo: stopping and disabling fail2ban"
  systemctl disable --now fail2ban 2>/dev/null || true
  echo
  echo "Undone. Not undone on purpose: installed packages and automatic security updates."
  exit 0
fi
[[ -z "${1:-}" ]] || { echo "Unknown option: $1 (only --undo is supported)" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l     # list services needing a restart, never restart them automatically
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_ROOT" "$BACKUP_DIR"
echo "Backups of anything changed go to $BACKUP_DIR"

# --- 0. Record the SSH state BEFORE any change ------------------------------------------------
BEFORE_PW="$(ssh_value passwordauthentication)"
BEFORE_ROOT="$(ssh_value permitrootlogin)"
if [[ -z "$BEFORE_PW" || -z "$BEFORE_ROOT" ]]; then
  echo "!!! Could not read the current SSH settings with sshd -T. Nothing was changed. sshd said:" >&2
  sshd -T 2>&1 | head -5 >&2 || true
  exit 1
fi
sshd -T > "$BACKUP_DIR/sshd-T.before" 2>&1 || true
echo "==> SSH before: passwordauthentication=$BEFORE_PW permitrootlogin=$BEFORE_ROOT"

# --- 1. Packages (only if missing) ------------------------------------------------------------
echo "==> Installing ufw, fail2ban, unattended-upgrades if missing"
need=()
for p in ufw fail2ban unattended-upgrades; do
  dpkg -s "$p" >/dev/null 2>&1 || need+=("$p")
done
if ((${#need[@]})); then
  apt-get update -y
  apt-get install -y "${need[@]}"
else
  echo "    all three already installed"
fi

# --- 2. SSH hardening drop-in -----------------------------------------------------------------
echo "==> SSH drop-in $SSH_DROPIN"
NEW_DROPIN="$(mktemp)"
cat > "$NEW_DROPIN" <<'EOF'
# Managed by deploy/4-harden-server.sh. Remove with: sudo ./deploy/4-harden-server.sh --undo
# Deliberately does NOT set PermitRootLogin, PasswordAuthentication or AllowUsers.
PermitEmptyPasswords no
X11Forwarding no
MaxAuthTries 4
LoginGraceTime 30
EOF
HAD_DROPIN=0
if [[ -f "$SSH_DROPIN" ]]; then
  HAD_DROPIN=1
  cp -a "$SSH_DROPIN" "$BACKUP_DIR/10-hardening.conf.prev"
fi
if [[ $HAD_DROPIN -eq 1 ]] && cmp -s "$NEW_DROPIN" "$SSH_DROPIN"; then
  echo "    already in place"
else
  install -m 644 -o root -g root "$NEW_DROPIN" "$SSH_DROPIN"
  if ! sshd -t; then
    echo "!!! sshd -t rejected the configuration. Restoring and stopping." >&2
    if [[ $HAD_DROPIN -eq 1 ]]; then cp -a "$BACKUP_DIR/10-hardening.conf.prev" "$SSH_DROPIN"; else rm -f "$SSH_DROPIN"; fi
    rm -f "$NEW_DROPIN"; exit 1
  fi
  reload_ssh
  echo "    validated with sshd -t and reloaded"
fi
rm -f "$NEW_DROPIN"

AFTER_PW="$(ssh_value passwordauthentication)"
AFTER_ROOT="$(ssh_value permitrootlogin)"
if [[ "$AFTER_PW" != "$BEFORE_PW" || "$AFTER_ROOT" != "$BEFORE_ROOT" ]]; then
  echo "!!! !!! !!! SSH SETTINGS CHANGED UNEXPECTEDLY !!! !!! !!!" >&2
  echo "    passwordauthentication: $BEFORE_PW -> $AFTER_PW ; permitrootlogin: $BEFORE_ROOT -> $AFTER_ROOT" >&2
  if [[ $HAD_DROPIN -eq 1 ]]; then cp -a "$BACKUP_DIR/10-hardening.conf.prev" "$SSH_DROPIN"; else rm -f "$SSH_DROPIN"; fi
  sshd -t && reload_ssh
  echo "    Drop-in restored/removed and ssh reloaded. Firewall and fail2ban were NOT touched. Keep your session open." >&2
  exit 1
fi
sshd -T > "$BACKUP_DIR/sshd-T.after" 2>&1 || true
echo "    unchanged (as required): passwordauthentication=$AFTER_PW permitrootlogin=$AFTER_ROOT"
echo "    now: permitemptypasswords=$(ssh_value permitemptypasswords) x11forwarding=$(ssh_value x11forwarding)" \
     "maxauthtries=$(ssh_value maxauthtries) logingracetime=$(ssh_value logingracetime)"

# --- 3. Firewall ------------------------------------------------------------------------------
echo "==> Firewall (ufw)"
cp -a /etc/ufw "$BACKUP_DIR/ufw" 2>/dev/null || true
cp -a /etc/default/ufw "$BACKUP_DIR/default-ufw" 2>/dev/null || true
if ip -6 addr show scope global 2>/dev/null | grep -q inet6 && grep -q '^IPV6=no' /etc/default/ufw; then
  sed -i 's/^IPV6=no/IPV6=yes/' /etc/default/ufw
  echo "    droplet has public IPv6: set IPV6=yes in /etc/default/ufw"
fi
ufw default deny incoming
ufw default allow outgoing
if ufw app info OpenSSH >/dev/null 2>&1; then
  ufw allow OpenSSH
else
  ufw allow 22/tcp
fi
# Refuse to enable unless an SSH rule is really in the list
if ! ufw show added | grep -Eq 'OpenSSH|22/tcp'; then
  echo "!!! SSH rule is not present; NOT enabling the firewall." >&2
  exit 1
fi
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp      # Caddy HTTP/3
ufw --force enable
ufw status verbose

# --- 4. fail2ban ------------------------------------------------------------------------------
echo "==> fail2ban"
if [[ -f /var/log/auth.log ]]; then
  F2B_BACKEND="auto"; F2B_LOG="logpath = /var/log/auth.log"
else
  F2B_BACKEND="systemd"; F2B_LOG=""
fi
NEW_JAIL="$(mktemp)"
cat > "$NEW_JAIL" <<EOF
# Managed by deploy/4-harden-server.sh
[sshd]
enabled  = true
port     = ssh
backend  = $F2B_BACKEND
$F2B_LOG
maxretry = 5
findtime = 10m
bantime  = 1h
ignoreip = 127.0.0.1/8 ::1
EOF
if [[ -f "$JAIL_FILE" ]] && cmp -s "$NEW_JAIL" "$JAIL_FILE"; then
  echo "    jail already configured"
  systemctl enable --now fail2ban
else
  [[ -f "$JAIL_FILE" ]] && cp -a "$JAIL_FILE" "$BACKUP_DIR/sshd-regsite.conf.prev"
  install -m 644 -o root -g root "$NEW_JAIL" "$JAIL_FILE"
  systemctl enable fail2ban
  systemctl restart fail2ban
fi
rm -f "$NEW_JAIL"
ok=0
for _ in $(seq 1 15); do
  if fail2ban-client status sshd >/dev/null 2>&1; then ok=1; break; fi
  sleep 1
done
if [[ $ok -eq 1 ]]; then
  fail2ban-client status sshd
else
  echo "!!! The sshd jail did not start. Check: journalctl -u fail2ban -n 50 --no-pager" >&2
  exit 1
fi

# --- 5. Automatic security updates ------------------------------------------------------------
echo "==> Automatic security updates"
if ! grep -Eq '^\s*"\$\{distro_id\}ESMApps:\$\{distro_codename\}-security";|^\s*"\$\{distro_id\}:\$\{distro_codename\}-security";' \
     /etc/apt/apt.conf.d/50unattended-upgrades; then
  echo "    WARNING: the -security origin does not look enabled in 50unattended-upgrades; check it." >&2
fi
cat > "$UPGRADES_FILE" <<'EOF'
// Managed by deploy/4-harden-server.sh
Unattended-Upgrade::Automatic-Reboot "false";
EOF
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades
echo "    Automatic-Reboot effective value: $(apt-config dump | grep -i 'Automatic-Reboot ' | head -1)"

echo "==> apt-get update and upgrade (no dist-upgrade)"
apt-get update -y
apt-get -y -o Dpkg::Options::=--force-confold upgrade

echo
if [[ -f /var/run/reboot-required ]]; then
  echo "A REBOOT IS REQUIRED (not done; do it yourself when convenient):"
  cat /var/run/reboot-required.pkgs 2>/dev/null || true
else
  echo "No reboot required."
fi
echo
echo "Done. BEFORE closing this session, open a NEW SSH session from your laptop and log in with your password."
echo "To go back:  sudo ./deploy/4-harden-server.sh --undo"
