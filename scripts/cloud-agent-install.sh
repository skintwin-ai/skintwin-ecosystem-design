#!/usr/bin/env bash
set -euo pipefail

# SkinTwin-AI org ecosystem bootstrap.
# Idempotent. Skips repos that are not present in this checkout.
# CPU-core vs checkout-only vs install kind come from domain/org-ecosystem.json.
# Does not start servers, run tests, or touch lockfiles.

export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
export npm_config_fund=false
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONUNBUFFERED=1

if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv python3-dev
fi

corepack enable >/dev/null 2>&1 || true

HUB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HUB_ROOT"
export PYTHONPATH="${HUB_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 -m domain.bootstrap
