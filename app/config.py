"""
Configuración de la aplicación.

Un solo objeto `settings`, validado al importar. Si algo obligatorio falta o es
inseguro, el proceso **no arranca**: es preferible fallar en el despliegue a
descubrir en producción que se está firmando con una clave de desarrollo.
"""

from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Claves que alguna vez estuvieron en el repositorio o en su documentación.
# Arrancar con cualquiera de ellas equivale a no tener clave: quien lea el
# historial de git puede firmar un token de sesión válido para cualquier usuario.
KNOWN_PLACEHOLDER_SECRETS = frozenset(
    {
        "dev-secret-key-change-this",
        "change-this",
        "changeme",
        "secret",
        "supersecret",
        "your-secret-key",
        "CAMBIAR",
    }
)

MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Entorno ─────────────────────────────────────────────────────────────
    MODE: Literal["DEV", "TEST", "PROD"]
    LOG_LEVEL: str = "INFO"

    # Dominio base para resolver la compañía por subdominio.
    BASE_DOMAIN: str

    # ── Base de datos ───────────────────────────────────────────────────────
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str
    DB_PASS: str
    DB_NAME: str
    DB_CLOUDSQL_CONNECTION_NAME: str = ""

    DATABASE_URL: Optional[str] = None
    TEST_DATABASE_URL: Optional[str] = None

    # Conexiones que este proceso puede llegar a abrir a la vez
    # (`pool_size` + `max_overflow`, ver `database.py`). El valor por defecto
    # asume lo peor: el nodo más chico de un Postgres administrado (p.ej. el
    # tier de entrada de DigitalOcean, ~25 conexiones en total para toda la
    # base), una sola réplica del componente web, y margen real para
    # migraciones, `psql` manual y lo que el proveedor reserva para sí mismo.
    # Sin ese margen, un plan chico se agota igual sin ninguna ráfaga de por
    # medio (`TooManyConnectionsError` en producción, 2026-09-12). Súbelo sólo
    # tras confirmar el `max_connections` real y cuántas réplicas corren.
    DB_POOL_SIZE: int = Field(default=3, ge=1)
    DB_POOL_MAX_OVERFLOW: int = Field(default=2, ge=0)

    # ── Seguridad ───────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, ge=1)

    # Orígenes CORS separados por comas. Vacío = ninguno, que es lo correcto
    # cuando la propia aplicación sirve el frontend.
    CORS_ORIGINS: str = ""

    # ── Infraestructura ─────────────────────────────────────────────────────
    ENABLE_METRICS: bool = True
    # La documentación OpenAPI describe toda la superficie de la API. Se publica
    # sola en DEV; fuera de ahí hay que pedirla explícitamente.
    ENABLE_API_DOCS: bool = False

    # ── Identidad del proyecto ──────────────────────────────────────────────
    #
    # Una aplicación construida sobre esta base no reescribe plantillas ni
    # componentes para llamarse distinto: lo declara aquí.

    #: Identificador corto (logs, títulos de API, asunto de avisos).
    APP_NAME: str = "CER Application"
    #: Título visible en la pestaña del navegador y en la pantalla de login.
    APP_TITLE: str = "CER Application"
    #: Texto de marca junto al logo en el shell.
    APP_BRAND_LABEL: str = "CER Management Group"
    #: Subtítulo de marca bajo el texto (vacío = sin subtítulo).
    APP_BRAND_TAGLINE: str = ""
    #: Logo del shell, ruta bajo `/static`.
    APP_LOGO_PATH: str = "/static/img/cer-logo.svg"
    #: Icono cuadrado (favicon y shell colapsado), ruta bajo `/static`.
    APP_ICON_PATH: str = "/static/img/cer-icon.svg"
    #: Nombre del entorno que se muestra en la banda del shell. Vacío = se
    #: deriva de `MODE` (DEV muestra "Development environment"; PROD, nada).
    ENVIRONMENT_NAME: str = ""
    #: Adónde va un usuario autenticado que entra a `/` o a `/login`.
    DEFAULT_AUTHENTICATED_PATH: str = "/admin"

    # ── Archivos subidos ────────────────────────────────────────────────────
    #
    # Nada de esto se fija en el código: lista blanca, límite de tamaño y raíz
    # del almacén de desarrollo son política, no constantes.

    #: Tipos aceptados al subir un archivo. Lista blanca, no lista negra.
    UPLOAD_ALLOWED_TYPES: str = (
        "image/png,image/jpeg,image/heic,image/heif,image/webp,application/pdf"
    )
    #: Límite por archivo.
    UPLOAD_MAX_BYTES: int = Field(default=10 * 1024 * 1024, ge=1024)
    #: Raíz del adaptador de almacenamiento de DESARROLLO. Vacío = `./var/storage`.
    STORAGE_ROOT: str = ""

    # ── Integraciones entre aplicaciones ────────────────────────────────────
    #
    # Ver `docs/INTEGRATION_GUIDE.md`. Los secretos de cada contraparte no
    # viven aquí: se guardan cifrados por integración.

    #: Tolerancia, en segundos, entre el `timestamp` firmado de un webhook y el
    #: reloj propio. Fuera de ella la entrega se rechaza (anti-replay).
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS: int = Field(default=300, ge=30, le=3600)
    #: Tiempo máximo de una entrega saliente.
    WEBHOOK_DELIVERY_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=60)
    #: Intentos máximos de una entrega saliente antes de quedar `failed`.
    WEBHOOK_MAX_ATTEMPTS: int = Field(default=6, ge=1, le=20)
    #: Cuánto se recuerda una clave de idempotencia.
    IDEMPOTENCY_TTL_HOURS: int = Field(default=24, ge=1, le=24 * 30)

    # ── Correo ──────────────────────────────────────────────────────────────
    EMAIL_BACKEND: Literal["console", "memory", "smtp"] = "console"
    EMAIL_FROM: str = "no-reply@example.com"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True

    PASSWORD_RESET_TOKEN_MINUTES: int = Field(default=60, ge=1)

    # ── Almacén de secretos de plataforma (D12-01, fase 12) ─────────────────
    # Llave de 32 bytes en base64 que cifra las credenciales guardadas en la base
    # desde Settings. Es lo único de la configuración de integraciones que no
    # vive en la base: si viviera ahí, un volcado entregaría las credenciales y
    # la llave juntas. Generar con: python -m app.core.platform.secrets generate
    PLATFORM_MASTER_KEY: str = ""
    # La llave anterior, sólo mientras dura una rotación.
    PLATFORM_MASTER_KEY_PREVIOUS: str = ""
    # Chequeos programados, re-escaneo de cuarentena y avisos. Con varias
    # instancias sólo trabaja la que tiene el candado de PostgreSQL.
    PLATFORM_SCHEDULER_ENABLED: bool = True

    # ── Derivados ───────────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.MODE == "PROD"

    @property
    def is_testing(self) -> bool:
        return self.MODE == "TEST"

    @property
    def environment_label(self) -> str:
        """La banda de entorno del shell. Vacía en producción salvo que se pida."""
        if self.ENVIRONMENT_NAME:
            return self.ENVIRONMENT_NAME
        return {"DEV": "Development environment", "TEST": "Test environment"}.get(self.MODE, "")

    @property
    def docs_enabled(self) -> bool:
        """Swagger/OpenAPI: automático en DEV, explícito en el resto (D4)."""
        return self.MODE == "DEV" or self.ENABLE_API_DOCS

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def cookie_secure(self) -> bool:
        """`Secure` en las cookies: obligatorio en PROD, imposible en http local."""
        return self.is_production

    @property
    def allowed_hosts(self) -> list[str]:
        """Hosts que `TrustedHostMiddleware` acepta.

        El tenant se resuelve desde la cabecera `Host`, así que dejarla sin
        validar permitiría elegir tenant desde el cliente si algún día hay un
        proxy delante. Se admite el dominio base y cualquier subdominio suyo.
        """
        base = self.BASE_DOMAIN.strip().lower()
        hosts = [base, f"*.{base}"]
        if not self.is_production:
            # uvicorn en local y las sondas de infraestructura llegan por IP.
            hosts += ["localhost", "*.localhost", "127.0.0.1", "testserver"]
        return list(dict.fromkeys(hosts))

    # ── Validación ──────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _build_database_url(self):
        if self.DB_CLOUDSQL_CONNECTION_NAME:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
                f"@/{self.DB_NAME}?host=/cloudsql/{self.DB_CLOUDSQL_CONNECTION_NAME}"
            )
        else:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )
        return self


