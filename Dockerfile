# =============================================================================
# Imagen de la aplicación
# =============================================================================
# El Dockerfile anterior no construía: usaba Python 3.12 cuando el proyecto
# exige >=3.13, copiaba un `requirements.txt` que no existe —las dependencias
# están en pyproject.toml— y un directorio `./docker` que tampoco existe, y
# tenía los dos CMD comentados, así que la imagen no habría tenido comando
# (AUD-TOOL-004).
#
# Construcción en dos etapas: el bundle de React se genera aquí, no se copia
# desde el árbol de trabajo. Los artefactos de `app/static/javascript/` dejaron
# de estar versionados (D0), así que la imagen tiene que producirlos.
# =============================================================================

# ── Etapa 1: bundle del frontend ─────────────────────────────────────────────
FROM node:22-slim AS frontend

WORKDIR /build

# Las dependencias primero: cambian mucho menos que el código, así que la capa
# se reaprovecha entre builds.
COPY app/package.json app/package-lock.json ./
RUN npm ci

COPY app/tsconfig.json app/webpack.config.ts app/babel.config.json ./
COPY app/postcss.config.js app/tailwind.config.js ./
COPY app/configwebpack ./configwebpack
COPY app/components ./components
COPY app/templates ./templates

RUN npm run build:prod


# ── Etapa 2: aplicación ──────────────────────────────────────────────────────
FROM python:3.13-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

# `uv` resuelve desde el lockfile, así que la imagen instala exactamente las
# mismas versiones que hay en desarrollo.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# El bundle viene de la etapa anterior.
COPY --from=frontend /build/static/javascript ./app/static/javascript

# Sin privilegios: si algo se cuela por la aplicación, no es root quien lo
# ejecuta.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /code
USER appuser

ENV PATH="/code/.venv/bin:${PATH}"

EXPOSE 8000

# `/health` no depende de resolver el tenant (D11): antes el único health check
# estaba detrás del resolutor de compañía y devolvía 404 sin un subdominio
# válido, que es justo lo que envía un orquestador.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
