#!/usr/bin/env bash
set -euo pipefail

# Seed the database with a sample case for testing stats.
# Usage:
#   DB_USER=fct_user DB_NAME=fct_db DB_PASSWORD='pw' ./scripts/seed_sample_case.sh
# Defaults: DB_USER=fct_user, DB_NAME=fct_db, DB_HOST=localhost, DB_PORT=5432

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SQL_FILE="$REPO_ROOT/scripts/seed_sample_case.sql"

DB_USER="${DB_USER:-fct_user}"
DB_NAME="${DB_NAME:-fct_db}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

if [ ! -f "$SQL_FILE" ]; then
  echo "SQL file not found: $SQL_FILE"
  exit 1
fi

if [ -z "${DB_PASSWORD:-}" ]; then
  read -s -p "Enter DB password for user '$DB_USER': " DB_PASSWORD
  echo
fi

echo "Seeding database '$DB_NAME' (user: $DB_USER) with sample case..."
PGPASSWORD="$DB_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -f "$SQL_FILE"

echo "Done. You can now run: conda run -n fct python -m src.cli.main stats --year 2025"
