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
