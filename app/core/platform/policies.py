"""
Políticas operativas editables desde Settings.

No son secretos: el tamaño máximo de un archivo o la frecuencia de los chequeos
no necesitan cifrado ni un almacén aprobado. Vivían en el entorno, así que
cambiarlas exigía redesplegar (S6). Cada política tiene un esquema con límites,
y lo que no está guardado vale su valor por defecto —el del entorno, si lo hay—.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings


class UploadPolicy(BaseModel):
    allowed_types: list[str] = Field(min_length=1)
    max_bytes: int = Field(ge=1024, le=50 * 1024 * 1024)
    #: Lado mayor al que se reduce una foto al normalizarla (WP-6).
    max_image_dimension: int = Field(default=3000, ge=800, le=8000)
    jpeg_quality: int = Field(default=85, ge=50, le=95)
    max_pdf_pages: int = Field(default=20, ge=1, le=100)

    @field_validator("allowed_types")
    @classmethod
    def _tipos(cls, valor: list[str]) -> list[str]:
        limpios = [t.strip().lower() for t in valor if t.strip()]
        permitidos = {
            "image/jpeg", "image/png", "image/heic", "image/heif", "image/webp", "application/pdf",
        }
        desconocidos = sorted(set(limpios) - permitidos)
        if desconocidos:
            raise ValueError(f"unsupported file types: {', '.join(desconocidos)}")
        return limpios


class HealthCheckPolicy(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(default=60, ge=5, le=1440)


class RouteLocationPolicy(BaseModel):
    """Cuándo un punto de ubicación sirve, y cuánto se espera por uno.

    Los valores por defecto son **técnicamente defendibles, no certificados**.
    §26 prohíbe fijar los números indicativos de RTE01 como constantes
    aprobadas por CER, así que viven aquí —ajustables sin desplegar— y su
    validación depende de V-2 y V-5, que necesitan muestreo en campo.

    De dónde sale cada uno:

    * `fresh_timeout_seconds` 10 — el intento de posición actual. Más largo
      retrasaría la ventana de recuperación sin mejorar la probabilidad: un GPS
      que no ha fijado en 10 s con alta precisión no suele fijar a los 20.
    * `cached_max_age_seconds` 300 — cinco minutos. Un punto de hace cinco
      minutos en un vehículo en marcha puede estar a varios kilómetros, así que
      esto es el límite de lo que todavía dice algo sobre dónde ocurrió el
      evento. Es el número que más claramente pide validación con datos reales.
    * `cached_max_accuracy_m` 500 — medio kilómetro. Por encima, el punto no
      distingue una parada de la siguiente.
    * `recovery_window_seconds` 180 — tres minutos de reintento silencioso.
      Acotado porque §11 lo exige acotado.
    * `sweeper_grace_seconds` 120 — margen antes de que el servidor dé por
      perdido un evento del que el cliente no volvió a decir nada. Cubre una
      sincronización lenta sin dejar el evento pendiente para siempre.
    """

    fresh_timeout_seconds: int = Field(default=10, ge=1, le=60)
    fresh_max_accuracy_m: int = Field(default=100, ge=1, le=10_000)
    cached_max_age_seconds: int = Field(default=300, ge=1, le=86_400)
    cached_max_accuracy_m: int = Field(default=500, ge=1, le=100_000)
    recovery_window_seconds: int = Field(default=180, ge=10, le=3_600)
    sweeper_grace_seconds: int = Field(default=120, ge=0, le=3_600)


class RouteMileagePolicy(BaseModel):
    """Cuándo un tramo enrutado es creíble, y cuántas veces se reintenta.

    Mismo estatus que los de ubicación: defendibles y **no** certificados.

    * `segment_max_meters` 800_000 — 800 km entre dos paradas consecutivas de
      la misma jornada. No es un límite de negocio: es el punto a partir del
      cual el resultado es casi seguro un error de coordenada, no un viaje.
    * `implied_speed_max_kmh` 160 — distancia dividida por el tiempo entre las
      dos capturas. Atrapa la clase de error que un límite de distancia no ve:
      50 km en cuatro minutos.
    * `max_attempts` 5 con `backoff_base_seconds` 60 — reintento acotado (§24:
      ningún viaje puede quedar Pending indefinidamente). Cinco intentos con
      backoff exponencial cubren unos 30 minutos de caída del proveedor.
    * `request_timeout_seconds` 5 — por tramo. Un routing que tarda más que
      esto no es un problema de latencia, es un proveedor caído.
    """

    segment_max_meters: int = Field(default=800_000, ge=1_000, le=20_000_000)
    implied_speed_max_kmh: int = Field(default=160, ge=10, le=1_000)
    plausibility_enabled: bool = True
    max_attempts: int = Field(default=5, ge=1, le=20)
    backoff_base_seconds: int = Field(default=60, ge=5, le=3_600)
    request_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    sweeper_interval_minutes: int = Field(default=5, ge=1, le=60)


@dataclass(frozen=True)
class PolicyDefinition:
    key: str
    title: str
    summary: str
    schema: type[BaseModel]
    defaults: Callable[[], dict]


POLICIES: tuple[PolicyDefinition, ...] = (
    PolicyDefinition(
        key="upload",
        title="Upload & media policy",
        summary="Which files users may upload, and how photos are normalized.",
        schema=UploadPolicy,
        defaults=lambda: {
            "allowed_types": [
                t.strip() for t in settings.UPLOAD_ALLOWED_TYPES.split(",") if t.strip()
            ],
            "max_bytes": settings.UPLOAD_MAX_BYTES,
            "max_image_dimension": 3000,
            "jpeg_quality": 85,
            "max_pdf_pages": 20,
        },
    ),
    PolicyDefinition(
        key="health_checks",
        title="Scheduled checks",
        summary="How often Diagnostics checks every configured integration on its own.",
        schema=HealthCheckPolicy,
        defaults=lambda: {"enabled": True, "interval_minutes": 60},
    ),
    PolicyDefinition(
        key="route_location",
        title="Route location evidence",
        summary="When a location point is good enough, and how long recovery waits.",
        schema=RouteLocationPolicy,
        defaults=lambda: RouteLocationPolicy().model_dump(),
    ),
    PolicyDefinition(
        key="route_mileage",
        title="Route official mileage",
        summary="Plausibility limits and bounded retry for routed trip mileage.",
        schema=RouteMileagePolicy,
        defaults=lambda: RouteMileagePolicy().model_dump(),
    ),
)

BY_KEY: dict[str, PolicyDefinition] = {p.key: p for p in POLICIES}


def validate(key: str, value: dict) -> tuple[dict | None, list[str]]:
    definicion = BY_KEY[key]
    combinado = {**definicion.defaults(), **(value or {})}
    try:
        modelo = definicion.schema.model_validate(combinado)
    except ValidationError as exc:
        return None, [
            f"{'.'.join(str(p) for p in e['loc']) or key}: {e['msg']}" for e in exc.errors()
        ]
    return modelo.model_dump(), []
