"""
Cuenta propia del usuario autenticado.

Este router es **privado**: cuelga de `api_router`, que exige sesión.
Lo que puede hacerse sin sesión —iniciarla, cerrarla, recuperar la contraseña—
vive en `public_router.py` y se declara endpoint a endpoint.

`POST /auth/register` ya no existe: no hay auto-registro en el producto (D2).
Las altas las hace administración desde `POST /api/users`, que exige el permiso
`users.create` y crea el usuario ya vinculado a la compañía.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.routers_api.companies.dependencies import get_company_required
from app.routers_api.companies.context import TenantContext
from app.routers_api.companies.models import UserCompany
from app.routers_api.users.dao import UsersDAO
from app.routers_api.users.dependencies import get_current_membership, get_current_user
from app.routers_api.users.models import Users
from app.routers_api.users.schemas import SUserProfileResponse, SUserProfileUpdate


router = APIRouter(prefix="/auth", tags=["Auth & Users"])


@router.get("/profile", response_model=SUserProfileResponse)
async def get_profile(
    current_user: Users = Depends(get_current_user),
    _membership: UserCompany = Depends(get_current_membership),
):
    return SUserProfileResponse.model_validate(current_user)


@router.put("/profile", response_model=SUserProfileResponse)
async def update_profile(
    payload: SUserProfileUpdate,
    current_user: Users = Depends(get_current_user),
    _membership: UserCompany = Depends(get_current_membership),
    _company: TenantContext = Depends(get_company_required),
):
    try:
        updated_user = await UsersDAO.update_profile_by_user_id(
            current_user.id,
            data=payload.model_dump(),
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already exists",
        ) from exc

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return SUserProfileResponse.model_validate(updated_user)
