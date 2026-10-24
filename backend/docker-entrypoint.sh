#!/bin/sh
set -e

# Ensure data directory exists for SQLite storage
if [ -n "$DATABASE_PATH" ]; then
    DB_DIR=$(dirname "$DATABASE_PATH")
    if [ "$DB_DIR" != "." ] && [ "$DB_DIR" != "/" ]; then
        mkdir -p "$DB_DIR"
    fi
fi

# Apply database migrations
if [ -f "alembic.ini" ]; then
    echo "Applying database migrations..."
    alembic upgrade head
fi

# Execute the primary container command
exec "$@"
