#!/usr/bin/env bash
# Local pg_dump/pg_restore drill. This is not encrypted point-in-time recovery.
set -euo pipefail

SOURCE="${1:-grok_m0_e2e}"
TARGET="grok_m0_restore"
DUMP="/tmp/grok_m0_restore.dump"

sudo -u postgres pg_dump -Fc "$SOURCE" -f "$DUMP"
sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TARGET' AND pid <> pg_backend_pid()" >/dev/null
sudo -u postgres dropdb --if-exists "$TARGET"
sudo -u postgres createdb "$TARGET"
sudo -u postgres pg_restore -d "$TARGET" "$DUMP"
sudo -u postgres psql -d "$TARGET" -v ON_ERROR_STOP=1 -c "SELECT 'properties' AS table_name, count(*) FROM properties UNION ALL SELECT 'journal_entries', count(*) FROM journal_entries UNION ALL SELECT 'owner_statements', count(*) FROM owner_statements ORDER BY 1;"
sudo rm -f "$DUMP"
echo "local backup restore drill completed for $SOURCE"
