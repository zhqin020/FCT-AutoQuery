#!/usr/bin/env bash
set -euo pipefail
# Usage: ./scripts/update_pr_body.sh [PR_NUMBER] [OWNER] [REPO] [BODY_FILE]
# Example: PR_NUMBER=11 OWNER=zhqin020 REPO=FCT-AutoQuery BODY_FILE=PULL_REQUEST_BODY.md ./scripts/update_pr_body.sh

PR_NUMBER=${1:-11}
OWNER=${2:-zhqin020}
REPO=${3:-FCT-AutoQuery}
BODY_FILE=${4:-PULL_REQUEST_BODY.md}

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "ERROR: GITHUB_TOKEN environment variable is not set. Export it and re-run."
  exit 1
fi

if [ ! -f "$BODY_FILE" ]; then
  echo "ERROR: body file '$BODY_FILE' not found."
  exit 1
fi

echo "Updating PR #$PR_NUMBER on $OWNER/$REPO using body file: $BODY_FILE"

# Safely JSON-encode the file contents using Python to avoid jq dependency
BODY_JSON=$(python3 - <<PY
import sys, json
text = open('$BODY_FILE', 'r', encoding='utf-8').read()
print(json.dumps(text))
PY
)

API_URL="https://api.github.com/repos/${OWNER}/${REPO}/pulls/${PR_NUMBER}"

resp=$(curl -sS -X PATCH "$API_URL" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -d "{\"body\": $BODY_JSON}")

if echo "$resp" | grep -q '"url"'; then
  echo "PR updated successfully."
  echo
  # Print PR html_url if present
  echo "$resp" | python3 -c "import sys, json
obj=json.load(sys.stdin)
print(obj.get('html_url',''))"
  exit 0
else
  echo "Failed to update PR. Response:" >&2
  echo "$resp" >&2
  exit 2
fi
