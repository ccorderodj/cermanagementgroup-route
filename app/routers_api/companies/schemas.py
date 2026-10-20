from datetime import datetime
from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core import schema
from app.routers_api.worksessions.time_zones import zona_valida


class CompanyBase(BaseModel):
    name: str


class CompanyRead(CompanyBase):
    id: int
    subdomain: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyProfileResponse(BaseModel):
    id: int
    name: str
    # Se devuelven para que la interfaz pueda mostrarlos, pero son de solo
    # lectura: `CompanyProfileUpdate` no los admite.
    domain: Optional[str] = None
    subdomain: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_secondary: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    pdf_text_color: Optional[str] = None
    pdf_muted_text_color: Optional[str] = None
    pdf_surface_color: Optional[str] = None
    operational_time_zone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CompanyProfileUpdate(BaseModel):
    """Lo que un administrador de tenant puede cambiar de su compañía.

    **`domain` y `subdomain` quedan deliberadamente fuera** (D5). Son la clave
    con la que `CompanyResolverMiddleware` resuelve el tenant: cambiarlos dejaba
    la compañía inalcanzable para todos sus usuarios —administradores incluidos—
    y la única recuperación era por SQL. Ese cambio pertenece a administración
    de plataforma, no al perfil de la compañía.
    """

    name: str = Field(min_length=1)
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_secondary: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    pdf_text_color: Optional[str] = None
    pdf_muted_text_color: Optional[str] = None
    pdf_surface_color: Optional[str] = None
    #: Zona IANA (`America/New_York`). Vacía: sin zona de compañía.
    operational_time_zone: Optional[str] = Field(default=None, max_length=64)

    model_config = ConfigDict(extra="forbid")

    @field_validator("operational_time_zone")
    @classmethod
    def validate_time_zone(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        zona = zona_valida(value)
        if zona is None:
            raise ValueError("Unknown time zone: use an IANA name like America/New_York")
        return zona

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Company name is required")
        return normalized


class CompaniesPaginationParams(schema.CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        name: Optional[str] = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.name = (name or "").strip() or None
