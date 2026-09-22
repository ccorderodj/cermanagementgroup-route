"""
Contexto de compania para las dependencias de FastAPI.

`request.state.company` lo deja `CompanyResolverMiddleware` a partir del
subdominio. Es un `TenantContext`, no la entidad `Company`: ver
`app/routers_api/companies/context.py` para el porque.
"""

from fastapi import HTTPException, Request, status

from app.routers_api.companies.context import TenantContext


def get_company_optional(request: Request) -> TenantContext | None:
    return getattr(request.state, "company", None)


def get_company_required(request: Request) -> TenantContext:
    company = getattr(request.state, "company", None)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )
    return company
