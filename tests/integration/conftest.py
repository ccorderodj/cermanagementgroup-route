"""
Fixtures de los tests de integración.

Dos compañías, no una
---------------------
Todo se monta con **dos tenants** (`alpha` y `beta`) aunque un test concreto solo
use uno. Es deliberado: los fallos de aislamiento que encontró la auditoría son
invisibles con una sola compañía —el listado de roles "de todos los tenants"
devuelve lo mismo que el listado del tenant cuando solo hay uno— y esa es
exactamente la razón por la que llegaron a producción sin que nadie los viera.

Peticiones HTTP
---------------
Se habla con la aplicación ASGI en memoria, sin levantar un servidor. El host
decide el tenant, igual que en producción:

    await client_for("alpha").get("/api/roles")

El cliente resuelve además el testigo CSRF: carga primero `/login`, que emite la
cookie, y copia su valor a la cabecera en los métodos que mutan estado. Es lo
mismo que hace el navegador, así que los tests ejercitan la protección real en
vez de esquivarla.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select

from app.config import settings
from app.core.rbac.catalog import CAPABILITIES, DEFAULT_ROLES, capabilities_for
from app.core.security.csrf import CSRF_HEADER_NAME
from app.database import async_session_maker
from app.routers_api.companies.models import Company, UserCompany
from app.routers_api.permissions.models import Permission
from app.routers_api.regions.models import Region
from app.routers_api.rolepermissions.models import RolePermission
from app.routers_api.roles.models import Role
from app.routers_api.users.auth import get_password_hash
from app.routers_api.users.models import Users


TEST_PASSWORD = "TestPassword123!"


def _hash_de_prueba() -> str:
    """El hash de `TEST_PASSWORD`, calculado **una vez** por sesión.

    Los trece usuarios que siembra cada test tienen todos la misma contraseña,
    así que hasta ahora se calculaba trece veces el hash del mismo texto. Argon2
    es lento a propósito —58 ms por llamada, medido—, de modo que eran ~760 ms
    por test gastados en repetir un cálculo cuyo resultado ya se tenía.

    Esto **no** ablanda nada de lo que se prueba: el hash sigue siendo un argon2
    real con los parámetros de producción, y el login sigue verificándolo por el
    camino de siempre. Lo único que cambia es que todos los usuarios de prueba
    comparten la misma sal, que es exactamente igual de irrelevante que
    compartir la misma contraseña.
    """
    global _HASH_CACHE
    if _HASH_CACHE is None:
        _HASH_CACHE = get_password_hash(TEST_PASSWORD)
    return _HASH_CACHE


_HASH_CACHE: str | None = None


@dataclass(frozen=True)
class SeededUser:
    id: int
    email: str
    username: str
    role: str


@dataclass(frozen=True)
class SeededCompany:
    id: int
    subdomain: str
    roles: dict[str, int]
    users: dict[str, SeededUser]


@dataclass(frozen=True)
class Fixture:
    alpha: SeededCompany
    beta: SeededCompany
    platform_admin: SeededUser
    regions: dict[str, int]


async def _seed_capabilities(session) -> dict[str, int]:
    """El catálogo de capacidades, en una sentencia y no en setenta y ocho.

    Se siembran las mismas filas que antes y se salta las que ya estén; lo único
    que cambia es que se insertan juntas. Como `permission` se vacía entre tests,
    esto ocurría 78 veces por test.
    """
    existing = {
        row.name: row.id
        for row in (await session.execute(select(Permission))).scalars().all()
    }
    faltantes = [c for c in CAPABILITIES if c.name not in existing]
    if faltantes:
        filas = await session.execute(
            insert(Permission)
            .values([
                {"name": c.name, "description": c.description} for c in faltantes
            ])
            .returning(Permission.id, Permission.name)
        )
        for permission_id, name in filas.all():
            existing[name] = permission_id
    return existing


async def _seed_company(session, *, name: str, subdomain: str, capabilities) -> SeededCompany:
    company_id = (
        await session.execute(
            insert(Company)
            .values(name=name, subdomain=subdomain, domain=f"{subdomain}.test")
            .returning(Company.id)
        )
    ).scalar_one()

    roles: dict[str, int] = {}
    # Los permisos de los cuatro roles son 229 filas por compañía. Se juntan y
    # se insertan de una vez: son exactamente las mismas filas, y hacerlo de una
    # en una costaba 458 sentencias por test para sembrar algo que no cambia.
    concesiones: list[dict] = []
    for template in DEFAULT_ROLES:
        role_id = (
            await session.execute(
                insert(Role)
                .values(
                    company_id=company_id,
                    name=template.name,
                    description=template.description,
                    category=template.category,
                )
                .returning(Role.id)
            )
        ).scalar_one()
        roles[template.name] = role_id

        concesiones.extend(
            {
                "role_id": role_id,
                "permission_id": capabilities[capability_name],
                "is_active": True,
            }
            for capability_name in capabilities_for(template)
        )

    if concesiones:
        await session.execute(insert(RolePermission), concesiones)

    users: dict[str, SeededUser] = {}
    # Un usuario por rol, más dos casos límite que la auditoría demostró que no
    # se comprobaban en ninguna parte.
    accounts = [
        ("owner", "owner", True, True),
        ("admin", "admin", True, True),
        ("manager", "manager", True, True),
        ("viewer", "viewer", True, True),
        # Pertenencia suspendida: puede existir, pero no entra a ESTE tenant.
        ("suspended", "viewer", True, False),
        # Identidad deshabilitada en la plataforma: no entra a ninguna parte.
        ("disabled", "viewer", False, True),
        # CER Route: los dos roles del dominio de campo. `route_admin`
        # administra la configuración operativa; `supervisor` no administra
        # nada, y probar eso es justamente el punto.
        ("route_admin", "route_admin", True, True),
        ("supervisor", "supervisor", True, True),
    ]

    for key, role_name, platform_active, membership_active in accounts:
        username = f"{subdomain}_{key}"
        user_id = (
            await session.execute(
                insert(Users)
                .values(
                    username=username,
                    email=f"{key}@{subdomain}.example.com",
                    password=_hash_de_prueba(),
                    first_name=key.capitalize(),
                    last_name="Tester",
                    is_active=platform_active,
                    is_superuser=False,
                )
                .returning(Users.id)
            )
        ).scalar_one()

        await session.execute(
            insert(UserCompany).values(
                user_id=user_id,
                company_id=company_id,
                role_id=roles[role_name],
                is_active=membership_active,
            )
        )

        users[key] = SeededUser(
            id=user_id,
            email=f"{key}@{subdomain}.example.com",
            username=username,
            role=role_name,
        )

    return SeededCompany(id=company_id, subdomain=subdomain, roles=roles, users=users)


#: Tablas protegidas por disparadores append-only. Una aplicación de dominio
#: añade aquí las suyas.
APPEND_ONLY_TABLES: tuple[str, ...] = (
    "audit_event",
    "integration_event",
    "platform_audit_event",
    "platform_health_check_run",
)

#: Todas las tablas con datos, hijos antes que padres. `region` se siembra en
#: cada test, así que también se vacía.
TABLES_IN_DELETE_ORDER: tuple[str, ...] = (
    "audit_event",
    # CER Route: hijos antes que padres. `vehicle_assignment` referencia a
    # `supervisor_profile` y `vehicle`, y `supervisor_profile` a `user_company`.
    # `work_session` referencia a `vehicle` (RESTRICT), así que va antes.
    # RTE04: hijos antes que padres. `trip_purpose_change` referencia a
    # `trip`, y `trip` a `work_session` y a `standard_value`.
    # RTE04: la evidencia de odometro referencia jornada y vehiculo.
    "odometer_exception_request",
    "odometer_evidence",
    "trip_purpose_change",
    "trip",
    "work_session",
    "vehicle_assignment",
    "supervisor_profile",
    "vehicle",
    "standard_value",
    "integration_event",
    "idempotency_record",
    "webhook_delivery",
    "webhook_endpoint",
    "platform_audit_event",
    "platform_health_check_run",
    "platform_secret",
    "platform_integration",
    "platform_policy",
    "platform_health_check",
    "role_permission_change_request",
    "role_permission",
    "user_company",
    "company_state",
    "role",
    "permission",
    '"user"',
    "company",
    "region",
)


@pytest_asyncio.fixture
async def seeded(database_schema) -> Fixture:
    """Dos compañías completas, sus roles, sus usuarios y el catálogo.

    Se siembra por test (no por sesión) para que ninguno dependa de lo que haya
    dejado otro: los tests de aislamiento crean y borran filas, y compartir el
    estado convertiría un fallo en una cascada difícil de leer.
    """
    from sqlalchemy import text

    async with async_session_maker() as session:
        # Las tablas append-only rechazan `UPDATE`, `DELETE` y `TRUNCATE` por
        # disparador, y el borrado en cascada desde `company` también los
        # dispara. Se desactivan **solo aquí**, en la limpieza entre tests, y se
        # vuelven a activar acto seguido. Es una excepción deliberada de la
        # infraestructura de pruebas: la aplicación no tiene ningún camino para
        # hacer esto, y ese es justamente el control que se quiere conservar.
        for tabla in APPEND_ONLY_TABLES:
            await session.execute(text(f"ALTER TABLE {tabla} DISABLE TRIGGER USER"))

        # Orden inverso al de las dependencias.
        for table in TABLES_IN_DELETE_ORDER:
            await session.execute(text(f"DELETE FROM {table}"))

        for tabla in APPEND_ONLY_TABLES:
            await session.execute(text(f"ALTER TABLE {tabla} ENABLE TRIGGER USER"))
        await session.commit()

    async with async_session_maker() as session:
        capabilities = await _seed_capabilities(session)

        regions: dict[str, int] = {}
        for code, name in (("GA", "Georgia"), ("TX", "Texas"), ("FL", "Florida")):
            regions[code] = (
                await session.execute(
                    insert(Region).values(code=code, name=name).returning(Region.id)
                )
            ).scalar_one()

        alpha = await _seed_company(
            session, name="Alpha Company", subdomain="alpha", capabilities=capabilities
        )
        beta = await _seed_company(
            session, name="Beta Company", subdomain="beta", capabilities=capabilities
        )

        # Administrador de plataforma: por encima de cualquier tenant (D6).
        # Se le da pertenencia a alpha para poder entrar por su subdominio.
        platform_id = (
            await session.execute(
                insert(Users)
                .values(
                    username="platform_admin",
                    email="platform@example.com",
                    password=_hash_de_prueba(),
                    first_name="Platform",
                    last_name="Admin",
                    is_active=True,
                    is_superuser=True,
                )
                .returning(Users.id)
            )
        ).scalar_one()
        await session.execute(
            insert(UserCompany).values(
                user_id=platform_id,
                company_id=alpha.id,
                role_id=alpha.roles["viewer"],
                is_active=True,
            )
        )

        await session.commit()

    return Fixture(
        alpha=alpha,
        beta=beta,
        platform_admin=SeededUser(
            id=platform_id,
            email="platform@example.com",
            username="platform_admin",
            role="viewer",
        ),
        regions=regions,
    )


class TenantClient:
    """Cliente HTTP atado a un subdominio, con CSRF resuelto."""

    def __init__(self, subdomain: str) -> None:
        from app.main import app

        self._client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url=f"http://{subdomain}.{settings.BASE_DOMAIN}",
            follow_redirects=False,
        )

    async def __aenter__(self) -> "TenantClient":
        # Cargar el login emite la cookie CSRF, igual que en un navegador.
        await self._client.get("/login")
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.aclose()

    def _headers(self, extra: dict | None = None) -> dict:
        headers = dict(extra or {})
        token = self._client.cookies.get("cer_csrf_token")
        if token:
            headers[CSRF_HEADER_NAME] = token
        return headers

    async def get(self, url: str, **kwargs):
        return await self._client.get(url, **kwargs)

    async def post(self, url: str, headers: dict | None = None, **kwargs):
        return await self._client.post(url, headers=self._headers(headers), **kwargs)

    async def put(self, url: str, headers: dict | None = None, **kwargs):
        return await self._client.put(url, headers=self._headers(headers), **kwargs)

    async def patch(self, url: str, headers: dict | None = None, **kwargs):
        return await self._client.patch(url, headers=self._headers(headers), **kwargs)

    async def delete(self, url: str, headers: dict | None = None, **kwargs):
        return await self._client.delete(url, headers=self._headers(headers), **kwargs)

    async def reload_login_page(self):
        """Vuelve a cargar `/login`, que reemite la cookie CSRF.

        Cambiar la contrasena o cerrar sesion BORRA el testigo CSRF junto con la
        sesion. Un navegador siempre vuelve a cargar una pagina despues —el
        enlace "volver al inicio de sesion"— y con ella recibe uno nuevo. Sin
        esta llamada, la siguiente peticion que muta estado se rechaza con 403 y
        el test acaba comprobando el CSRF en vez de lo que pretendia.
        """
        return await self._client.get("/login")

    async def login(self, email: str, password: str = TEST_PASSWORD):
        response = await self.post(
            "/api/public/auth/login",
            json={"email": email, "password": password},
        )
        # Tras iniciar sesión el servidor rota el testigo CSRF; el cliente ya lo
        # tiene en sus cookies y `_headers` lo recogerá.
        return response

    @property
    def cookies(self):
        return self._client.cookies


@pytest_asyncio.fixture
async def alpha_client():
    async with TenantClient("alpha") as client:
        yield client


@pytest_asyncio.fixture
async def alpha_anonymous():
    """El mismo tenant, sin sesion interna. Nunca llama a `login`.

    Sirve para demostrar que una superficie funciona (o se niega) sin sesión,
    en vez de hacerlo con una sesión iniciada que ocultaría cuál credencial abre
    la puerta.
    """
    async with TenantClient("alpha") as client:
        yield client


@pytest_asyncio.fixture
async def beta_client():
    async with TenantClient("beta") as client:
        yield client


@pytest.fixture
def tenant_client():
    """Fábrica, para los tests que necesitan varias sesiones a la vez."""
    return TenantClient
