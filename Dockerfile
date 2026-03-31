FROM python:3.11-slim

# Diretório de trabalho
WORKDIR /app

# Copiar requirements primeiro (cache de camadas)
COPY requirements.txt .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o restante do código
COPY . .

# Expor porta (Railway usa $PORT dinamicamente)
EXPOSE 8080

# Iniciar com gunicorn lendo $PORT do ambiente
CMD gunicorn app:app --bind "0.0.0.0:${PORT:-8080}" --workers 2 --timeout 120 --log-level info
