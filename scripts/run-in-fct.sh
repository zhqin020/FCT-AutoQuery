#!/usr/bin/env bash
set -euo pipefail

# Wrapper to run commands inside the project's conda environment (defaults to 'fct').
# Usage:
#   ./scripts/run-in-fct.sh pytest -q
#   ./scripts/run-in-fct.sh -n other-env python -m src.cli.main

CONDA_ENV="${CONDA_DEFAULT_ENV:-fct}"

if [[ "${1:-}" == "-n" || "${1:-}" == "--env" ]]; then
  shift
  if [[ -z "${1:-}" ]]; then
    echo "Usage: $0 [-n|--env <env>] <command...>" >&2
    exit 2
  fi
  CONDA_ENV="$1"
  shift
fi

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 [-n|--env <env>] <command...>" >&2
  exit 2
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found in PATH. Please install Conda or activate environment manually." >&2
  exit 3
fi

echo "Running under conda environment: ${CONDA_ENV}" >&2
exec conda run -n "${CONDA_ENV}" -- "$@"
