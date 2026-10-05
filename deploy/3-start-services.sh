#!/usr/bin/env bash
# STEP 3 of 3. Run this yourself with sudo:
#
#     sudo ./deploy/3-start-services.sh
#
# Starts the site and the nightly backup timer, restarts Caddy, and runs a quick check.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run this with sudo:  sudo ./deploy/3-start-services.sh" >&2
  exit 1
fi

systemctl daemon-reload
systemctl enable --now regsite.service
systemctl enable --now regsite-backup.timer
systemctl restart regsite.service
systemctl reload-or-restart caddy

sleep 3
echo
systemctl --no-pager --lines=0 status regsite.service | head -4 || true
echo
echo "Local check:  $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/healthz) (expect 200)"
echo "Public check: $(curl -s -o /dev/null -w '%{http_code}' https://register.faysalaziz.com/healthz || echo failed) (expect 200; the first request can take a few seconds while Caddy gets the certificate)"
echo
echo "Done. Logs:   journalctl -u regsite -f     and     journalctl -u caddy -f"
