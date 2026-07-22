FROM python:3.12-slim

# LibreOffice (headless) para convertir los recibos .xlsx a PDF antes de enviarlos.
# Se instala solo Calc + core; fuentes DejaVu vienen con libreoffice-core.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-core \
        libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copiar archivos de configuración del workspace
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY packages/contracts/pyproject.toml packages/contracts/
COPY packages/api/pyproject.toml packages/api/
# bot y desktop no son dependencias de la API, pero uv necesita sus pyproject.toml
# para resolver el workspace correctamente
COPY packages/bot/pyproject.toml packages/bot/
COPY packages/desktop/pyproject.toml packages/desktop/

# Instalar dependencias (sin grupos dev, sin bot ni desktop)
RUN uv sync --package coop-api --no-dev --frozen

# Copiar el código fuente
COPY packages/core/src packages/core/src
COPY packages/contracts/src packages/contracts/src
COPY packages/api/src packages/api/src

EXPOSE 8080

CMD ["sh", "-c", "uv run --package coop-api uvicorn coop_api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
