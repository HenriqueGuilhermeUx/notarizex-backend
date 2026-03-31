#!/bin/bash
set -e

# Railway injeta $PORT dinamicamente — este script garante que o gunicorn leia corretamente
PORT="${PORT:-5000}"
echo "Iniciando NotarizeX Backend na porta $PORT..."
exec gunicorn app:app --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120 --log-level info
