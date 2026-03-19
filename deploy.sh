#!/bin/bash
# Script de Despliegue Agente ChatIA - CONTROL TOTAL

echo "--- 1. Limpieza de contenedores (Evitando conflictos) ---"
docker rm -f api worker frontend db redis vectorstore cloudflared 2>/dev/null || true
docker network rm chatia-net 2>/dev/null || true
docker network create chatia-net

# Cargar variables de entorno
if [ -f .env ]; then set -a; source .env; set +a; fi

echo "--- 2. Iniciando Base de Datos y Redis ---"
docker run -d --name db --network chatia-net \
  -e POSTGRES_USER=${POSTGRES_USER} -e POSTGRES_PASSWORD=${POSTGRES_PASSWORD} -e POSTGRES_DB=${POSTGRES_DB} \
  -v $(pwd)/data/postgres:/var/lib/postgresql/data --restart unless-stopped postgres:15-alpine

docker run -d --name redis --network chatia-net --restart unless-stopped redis:7-alpine

echo "--- 3. Iniciando VectorStore (Puerto 8002) ---"
docker run -d --name vectorstore --network chatia-net \
  -e CHROMA_SERVER_HOST=0.0.0.0 -e CHROMA_SERVER_HTTP_PORT=8000 \
  -v $(pwd)/data/chromadb:/chroma/chroma --restart unless-stopped chromadb/chroma:latest

echo "Esperando 10s..."
sleep 10

echo "--- 4. Iniciando API (Moviendo a Puerto 8001 para evitar conflicto) ---"
docker run -d --name api --network chatia-net -p 8001:8000 \
  -e DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}" \
  -e REDIS_URL="redis://redis:6379/0" \
  -e CHROMA_SERVER_HOST=vectorstore -e CHROMA_SERVER_HTTP_PORT=8000 \
  -v $(pwd)/backend:/app --restart unless-stopped chatia_api:latest

# Worker
echo "--- 5. Iniciando Worker ---"
docker run -d --name worker --network chatia-net \
  -e DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}" \
  -e REDIS_URL="redis://redis:6379/0" \
  -e CHROMA_SERVER_HOST=vectorstore -e CHROMA_SERVER_HTTP_PORT=8000 \
  -v $(pwd)/backend:/app --restart unless-stopped chatia_worker:latest \
  celery -A worker.celery_app worker --loglevel=info

echo "--- 6. Iniciando Frontend (Mapeo DUAL 8000 y 7860) ---"
# Lo mapeamos a ambos puertos para que no haya margen de error
docker run -d --name frontend --network chatia-net \
  -p 7860:7860 -p 8000:7860 \
  -e API_URL=http://api:8000 \
  -v $(pwd)/frontend:/app --restart unless-stopped chatia_frontend:latest

echo "--- 6. Iniciando Túnel de Cloudflare ---"
docker run -d --name cloudflared --network host \
  --restart unless-stopped \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}

echo "--- Verificación Final del Agente ---"
sleep 5
echo "Puertos activos:"
ss -tulpn | grep -E "7860|8000|8001"
echo "Contenedores:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
