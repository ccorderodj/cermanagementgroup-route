from datetime import datetime
from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core import schema
from app.routers_api.users.schemas import MIN_PASSWORD_LENGTH


class UserManagementCreate(BaseModel):
    """Alta de un usuario en la compañía activa.

    **`is_superuser` no está aquí y no debe volver.** Era un campo del cuerpo
    que el DAO pasaba tal cual al `INSERT`, así que cualquiera con el permiso
    `users.create` podía fabricarse un administrador de plataforma y saltarse
    todo el RBAC en todos los tenants (AUD-SEC-012). El privilegio de plataforma
    se administra fuera de las APIs de tenant (D6).
    """

    username: str = Field(min_length=1)
    email: EmailStr
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    gender: bool = False
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    role_id: int

    model_config = ConfigDict(extra="forbid")


class UserManagementUpdate(BaseModel):
    """Edición de un usuario de la compañía activa.

    Tampoco admite `is_superuser` ni `is_active`: suspender el acceso tiene su
    propio endpoint (`PUT /users/{id}/access`) y actúa sobre la pertenencia a
    esta compañía, no sobre la identidad global (D7).
    """

    username: Optional[str] = Field(default=None, min_length=1)
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(default=None, min_length=1)
    last_name: Optional[str] = Field(default=None, min_length=1)
    gender: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=MIN_PASSWORD_LENGTH)
    # El rol vive en `user_company`, pero desde la interfaz es un campo más del
    # usuario. Debe ser un rol de esta compañía; la base lo impone.
    role_id: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class UserAccessUpdate(BaseModel):
    """Activa o suspende el acceso del usuario **a esta compañía**.

    Escribe en `UserCompany.is_active`, no en `Users.is_active`. La diferencia
    importa: la identidad global es de administración de plataforma, y antes
    este endpoint la tocaba —además de que el login no la comprobaba, así que
    "suspender" no suspendía nada (AUD-BE-032).
    """

    is_active: bool


class UserManagementRead(BaseModel):
    id: int
    username: str
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: bool

    # Estado de la pertenencia a ESTA compañía: lo que administra el tenant.
    is_active: bool
    # Estado de la identidad en la plataforma: informativo, solo lectura.
    is_platform_active: bool = True
    # Informativo, solo lectura. No se puede asignar desde ninguna API de tenant.
    is_superuser: bool = False

    last_login: Optional[datetime] = None
    date_joined: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    company_id: Optional[int] = None
    role_id: Optional[int] = None
    role_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AssignableRoleRead(BaseModel):
    """Un rol que quien administra usuarios **puede** conceder aquí.

    Lleva la etiqueta de producto, no el código técnico: la pantalla nunca
    muestra `route_admin`. Y lleva sólo lo que hace falta para rellenar un
    selector — nada de capacidades ni categorías, que no son asunto del
    formulario y exponerlas filtraría la taxonomía del núcleo a un cliente que no
    la necesita.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label: str


class UsersPaginationParams(schema.CommonQueryParams):
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        q: Optional[str] = Query(None),
        is_active: Optional[bool] = Query(None),
    ):
        super().__init__(page=page, page_size=page_size)
        self.q = (q or "").strip() or None
        self.is_active = is_active
