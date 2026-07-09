# ─── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Dependências do sistema (mínimas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências de produção
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ─── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copia apenas o que precisa
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copia o código da aplicação
COPY licita/ ./licita/

# Porta padrão do Cloud Run
ENV PORT=8080

# Usuário não-root para segurança
RUN useradd -m -u 1001 appuser
USER appuser

EXPOSE 8080

# Cloud Run injeta $PORT; uvicorn respeita 0.0.0.0 para ser alcançável
CMD ["sh", "-c", "uvicorn licita.api:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2"]
