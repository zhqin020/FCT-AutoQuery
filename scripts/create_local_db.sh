#!/usr/bin/env bash
set -euo pipefail

# create_local_db.sh
#
# Create a local Postgres role and database for FCT-AutoQuery and import schema.
# Usage:
#   ./scripts/create_local_db.sh [db_user] [db_name]
# Examples:
#   ./scripts/create_local_db.sh             # uses defaults fct_user / fct_db
#   ./scripts/create_local_db.sh myuser mydb  # custom names
#
# The script will prompt for a password (hidden). You can also supply it
# via the environment variable FCT_DB_PASSWORD to run non-interactively.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCHEMA_FILE="$REPO_ROOT/src/lib/database_schema.sql"

DB_USER="${1:-fct_user}"
DB_NAME="${2:-fct_db}"

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "Schema file not found: $SCHEMA_FILE"
  exit 1
fi

echo "This script will create Postgres role '$DB_USER' and database '$DB_NAME'."

if [ -z "${FCT_DB_PASSWORD:-}" ]; then
  read -s -p "Enter password for database user '$DB_USER': " FCT_DB_PASSWORD
  echo
else
  echo "Using FCT_DB_PASSWORD from environment"
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql command not found. Install PostgreSQL client tools and try again."
  exit 1
fi

echo "Creating role '$DB_USER'..."
sudo -u postgres psql -v ON_ERROR_STOP=1 <<-SQL
DO
\$do\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DB_USER}') THEN
      CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${FCT_DB_PASSWORD}';
   ELSE
      ALTER ROLE ${DB_USER} WITH PASSWORD '${FCT_DB_PASSWORD}';
   END IF;
END
\$do\$;
SQL

echo "Creating database '$DB_NAME' owned by '$DB_USER'..."
# Check whether database exists, create if not
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  echo "Database '${DB_NAME}' already exists"
else
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
fi

echo "Importing schema into '$DB_NAME'..."
PGPASSWORD="$FCT_DB_PASSWORD" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -h localhost -d "$DB_NAME" -f "$SCHEMA_FILE"

echo "Done. Database '$DB_NAME' is ready and owned by '$DB_USER'."
echo "Remember: config.private.toml should contain these credentials and is ignored by git."
