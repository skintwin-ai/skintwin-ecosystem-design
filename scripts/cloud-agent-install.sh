#!/usr/bin/env bash
set -euo pipefail

# SkinTwin-AI org ecosystem bootstrap.
# Idempotent. Skips repos that are not present in this checkout.
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

# Colon-separated search roots for hermetic tests. Default Cloud Agent layouts.
DEFAULT_REPO_ROOTS="/agent/repos:/workspace/repos:/workspace"

find_repo() {
  local name="$1"
  local d roots="${CLOUD_AGENT_REPO_ROOTS:-$DEFAULT_REPO_ROOTS}"
  local IFS=:
  for d in $roots; do
    if [ -d "${d}/${name}" ] && { [ -f "${d}/${name}/package.json" ] || [ -f "${d}/${name}/pyproject.toml" ] || [ -f "${d}/${name}/requirements.txt" ] || [ -f "${d}/${name}/README.md" ]; }; then
      printf "%s" "${d}/${name}"
      return 0
    fi
  done
  if [ -z "${CLOUD_AGENT_REPO_ROOTS:-}" ] && [ -f /workspace/package.json ] && grep -q "\"name\": \"${name}\"" /workspace/package.json; then
    printf "%s" /workspace
    return 0
  fi
  return 1
}

install_node_repo() {
  local name="$1"
  local dir
  dir="$(find_repo "$name" || true)"
  if [ -z "${dir}" ]; then
    echo "[skip] ${name}: not present"
    return 0
  fi
  echo "[node] ${name} @ ${dir}"
  (
    cd "$dir"
    if [ -f pnpm-lock.yaml ]; then
      corepack pnpm install --frozen-lockfile
    elif [ -f yarn.lock ]; then
      corepack yarn install --frozen-lockfile
    elif [ -f package-lock.json ]; then
      npm ci
    elif [ -f package.json ]; then
      npm install
    fi
  )
}

install_python_editable() {
  local name="$1"
  shift
  local dir
  dir="$(find_repo "$name" || true)"
  if [ -z "${dir}" ]; then
    echo "[skip] ${name}: not present"
    return 0
  fi
  echo "[py] ${name} @ ${dir}"
  (
    cd "$dir"
    python3 -m venv .venv
    .venv/bin/pip install -U pip setuptools wheel
    if [ "$#" -gt 0 ]; then
      .venv/bin/pip install "$@"
    elif [ -f pyproject.toml ]; then
      .venv/bin/pip install -e ".[dev]" || .venv/bin/pip install -e .
    elif [ -f requirements.txt ]; then
      .venv/bin/pip install -r requirements.txt
    fi
  )
}

install_node_repo skintwinnector
install_node_repo skinport
install_node_repo skintwin-customer-portal
install_node_repo cognitive-architecture
install_node_repo regima-platform
install_node_repo skintwin-bot

install_python_editable org-skin -e ".[dev]"
install_python_editable skintwin-integrations -r requirements.txt
install_python_editable neuro-symbolic-core -e "./packages/nettica" -e "./packages/neuro-symbolic-hybrid" pytest

dir="$(find_repo pcsdbx || true)"
if [ -n "${dir}" ]; then
  echo "[ok] pcsdbx present at ${dir} (stdlib only)"
else
  echo "[skip] pcsdbx: not present"
fi

echo "[done] SkinTwin-AI ecosystem install"
