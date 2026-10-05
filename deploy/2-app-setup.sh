#!/usr/bin/env bash
# STEP 2 of 3. No sudo needed. Run from the project folder:
#
#     ./deploy/2-app-setup.sh
#
# Creates the Python environment, installs the app, writes the private .env file (asking you for the
# Resend API key at a hidden prompt), builds the database, adds the starter course and, if there is no
# admin yet, asks you to choose the admin username and password. Safe to run more than once.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
APP_DIR="$(pwd)"

echo "==> Python environment"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "==> Private settings file (.env)"
if [[ -f .env ]]; then
  echo ".env already exists, leaving it alone."
else
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  read -r -s -p "Paste the Resend API key (input is hidden, press Enter): " RESEND_KEY
  echo
  if [[ -z "$RESEND_KEY" ]]; then
    echo "No key entered. Emails will only be written to the log until you add RESEND_API_KEY to .env." >&2
  fi
  umask 077
  cat > .env <<EOF
APP_ENV=production
SECRET_KEY=$SECRET_KEY
BASE_URL=https://register.faysalaziz.com
TIMEZONE=Asia/Kuala_Lumpur

MAIL_PROVIDER=$([[ -n "$RESEND_KEY" ]] && echo resend || echo console)
MAIL_FROM=Faysal Aziz <registration@register.faysalaziz.com>
MAIL_REPLY_TO=faysalabdulaziz@gmail.com
ADMIN_ALERT_EMAIL=faysalabdulaziz@gmail.com
RESEND_API_KEY=$RESEND_KEY
EOF
  chmod 600 .env
  echo ".env written (readable only by you)."
fi

echo "==> Database"
mkdir -p data
alembic upgrade head
python -m scripts.seed

echo "==> Admin account"
if python - <<'PY'
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import AdminUser
with SessionLocal() as db:
    raise SystemExit(0 if db.scalar(select(func.count()).select_from(AdminUser)) else 1)
PY
then
  echo "An admin account already exists. To change the password: python -m scripts.create_admin <username>"
else
  python -m scripts.create_admin
fi

echo
echo "Step 2 done. Next (needs sudo):  sudo ./deploy/3-start-services.sh"
