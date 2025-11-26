#!/usr/bin/env bash
# Check project Constitution preflight: active conda env and tests for changed src files
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

# 1) Verify active Conda environment
ACTIVE_CONDA=${CONDA_DEFAULT_ENV:-}
if [[ -z "$ACTIVE_CONDA" ]]; then
  echo "Conda env not detected via CONDA_DEFAULT_ENV."
  echo "Please activate the required environment: 'conda activate fct' or 'conda activate fct-env'"
  exit 2
fi

case "$ACTIVE_CONDA" in
  fct|fct-env|fct_env)
    echo "Conda env active: $ACTIVE_CONDA" ;;
  *)
    echo "Active conda env is '$ACTIVE_CONDA' — required 'fct' or 'fct-env'."
    echo "If you intend to proceed anyway, activate the correct env: conda activate fct"
    exit 3 ;;
esac

echo "[OK] Environment check passed"

# 2) Determine changed files to check for tests
# Prefer explicit file args: scripts/check_constitution.sh file1 file2
FILES_TO_CHECK=()
if [[ $# -gt 0 ]]; then
  for f in "$@"; do FILES_TO_CHECK+=("$f"); done
else
  # Try to get changed files relative to origin/main if available
  if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
    base_ref=$(git rev-parse --abbrev-ref @{u} | sed 's@.*/@@') || true
  fi
  if git rev-parse --verify origin/main >/dev/null 2>&1; then
    CHANGED=$(git diff --name-only origin/main...HEAD || true)
  else
    CHANGED=$(git status --porcelain | awk '{print $2}' || true)
  fi
  while read -r line; do
    [[ -z "$line" ]] && continue
    FILES_TO_CHECK+=("$line")
  done <<<"$CHANGED"
fi

if [[ ${#FILES_TO_CHECK[@]} -eq 0 ]]; then
  echo "No changed files detected. Skipping test existence checks."
  exit 0
fi

echo "Checking ${#FILES_TO_CHECK[@]} changed files for corresponding tests..."

MISSING_TESTS=()
for f in "${FILES_TO_CHECK[@]}"; do
  # Normalize path
  nf=$(echo "$f" | sed 's|\./||')
  # Only consider Python source files under src/
  if [[ "$nf" != src/*.py ]]; then
    continue
  fi

  base=$(basename "$nf" .py)
  # Look for any test file containing test_<base>.py anywhere under tests/
  matches=$(git ls-files -- "tests/**/test_${base}.py" || true)
  if [[ -z "$matches" ]]; then
    # Also accept tests named after modules (e.g., tests/test_services.py) or containing the base
    matches=$(git ls-files -- "tests/**/*${base}*.py" || true)
  fi

  if [[ -z "$matches" ]]; then
    MISSING_TESTS+=("$nf")
  fi
done

if [[ ${#MISSING_TESTS[@]} -gt 0 ]]; then
  echo "The following changed source files have no matching tests in 'tests/':" >&2
  for m in "${MISSING_TESTS[@]}"; do echo "  - $m" >&2; done
  echo "Per project constitution, add tests before merging." >&2
  exit 4
fi

echo "[OK] All changed src files have tests (or no src changes)."
exit 0
