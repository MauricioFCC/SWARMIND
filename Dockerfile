# Imagen de referencia para un usuario nuevo / CI de onboarding.
#
#   docker build -t swarmind-harness .
#   docker run --rm swarmind-harness
#
# El nucleo no requiere GPU ni LanceDB: `pip install .` solo trae
# numpy/pyyaml/requests/schedule. Para memoria persistente:
#   docker build --build-arg EXTRAS=lancedb -t swarmind-harness:lancedb .
#
# Nota: la DLL de RuscaDB es un artefacto por plataforma (Windows en este
# repo); en Linux el almacen degrada a LanceDB o al fallback in-memory.

FROM python:3.12-slim

ARG EXTRAS=test

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[${EXTRAS}]"

# Usuario no-root (UID 1001) para ejecutar el harness y montar ./data.
RUN useradd --create-home --uid 1001 harness \
    && chown -R 1001:1001 /app
USER 1001

# Smoke de instalacion limpia (import, memory backend, CLI, degradacion RuscaDB)
RUN python scripts/new_user_smoke.py

CMD ["python", "-m", "harness", "--help"]
