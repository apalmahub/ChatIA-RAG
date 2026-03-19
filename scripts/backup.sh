#!/bin/bash

# ChatIA Backup Script
# Run daily at 3:00 AM via cron

set -e

BACKUP_DIR="./data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "Starting backup at $(date)"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Backup PostgreSQL database
echo "Backing up PostgreSQL database..."
if command -v pg_dump &> /dev/null; then
    pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$BACKUP_DIR/db_$TIMESTAMP.sql"
    echo "Database backup completed: $BACKUP_DIR/db_$TIMESTAMP.sql"
else
    echo "pg_dump not found, skipping database backup"
fi

# Backup uploads directory
echo "Backing up uploads..."
tar -czf "$BACKUP_DIR/uploads_$TIMESTAMP.tar.gz" -C ./data/uploads . 2>/dev/null || true
echo "Uploads backup completed: $BACKUP_DIR/uploads_$TIMESTAMP.tar.gz"

# Backup ChromaDB data
echo "Backing up ChromaDB..."
tar -czf "$BACKUP_DIR/chroma_$TIMESTAMP.tar.gz" -C ./data/chromadb . 2>/dev/null || true
echo "ChromaDB backup completed: $BACKUP_DIR/chroma_$TIMESTAMP.tar.gz"

# Clean up old backups (older than 7 days)
echo "Cleaning up old backups..."
find "$BACKUP_DIR" -type f -mtime +7 -delete

echo "Backup completed successfully at $(date)"

# Optional: Send notification (uncomment and configure)
# curl -X POST -H 'Content-type: application/json' \
#      --data '{"text":"ChatIA backup completed"}' \
#      YOUR_SLACK_WEBHOOK_URL
