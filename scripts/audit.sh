#!/usr/bin/env bash
# Dependency audit: run on every build and before every deploy.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v pip-audit >/dev/null 2>&1; then
  echo "pip-audit is not installed; install it with: python -m pip install pip-audit" >&2
  exit 1
fi

pip-audit -r requirements.txt
