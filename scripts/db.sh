#!/bin/bash
# Database management helper script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Load database config from environment or use defaults
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-fct_db}"
DB_USER="${DB_USER:-fct_user}"
DB_PASSWORD="${DB_PASSWORD:-fctpass}"

function print_usage() {
    cat << EOF
Database Management Script for fct_db

Usage: $0 <command>

Commands:
    init            Initialize database (create DB, user, schema)
    init-force      Drop and recreate database (DESTRUCTIVE!)
    backup          Backup database to backups/ directory
    restore <file>  Restore database from backup file
    status          Show database status and table counts
    shell           Open psql shell
    reset-tracking  Reset case tracking table
    help            Show this help message

Examples:
    $0 init
    $0 backup
    $0 restore backups/backup_fct_db_20260128_120000.backup
    $0 status

EOF
}

function check_postgres() {
    if ! command -v psql &> /dev/null; then
        echo -e "${RED}Error: PostgreSQL client tools not found${NC}"
        echo "Please install postgresql-client"
        exit 1
    fi
}

function db_init() {
    echo -e "${GREEN}Initializing database...${NC}"
    python scripts/init_database.py "$@"
}

function db_backup() {
    echo -e "${GREEN}Creating backup...${NC}"
    python scripts/backup_database.py
}

function db_restore() {
    if [ -z "$1" ]; then
        echo -e "${RED}Error: Please specify backup file${NC}"
        echo "Usage: $0 restore <backup_file>"
        exit 1
    fi
    
    echo -e "${GREEN}Restoring from backup...${NC}"
    python scripts/restore_database.py "$1"
}

function db_status() {
    check_postgres
    
    echo -e "${GREEN}Database Status${NC}"
    echo "Host: $DB_HOST:$DB_PORT"
    echo "Database: $DB_NAME"
    echo "User: $DB_USER"
    echo ""
    
    export PGPASSWORD="$DB_PASSWORD"
    
    # Check connection
    if ! psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "\q" 2>/dev/null; then
        echo -e "${RED}✗ Cannot connect to database${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ Connection successful${NC}"
    echo ""
    
    # Get PostgreSQL version
    echo "PostgreSQL Version:"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT version();" | head -1
    echo ""
    
    # Get database size
    echo "Database Size:"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
        "SELECT pg_size_pretty(pg_database_size('$DB_NAME')) as size;"
    echo ""
    
    # List tables with row counts
    echo "Tables:"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
        "SELECT 
            schemaname,
            tablename,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
         FROM pg_tables 
         WHERE schemaname = 'public' 
         ORDER BY tablename;"
    echo ""
    
    # Row counts
    echo "Row Counts:"
    for table in cases docket_entries case_tracking scraper_runs; do
        count=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
            "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "N/A")
        printf "  %-20s %s\n" "$table:" "$count"
    done
}

function db_shell() {
    check_postgres
    echo -e "${GREEN}Opening PostgreSQL shell...${NC}"
    export PGPASSWORD="$DB_PASSWORD"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"
}

function db_reset_tracking() {
    check_postgres
    echo -e "${YELLOW}⚠️  This will clear all case tracking data${NC}"
    read -p "Continue? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ] && [ "$confirm" != "y" ]; then
        echo "Cancelled."
        exit 0
    fi
    
    export PGPASSWORD="$DB_PASSWORD"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c \
        "TRUNCATE TABLE case_tracking;"
    
    echo -e "${GREEN}✓ Case tracking table reset${NC}"
}

# Main command dispatcher
case "${1:-}" in
    init)
        db_init
        ;;
    init-force)
        db_init --drop
        ;;
    backup)
        db_backup
        ;;
    restore)
        db_restore "$2"
        ;;
    status)
        db_status
        ;;
    shell)
        db_shell
        ;;
    reset-tracking)
        db_reset_tracking
        ;;
    help|--help|-h)
        print_usage
        ;;
    *)
        echo -e "${RED}Error: Unknown command '${1:-}'${NC}"
        echo ""
        print_usage
        exit 1
        ;;
esac
