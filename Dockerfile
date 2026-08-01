# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile para Swarmind Harness.
# - Stage 1 (builder): instala dependencias en una imagen completa.
# - Stage 2 (runtime): imagen slim con solo el codigo y deps, non-root user.
# Beneficios: imagen final mas pequena (~200MB vs ~1GB), mejor cache de layers.

ARG PYTHON_VERSION=3.11

# ---------------------------------------------------------------------------
# Stage 1: builder (imagen completa con build tools)
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app

# System deps: git (para clones), curl (healthcheck opcional), build-essential (compilacion nativa)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv (gestor de deps rapido)
RUN pip install --no-cache-dir uv

# Copiar solo archivos de dependencias primero (cache de layers)
COPY pyproject.toml uv.lock README.md ./

# Instalar dependencias en un venv (luego copiamos solo el venv a runtime)
RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python -e ".[dev]"

# ---------------------------------------------------------------------------
# Stage 2: runtime (imagen slim, sin build tools)
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

WORKDIR /app

# Runtime deps minimos (git para clones, curl para healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Crear usuario no-root para ejecucion segura
RUN groupadd --system --gid 1001 swarmind \
    && useradd --system --uid 1001 --gid swarmind --create-home --shell /bin/bash swarmind \
    && mkdir -p /app/data /app/.opencode \
    && chown -R swarmind:swarmind /app

# Copiar venv del builder (solo deps, sin codigo)
COPY --from=builder --chown=swarmind:swarmind /app/.venv /app/.venv

# Activar venv por defecto (PATH)
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Copiar codigo del proyecto
COPY --chown=swarmind:swarmind . .

# Cambiar a usuario no-root
USER swarmind

# Healthcheck: verifica que Python responde (importar harness).
# En produccion podria reemplazarse por un endpoint HTTP si se expone uno.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import harness; print('OK')" || exit 1

# Default command (puede sobreescribirse en docker-compose o docker run)
CMD ["python", "-m", "harness.run"]
