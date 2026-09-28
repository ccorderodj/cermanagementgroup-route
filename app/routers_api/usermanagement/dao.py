"""
Gestión de los usuarios de una compañía.

Todo lo que hay aquí está acotado a `company_id`. Se retiraron los métodos
`*_global` (`create_global_user`, `update_global_user`, `get_total_global`,
`calculate_offset_global`, `_find_global_user_row`): ningún endpoint los
llamaba, y eran precisamente los que operaban sin compañía.

`is_superuser` ya no se acepta como dato de entrada en ninguna operación.
"""

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session, transaction
from app.routers_api.companies.models import UserCompany
from app.routers_api.roles.models import Role
from app.routers_api.users.auth import get_password_hash
from app.routers_api.users.models import Users


def _row_columns():
    """Las columnas que ve quien administra usuarios de una compañía."""
    return (
        Users.id.label("id"),
        Users.username.label("username"),
        Users.email.label("email"),
        Users.first_name.label("first_name"),
        Users.last_name.label("last_name"),
        Users.gender.label("gender"),
        Users.is_superuser.label("is_superuser"),
        Users.is_active.label("is_platform_active"),
        Users.last_login.label("last_login"),
        Users.date_joined.label("date_joined"),
        UserCompany.created_at.label("created_at"),
        UserCompany.updated_at.label("updated_at"),
        UserCompany.company_id.label("company_id"),
        UserCompany.role_id.label("role_id"),
        UserCompany.is_active.label("is_active"),
        Role.name.label("role_name"),
    )


