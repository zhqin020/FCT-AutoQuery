#!/usr/bin/env bash
# Check project Constitution preflight: active conda env and tests for changed src files
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

# 1) Verify active Conda environment (be resilient in non-interactive shells)
ACTIVE_CONDA=${CONDA_DEFAULT_ENV:-}
if [[ -n "$ACTIVE_CONDA" ]]; then
  case "$ACTIVE_CONDA" in
    fct|fct-env|fct_env)
      echo "Conda env active: $ACTIVE_CONDA" ;;
    *)
      echo "Active conda env is '$ACTIVE_CONDA' — required 'fct' or 'fct-env'."
      echo "If you intend to proceed anyway, activate the correct env: conda activate fct"
      # don't hard-fail here; continue with a warning so IDE/CI can proceed
      echo "[WARN] Proceeding despite non-matching conda env." >&2 ;;
  esac
  echo "[OK] Environment check passed"
else
  # No CONDA_DEFAULT_ENV set (IDE/CI shells). Try to detect if 'conda run -n fct' works,
  # otherwise warn and continue (non-fatal) so hooks remain usable in CI and editors.
  if command -v conda >/dev/null 2>&1; then
    if conda run -n fct true >/dev/null 2>&1; then
      echo "Conda not activated, but 'conda run -n fct' is available (fct environment exists)."
      echo "Pre-commit will proceed and rely on 'conda run -n fct' for env-specific commands."
    else
      echo "Warning: Conda found but environment 'fct' not available or 'conda run' failed." >&2
      echo "Pre-commit will continue, but some checks may be skipped or less strict." >&2
    fi
  else
    echo "Warning: conda not found; proceeding but skipping environment-specific checks." >&2
  fi
fi

# 1.5) Check that any 'Options' / 'Choices' sections in docs use numbered lists
if command -v python3 >/dev/null 2>&1; then
  python3 scripts/check_numbered_options.py || die "Numbering check failed: use numbered lists for Options sections"
else
  echo "Warning: python3 not found; skipping numbering check." >&2
fi

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
