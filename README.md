# CER Application Foundation

Base reutilizable para construir aplicaciones CER como **monolitos modulares**
pequeños, cada uno con su dominio acotado, que se integran entre sí por REST
versionado y webhooks firmados en las dos direcciones.

No trae ningún dominio de negocio. Trae lo que toda aplicación CER necesita y ya
se probó en producción:

- FastAPI + PostgreSQL + SQLAlchemy 2 async + Alembic, con configuración validada al arrancar.
- Multi-tenancy por subdominio: compañía, usuarios, pertenencias, roles y capacidades.
- Autenticación por cookie HttpOnly, CSRF de doble envío y autorización por capacidad en el servidor.
- Frontera de administración de plataforma (`is_superuser`) separada de la del tenant.
- Auditoría append-only, control de concurrencia por versión y cabeceras de seguridad.
- Errores homogéneos, diagnósticos de salud y puertas de preparación para producción.
- Secretos cifrados, almacenamiento y escaneo de archivos, y correo con respaldo.
- Integración entre aplicaciones: API versionada `/api/v1`, webhooks entrantes y salientes firmados, idempotencia y metadatos de integración.
- React 19 + TypeScript servido por Jinja con el patrón **ruta → plantilla → page-key**, Redux Toolkit, Axios, Zod, shell con barra lateral y kit de UI.
- pytest contra PostgreSQL real, tipado, lint, build de producción y CI.

Documentación:

| Documento | Para qué |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Cómo está armada la base y por qué |
| [`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md) | La disciplina de trabajo: fuente de verdad, migraciones, tests, evidencia |
| [`docs/DOMAIN_EXTENSION_GUIDE.md`](docs/DOMAIN_EXTENSION_GUIDE.md) | Cómo añadir un módulo de dominio sin romper la base |
| [`docs/INTEGRATION_GUIDE.md`](docs/INTEGRATION_GUIDE.md) | REST versionado, webhooks, firma, idempotencia, correlación |
| [`AGENTS.md`](AGENTS.md) | Invariantes y reglas para quien (persona o agente) cambia el código |
| [`EXTRACTION_REPORT.md`](EXTRACTION_REPORT.md) | De dónde sale esta base y cómo se validó |

---

## Lo que hay que saber antes de nada

1. **La aplicación exige un subdominio.** `http://localhost:8000` devuelve 404.
   La compañía se resuelve desde `<subdominio>.<BASE_DOMAIN>`: en desarrollo se
   entra por `http://cer.localhost:8000`. Los navegadores resuelven cualquier
   `*.localhost` sin tocar `hosts`. Sólo `/health`, `/health/ready` y
   `/metrics` funcionan sin subdominio.
2. **El bundle de React se genera; no está en el repositorio.** Tras clonar,
   `npm run build:prod` (o `build:dev`) dentro de `app/`.
3. **El `.env` se crea a mano** a partir de `.env.example`. La aplicación no
   arranca con configuración incompleta ni con un `SECRET_KEY` débil.

## Requisitos

- Python 3.13 y [`uv`](https://docs.astral.sh/uv/)
- Node 22 y npm 10
- PostgreSQL 14 o superior

## Puesta en marcha

```bash
# 1. Dependencias de Python (exactamente las del lockfile)
uv sync --frozen

# 2. Base de datos: rol de la aplicación sin superusuario, y base de tests.
#    Como `postgres`, una sola vez (crea antes la base `cer_app`):
psql -h localhost -U postgres -c "CREATE DATABASE cer_app"
psql -h localhost -U postgres -d cer_app -f app/db/scripts/01-crear-rol-aplicacion.sql
psql -h localhost -U postgres -d postgres -f app/db/scripts/03-crear-base-de-pruebas.sql

# 3. Configuración
cp .env.example .env      # rellenar DB_PASS, SECRET_KEY, PLATFORM_MASTER_KEY, APP_*

# 4. Esquema y siembra (compañía, capacidades, roles y administrador inicial)
uv run alembic -c app/alembic.ini upgrade head
uv run python -m app.db.scripts.bootstrap

# 5. Frontend
cd app && npm ci && npm run build:prod && cd ..

# 6. Arrancar
uv run uvicorn app.main:app --reload --port 8000
```

Entrar en `http://<BOOTSTRAP_COMPANY_SUBDOMAIN>.localhost:8000` con el correo
del administrador y la contraseña que imprimió el bootstrap.

## Comandos

| Qué | Comando |
|---|---|
| Importar la aplicación (humo) | `uv run python -c "import app.main"` |
| Migraciones | `uv run alembic -c app/alembic.ini upgrade head` |
| Comprobar que modelos y migraciones coinciden | `uv run alembic -c app/alembic.ini check` |
| Nueva migración | `uv run alembic -c app/alembic.ini revision --autogenerate -m "..."` |
| Tests (unit + integration) | `uv run pytest` (necesita `MODE=TEST` y `TEST_DATABASE_URL`) |
| Sólo unit | `uv run pytest tests/test_*.py` |
| Errores reales de Python | `uv run flake8 --select=E9,F63,F7,F82 app tests` |
| Tipado frontend | `cd app && npm run typecheck` |
| Lint frontend | `cd app && npm run lint:ts` |
| Build de producción | `cd app && npm run build:prod` |
| Build de desarrollo (conserva `data-testid`) | `cd app && npm run build:dev` |
| Docker (app + PostgreSQL) | `docker compose up --build` |
| Docker (suite) | `docker compose run --rm tests` |

## Estructura

```text
app/
  main.py                    composición: raíz, /api (privada, pública, /v1), páginas
  config.py                  Settings validados al arrancar (identidad APP_*, BD, seguridad)
  core/                      plataforma transversal (sin dominio)
    audit/  dao/  db/  middleware/  security/  storage/  email/  platform/
    rbac/catalog.py          catálogo de capacidades: FUENTE ÚNICA
    integration/             /api/v1, webhooks, firma, idempotencia, eventos de integración
  routers_api/               módulos de la API interna: companies, users, roles, permissions…
  routers_api_public/        lista blanca de endpoints sin sesión
  routers_pages/             rutas de página (name= es el page-key)
  templates/                 Jinja: base.html + un ancla por página
  components/react/          app/ entities/ features/ pages/ shared/ widgets/
  migrations/versions/       0001_foundation_baseline.py (única revisión de la base)
  db/scripts/                bootstrap y SQL de roles/bases
tests/                       unit (sin BD) e integration (PostgreSQL real)
docs/                        arquitectura, flujo de trabajo, extensión, integración
```
