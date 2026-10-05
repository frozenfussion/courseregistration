#!/usr/bin/env bash
# Replace the Resend API key in .env without the key ever appearing on screen, in history, or in chat:
#
#     ./deploy/set-resend-key.sh
#
# Then restart the site:  sudo systemctl restart regsite
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ -f .env ]] || { echo ".env not found. Run ./deploy/2-app-setup.sh first." >&2; exit 1; }

read -r -s -p "Paste the new Resend API key (hidden, press Enter): " KEY
echo
[[ -n "$KEY" ]] || { echo "Nothing entered, no change made." >&2; exit 1; }

umask 077
tmp="$(mktemp .env.XXXXXX)"
grep -v -E '^(RESEND_API_KEY|MAIL_PROVIDER)=' .env > "$tmp" || true
{ echo "MAIL_PROVIDER=resend"; echo "RESEND_API_KEY=$KEY"; } >> "$tmp"
chmod 600 "$tmp"
mv "$tmp" .env
echo "Updated .env. Now run:  sudo systemctl restart regsite"
echo "Then test with:        .venv/bin/python -m scripts.send_test_email faysalabdulaziz@gmail.com"