def _fail(message: str) -> None:
    """Aborta el arranque sin volcar la configuración en el mensaje.

    Las validaciones de seguridad NO se hacen como `model_validator` de pydantic
    a propósito: pydantic adjunta el diccionario de entrada al error, y ese
    diccionario lleva `DB_PASS` y `SECRET_KEY`. Un fallo de arranque acabaría
    escribiendo los secretos en el log del despliegue.
    """
    raise RuntimeError(f"Configuración inválida: {message}")


def _is_master_key(valor: str) -> bool:
    """Si el valor decodifica a exactamente 32 bytes (AES-256)."""
    import base64
    import binascii

    try:
        crudo = base64.urlsafe_b64decode(valor + "=" * (-len(valor) % 4))
    except (binascii.Error, ValueError):
        return False
    return len(crudo) == 32


def validate_settings(cfg: "Settings") -> "Settings":
    # ── Clave de firma ──────────────────────────────────────────────────────
    key = (cfg.SECRET_KEY or "").strip()

    if not key:
        _fail(
            "SECRET_KEY está vacía. Genera una con: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )

    if key in KNOWN_PLACEHOLDER_SECRETS:
        _fail(
            "SECRET_KEY es un placeholder conocido y publicado en el historial "
            "del repositorio. Cualquiera puede firmar un token de sesión válido "
            "con ella. Genera una nueva con: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )

    if len(key) < MIN_SECRET_KEY_LENGTH:
        _fail(
            f"SECRET_KEY tiene {len(key)} caracteres; se exigen al menos "
            f"{MIN_SECRET_KEY_LENGTH}."
        )

    # ── Base de datos de tests ──────────────────────────────────────────────
    # La suite recrea el esquema: apuntar a la base normal destruiría los datos
    # de desarrollo.
    if cfg.is_testing:
        if not cfg.TEST_DATABASE_URL:
            _fail(
                "MODE=TEST exige TEST_DATABASE_URL (ver .env.example). "
                "Debe ser una base distinta de DB_NAME."
            )
        if cfg.TEST_DATABASE_URL == cfg.DATABASE_URL:
            _fail(
                "TEST_DATABASE_URL apunta a la misma base que DATABASE_URL. "
                "La suite de tests recrea el esquema y destruiría los datos."
            )

    # ── Llave maestra de la plataforma ──────────────────────────────────────
    # Vacía no es un error: el proceso arranca y cada integración con secretos
    # informa de que la llave falta. Mal formada sí lo es, porque cifraría con
    # algo que nadie podría reproducir.
    for nombre in ("PLATFORM_MASTER_KEY", "PLATFORM_MASTER_KEY_PREVIOUS"):
        valor = (getattr(cfg, nombre) or "").strip()
        if valor and not _is_master_key(valor):
            _fail(
                f"{nombre} no es una llave de 32 bytes en base64. Genera una con: "
                "python -m app.core.platform.secrets generate"
            )

    # ── Endurecimiento de producción ────────────────────────────────────────
    # El correo ya no se exige aquí. Desde la fase 12 se configura en Settings y
    # vive en la base, que este validador no puede consultar: exigir
    # `EMAIL_BACKEND=smtp` al arrancar bloquearía un despliegue que tiene el
    # correo configurado y verificado. Lo comprueba el gate de correo de la
    # preparación para producción, que mira lo que de verdad se usa.
    if cfg.EMAIL_BACKEND == "smtp" and not cfg.SMTP_HOST:
        _fail("EMAIL_BACKEND=smtp exige SMTP_HOST.")

    return cfg


settings = validate_settings(Settings())
