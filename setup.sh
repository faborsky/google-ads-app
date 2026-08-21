#!/usr/bin/env bash
# Bootstrap the Google Ads CLI: create venv, install deps, prepare .env.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

echo "==> Creating virtual environment (.venv)"
"$PYTHON" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example (fill in your credentials)"
  cp .env.example .env
  chmod 600 .env
else
  echo "==> .env already exists — leaving it untouched"
fi

echo ""
echo "Done. Next steps:"
echo "  1) Edit .env: GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET,"
echo "     GOOGLE_ADS_LOGIN_CUSTOMER_ID (see README → Autentizace)"
echo "  2) ./run.sh auth          # OAuth in the browser → refresh token written into .env"
echo "  3) ./run.sh accounts      # first live read"
