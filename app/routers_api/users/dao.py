from sqlalchemy import select, update

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.companies.models import UserCompany
from app.routers_api.users.models import Users


class UsersDAO(BaseDAO):
    model = Users

    # ── Lecturas de sesión ──────────────────────────────────────────────────

    @classmethod
    async def find_active_by_id(cls, user_id: int) -> Users | None:
        """El usuario, solo si su identidad de plataforma sigue habilitada.

        `Users.is_active` se comprueba aquí y no en el llamador para que ninguna
        ruta de autenticación pueda olvidarlo (D7).
        """
        async with db_session() as session:
            stmt = select(Users).where(
                Users.id == user_id,
                Users.is_active.is_(True),
            )
            return await session.scalar(stmt)

    @classmethod
    async def find_active_membership(
        cls,
        *,
        user_id: int,
        company_id: int,
    ) -> UserCompany | None:
        async with db_session() as session:
            stmt = select(UserCompany).where(
                UserCompany.user_id == user_id,
                UserCompany.company_id == company_id,
                UserCompany.is_active.is_(True),
            )
            return await session.scalar(stmt)

    @classmethod
    async def find_login_candidate(cls, *, email: str, company_id: int) -> Users | None:
        """Usuario que puede iniciar sesión en esta compañía.

        Exige las dos banderas: identidad global activa y pertenencia activa a
        este tenant. Devuelve `None` en todos los casos de fallo —usuario
        inexistente, desactivado, o sin membresía— para que el llamador no pueda
        construir una respuesta que los distinga (AUD-BE-006).
        """
        normalized = (email or "").strip().lower()

        async with db_session() as session:
            stmt = (
                select(Users)
                .join(UserCompany, UserCompany.user_id == Users.id)
                .where(
                    Users.email.ilike(normalized),
                    Users.is_active.is_(True),
                    UserCompany.company_id == company_id,
                    UserCompany.is_active.is_(True),
                )
                .limit(1)
            )
            return await session.scalar(stmt)

    @classmethod
    async def display_name(cls, user_id: int | None) -> str | None:
        """El nombre con el que se enseña a una persona.

        Vive aqui porque lo necesitan varios dominios —el Job Opening lo copia
        al registrar, la asignacion de reclutamiento al asignar— y tener dos
        implementaciones habria hecho que la misma persona apareciera con dos
        nombres distintos en dos pantallas.

        Cae al `username` cuando no hay nombre y apellidos: una fila sin nada
        que mostrar es peor que una con el identificador de acceso.
        """
        if user_id is None:
            return None
        async with db_session() as session:
            usuario = await session.get(Users, user_id)
        if usuario is None:
            return None
        return (
            " ".join(p for p in (usuario.first_name, usuario.last_name) if p).strip()
            or usuario.username
        )

    @classmethod
    async def user_belongs_to_company(cls, user_id: int, company_id: int) -> bool:
        membership = await cls.find_active_membership(
            user_id=user_id,
            company_id=company_id,
        )
        return membership is not None

    # ── Escrituras ──────────────────────────────────────────────────────────

    @classmethod
    async def set_password_hash(cls, user_id: int, password_hash: str) -> None:
        """Persiste un hash nuevo. Se usa también para el rehash transparente."""
        async with db_session() as session:
            await session.execute(
                update(Users).where(Users.id == user_id).values(password=password_hash)
            )
            await session.commit()

    @classmethod
    async def touch_last_login(cls, user_id: int, when) -> None:
        async with db_session() as session:
            await session.execute(
                update(Users).where(Users.id == user_id).values(last_login=when)
            )
            await session.commit()

    @classmethod
    async def update_profile_by_user_id(cls, user_id: int, data: dict) -> Users | None:
        """Actualiza el perfil propio. `new_password` se traduce a hash Argon2id."""
        from app.routers_api.users.auth import get_password_hash

        values = dict(data)
        trimmed_password = (values.pop("new_password", "") or "").strip()
        if trimmed_password:
            values["password"] = get_password_hash(trimmed_password)

        if isinstance(values.get("email"), str):
            values["email"] = values["email"].strip().lower()

        async with db_session() as session:
            await session.execute(
                update(cls.model)
                .where(cls.model.id == user_id)
                .values(**values)
                .execution_options(synchronize_session="fetch")
            )
            await session.commit()

            return await session.scalar(
                select(cls.model).where(cls.model.id == user_id)
            )
