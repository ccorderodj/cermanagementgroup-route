"""
Contexto de tenant que viaja en `request.state.company`.

Es deliberadamente **no** el modelo `Company`. Resolver el tenant ocurre en cada
petición —incluidas las de archivos estáticos—, y pedir la entidad ORM completa
arrastraba sus relaciones `selectin` (`company_states`, `user_companies`,
`users`), es decir, cuatro consultas extra por request (AUD-BE-027).

Aquí solo están los campos que necesitan la resolución del tenant y la marca que
pinta la interfaz. Quien necesite la entidad completa la pide explícitamente con
`CompaniesDAO.get_for_profile(company_id)`.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True, slots=True)
class TenantContext:
    id: int
    name: str
    subdomain: str
    address: Optional[str] = None
    email: Optional[str] = None
    phone_secondary: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    brand_primary_color: Optional[str] = None
    brand_secondary_color: Optional[str] = None
    pdf_text_color: Optional[str] = None
    pdf_muted_text_color: Optional[str] = None
    pdf_surface_color: Optional[str] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "TenantContext":
        return cls(**{field: row[field] for field in cls.__annotations__ if field in row})
