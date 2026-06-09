#!/usr/bin/env bash
# Convenience wrapper: activates the venv and runs the CLI.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "No .venv found. Run ./setup.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python google_ads_cli.py "$@"