class UserManagementDAO(BaseDAO):
    model = Users

    @classmethod
    def query(
        cls,
        *,
        company_id: int,
        q: str | None = None,
        is_active: bool | None = None,
        **_: object,
    ) -> Select:
        stmt = (
            select(*_row_columns())
            .select_from(Users)
            .join(UserCompany, UserCompany.user_id == Users.id)
            .join(
                Role,
                and_(
                    Role.id == UserCompany.role_id,
                    Role.company_id == UserCompany.company_id,
                ),
            )
            .where(
                UserCompany.company_id == company_id,
                # Quien fue borrado del tenant sale de la experiencia normal:
                # no aparece ni entre los activos ni entre los suspendidos.
                UserCompany.deleted_at.is_(None),
            )
        )

        # `is_active` filtra por la PERTENENCIA, que es lo que administra el
        # tenant, no por la identidad global.
        if is_active is not None:
            stmt = stmt.where(UserCompany.is_active.is_(is_active))

        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Users.username.ilike(like),
                    Users.email.ilike(like),
                    Users.first_name.ilike(like),
                    Users.last_name.ilike(like),
                )
            )

        return stmt

    @classmethod
    def default_order(cls):
        return Users.id.desc()

    @classmethod
    async def find_for_company(cls, *, user_id: int, company_id: int) -> dict:
        async with db_session() as session:
            row = (
                await session.execute(
                    cls.query(company_id=company_id).where(Users.id == user_id)
                )
            ).mappings().first()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found for this company",
            )
        return dict(row)

    # ── Escrituras ──────────────────────────────────────────────────────────

    @staticmethod
    def _integrity_detail(exc: IntegrityError, default: str) -> str:
        raw = str(getattr(exc, "orig", exc) or "").lower()
        if "user_username_key" in raw or "key (username)" in raw:
            return "Username already exists. Please choose a different one."
        if "uq_user_company_user_company" in raw:
            return "This user is already linked to this company."
        if "fk_user_company_role_same_company" in raw:
            return "The selected role does not belong to this company."
        return default

    @classmethod
    async def list_assignable_roles(
        cls, *, company_id: int, actor_user_id: int, actor_is_superuser: bool
    ) -> list[dict]:
        """Los roles que este actor puede conceder, con su etiqueta de producto.

        Quien administra desde CER Route recibe **sus dos roles de producto** y
        nada más; es la misma frontera que aplica `ensure_assignable_role` al
        escribir, leída de la misma constante para que no puedan divergir.

        Quien administra desde el núcleo sigue viendo el catálogo del tenant, que
        es el comportamiento que ya tenía y que esta resolución no cambia.
        """
        from app.core.rbac.catalog import (
            ROUTE_PRODUCT_ROLES,
            ROUTE_PRODUCT_ROLE_LABELS,
        )
        from app.routers_api.usermanagement.role_policy import _rol_de_quien_llama

        rol_del_actor = (
            None
            if actor_is_superuser
            else await _rol_de_quien_llama(
                user_id=actor_user_id, company_id=company_id
            )
        )
        acotado_a_route = rol_del_actor in ROUTE_PRODUCT_ROLES

        async with db_session() as session:
            filas = await session.execute(
                select(Role.id, Role.name)
                .where(Role.company_id == company_id, Role.is_active.is_(True))
                .order_by(Role.name.asc())
            )

        opciones: list[dict] = []
        for role_id, nombre in filas.all():
            if acotado_a_route and nombre not in ROUTE_PRODUCT_ROLES:
                continue
            opciones.append({
                "id": role_id,
                "code": nombre,
                # Los roles del núcleo no tienen etiqueta de producto: se
                # muestran por su nombre, capitalizado por la pantalla.
                "label": ROUTE_PRODUCT_ROLE_LABELS.get(nombre, nombre),
            })
        return opciones

    @classmethod
    async def _assert_role_of_company(cls, session, *, role_id: int, company_id: int) -> None:
        role = await session.scalar(
            select(Role).where(
                Role.id == role_id,
                Role.company_id == company_id,
                Role.is_active.is_(True),
            )
        )
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found in this company",
            )

    @classmethod
    async def create_user_with_company_role(
        cls,
        *,
        company_id: int,
        username: str,
        password: str,
        role_id: int,
        email: str,
        first_name: str,
        last_name: str,
        gender: bool = False,
    ) -> dict:
        """Crea el usuario y su pertenencia **en una sola transacción**.

        Antes eran dos operaciones con su propio commit cada una: si la segunda
        fallaba, quedaba un usuario huérfano sin compañía (AUD-BE-015).
        """
        try:
            async with transaction() as session:
                await cls._assert_role_of_company(
                    session,
                    role_id=role_id,
                    company_id=company_id,
                )

                user_id = (
                    await session.execute(
                        insert(Users)
                        .values(
                            username=username.strip(),
                            email=email.strip().lower(),
                            password=get_password_hash(password),
                            first_name=first_name.strip(),
                            last_name=last_name.strip(),
                            gender=gender,
                            # Identidad de plataforma: siempre activa al crear.
                            # Suspender es cosa de la pertenencia.
                            is_active=True,
                            # Nunca desde una API de tenant (D6).
                            is_superuser=False,
                        )
                        .returning(Users.id)
                    )
                ).scalar_one()

                await session.execute(
                    insert(UserCompany).values(
                        user_id=user_id,
                        company_id=company_id,
                        role_id=role_id,
                        is_active=True,
                    )
                )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=cls._integrity_detail(exc, "Could not create the user."),
            ) from exc

        return await cls.find_for_company(user_id=user_id, company_id=company_id)

    @classmethod
    async def update_user_in_company(
        cls,
        *,
        user_id: int,
        company_id: int,
        role_id: int | None = None,
        password: str | None = None,
        **user_fields,
    ) -> dict:
        """Datos del usuario y su rol, en una sola transacción.

        Antes el router hacía dos llamadas independientes —datos y rol— cada una
        con su commit, así que un fallo al asignar el rol dejaba los datos ya
        escritos (AUD-BE-015).
        """
        values = {k: v for k, v in user_fields.items() if v is not None}

        if isinstance(values.get("username"), str):
            values["username"] = values["username"].strip()
        if isinstance(values.get("email"), str):
            values["email"] = values["email"].strip().lower()
        if password:
            values["password"] = get_password_hash(password)

        if not values and role_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided to update",
            )

        try:
            async with transaction() as session:
                membership = await session.scalar(
                    select(UserCompany).where(
                        UserCompany.user_id == user_id,
                        UserCompany.company_id == company_id,
                    )
                )
                if membership is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found for this company",
                    )

                if values:
                    await session.execute(
                        update(Users).where(Users.id == user_id).values(**values)
                    )

                if role_id is not None:
                    await cls._assert_role_of_company(
                        session,
                        role_id=role_id,
                        company_id=company_id,
                    )
                    membership.role_id = role_id
                    session.add(membership)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=cls._integrity_detail(exc, "Could not update the user."),
            ) from exc

        return await cls.find_for_company(user_id=user_id, company_id=company_id)

    @classmethod
    async def set_membership_access(
        cls,
        *,
        user_id: int,
        company_id: int,
        is_active: bool,
    ) -> dict:
        """Activa o suspende la pertenencia a ESTA compañía (D7)."""
        async with transaction() as session:
            result = await session.execute(
                update(UserCompany)
                .where(
                    UserCompany.user_id == user_id,
                    UserCompany.company_id == company_id,
                    UserCompany.deleted_at.is_(None),
                )
                .values(is_active=is_active)
                .returning(UserCompany.id)
            )
            if result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found for this company",
                )

        return await cls.find_for_company(user_id=user_id, company_id=company_id)

    @classmethod
    async def delete_membership(cls, *, user_id: int, company_id: int) -> dict:
        """Retira a la persona de ESTA compañía. **No destruye su identidad.**

        `user` puede pertenecer a otras compañías y al plano de plataforma, así
        que quien administra un tenant no puede borrarla: borra lo que posee,
        que es la pertenencia. Y la borra con lápida, porque
        `supervisor_profile` la referencia con `CASCADE` y un `DELETE` físico se
        llevaría por delante la designación de Route de esa persona junto con su
        historial de vehículos.

        Devuelve la fila **antes** de marcarla: el llamador la necesita para
        dejar en la auditoría a quién se retiró, y después de la lápida ya no
        sería recuperable por la consulta normal.
        """
        previo = await cls.find_for_company(user_id=user_id, company_id=company_id)

        async with transaction() as session:
            result = await session.execute(
                update(UserCompany)
                .where(
                    UserCompany.user_id == user_id,
                    UserCompany.company_id == company_id,
                    UserCompany.deleted_at.is_(None),
                )
                .values(deleted_at=func.now())
                .returning(UserCompany.id)
            )
            if result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found for this company",
                )

        return previo
