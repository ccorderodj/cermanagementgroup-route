from fastapi import HTTPException, status
from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError

from app.core.dao.base import BaseDAO
from app.core.db.session import db_session
from app.routers_api.companies.models import Company, UserCompany
from app.routers_api.companies.schemas import CompanyProfileResponse
from app.routers_api.roles.models import Role
from app.routers_api.users.models import Users


class CompaniesDAO(BaseDAO):
    model = Company

    @classmethod
    async def list_active_members(cls, *, company_id: int) -> list[dict]:
        """Los usuarios internos activos de esta compañía, para elegir en un selector.

        Vive aquí y no en el módulo que lo necesita primero, a propósito: es la
        pregunta que muchos dominios hacen ("¿quién puede figurar como
        responsable de esto?"), y duplicar la consulta en cada uno habría
        significado corregir el mismo bug en varios sitios el día que apareciera.
        Cada dominio la expone bajo su propio permiso: el listado en sí no
        concede `users.read`.
        """
        async with db_session() as session:
            filas = await session.execute(
                select(
                    Users.id,
                    Users.first_name,
                    Users.last_name,
                    Users.username,
                    Role.name.label("role_name"),
                )
                .select_from(UserCompany)
                .join(Users, Users.id == UserCompany.user_id)
                .outerjoin(Role, Role.id == UserCompany.role_id)
                .where(
                    UserCompany.company_id == company_id,
                    UserCompany.is_active.is_(True),
                    UserCompany.deleted_at.is_(None),
                    Users.is_active.is_(True),
                )
                .order_by(Users.first_name.asc(), Users.last_name.asc())
            )
            salida = []
            for fila in filas.all():
                datos = dict(fila._mapping)
                nombre = " ".join(
                    parte for parte in (datos["first_name"], datos["last_name"]) if parte
                ).strip()
                salida.append(
                    {
                        "user_id": datos["id"],
                        "display_name": nombre or datos["username"],
                        "role_name": datos["role_name"],
                    }
                )
            return salida

    @classmethod
    def query(cls, *, name: str | None = None, **_: object) -> Select:
        stmt = select(Company)
        if name:
            stmt = stmt.where(Company.name.ilike(f"%{name}%"))
        return stmt

    @classmethod
    async def find_by_subdomain(cls, subdomain: str) -> Company | None:
        """Resolución del tenant. Es la consulta más caliente del sistema.

        Se seleccionan columnas sueltas en vez de la entidad a propósito: el
        modelo `Company` carga `company_states`, `user_companies` y `users` con
        `lazy="selectin"`, así que pedir la entidad completa aquí disparaba
        cuatro consultas extra en **cada** petición, incluidas las de archivos
        estáticos (AUD-BE-027).
        """
        normalized = (subdomain or "").strip().lower()
        if not normalized:
            return None

        async with db_session() as session:
            row = await session.execute(
                select(
                    Company.id,
                    Company.name,
                    Company.subdomain,
                    Company.address,
                    Company.email,
                    Company.phone_secondary,
                    Company.website,
                    Company.logo_url,
                    Company.brand_primary_color,
                    Company.brand_secondary_color,
                    Company.pdf_text_color,
                    Company.pdf_muted_text_color,
                    Company.pdf_surface_color,
                )
                .where(
                    Company.subdomain == normalized,
                    Company.is_active.is_(True),
                )
                .limit(1)
            )
            return row.mappings().first()

    @classmethod
    async def get_for_profile(cls, company_id: int) -> Company | None:
        async with db_session() as session:
            return await session.scalar(
                select(Company).where(Company.id == company_id)
            )

    @classmethod
    async def update_profile_by_company_id(cls, *, company_id: int, data: dict) -> dict:
        """Actualiza datos de negocio y marca.

        `domain` y `subdomain` no llegan hasta aquí: `CompanyProfileUpdate` ya
        no los admite. Se filtran igualmente por si alguien construyera el dict
        a mano — un cambio de subdominio deja la compañía inalcanzable (D5).
        """
        values = {
            key: value
            for key, value in data.items()
            if key not in {"domain", "subdomain", "id", "is_active"}
        }

        nullable_fields = (
            "address",
            "phone",
            "email",
            "phone_secondary",
            "website",
            "logo_url",
            "brand_primary_color",
            "brand_secondary_color",
            "pdf_text_color",
            "pdf_muted_text_color",
            "pdf_surface_color",
        )
        for field_name in nullable_fields:
            value = values.get(field_name)
            if isinstance(value, str):
                values[field_name] = value.strip() or None

        if isinstance(values.get("name"), str):
            values["name"] = values["name"].strip()

        async with db_session() as session:
            try:
                await session.execute(
                    update(Company).where(Company.id == company_id).values(**values)
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Company values must be unique",
                ) from exc

            company = await session.scalar(
                select(Company).where(Company.id == company_id)
            )
            if not company:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Company not found",
                )

            result = CompanyProfileResponse.model_validate(company).model_dump()

        # `CompanyResolverMiddleware` cachea la identidad del tenant. Aquí se
        # acaba de cambiar (nombre, logo, colores), así que hay que olvidarla o
        # las páginas seguirían pintando la marca anterior hasta un minuto.
        from app.core.middleware.company_resolver_middleware import invalidate_tenant_cache

        invalidate_tenant_cache(company.subdomain)
        return result
