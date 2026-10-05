#!/usr/bin/env bash
# Update an existing deployment after new code has been pulled or copied in. No sudo needed:
#
#     ./deploy/update.sh
#
# Installs any new dependencies and applies database migrations, then tells you how to restart.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# shellcheck disable=SC1091
. .venv/bin/activate
python -m scripts.backup           # a safety copy before any migration
pip install --quiet -r requirements.txt
alembic upgrade head
echo
echo "Updated. Restart the site with:  sudo systemctl restart regsite"
