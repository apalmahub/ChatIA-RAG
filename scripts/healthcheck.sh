#!/bin/bash

# ChatIA Health Check Script
# Use with Docker healthcheck or monitoring

# Check PostgreSQL
if pg_isready -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    echo "PostgreSQL: OK"
else
    echo "PostgreSQL: FAIL"
    exit 1
fi

# Check Redis
if redis-cli -h redis ping | grep -q PONG; then
    echo "Redis: OK"
else
    echo "Redis: FAIL"
    exit 1
fi

# Check ChromaDB
if curl -f http://vectorstore:8000/api/v1/heartbeat >/dev/null 2>&1; then
    echo "ChromaDB: OK"
else
    echo "ChromaDB: FAIL"
    exit 1
fi

# Check API
if curl -f http://api:8000/health >/dev/null 2>&1; then
    echo "API: OK"
else
    echo "API: FAIL"
    exit 1
fi

echo "All services healthy"
exit 0
