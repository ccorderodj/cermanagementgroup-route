"""
Matriz de autorización: cada endpoint frente a cada clase de usuario.

Cuatro clases, que es lo que pedía el encargo:

    anónimo                     sin sesión
    autenticado sin permiso     `viewer`, que solo lee
    autenticado con permiso     `owner`, con el catálogo entero
    plataforma                  `is_superuser`

Es el test que habría detectado `AUD-SEC-004` (perfil de compañía editable sin
permiso), `AUD-SEC-005` (listado de tenants para cualquier autenticado) y
`AUD-BE-001` (páginas de administración sin comprobar permisos).
"""

from urllib.parse import quote

import pytest

from app.core.rbac.catalog import DEFAULT_ROLES, capabilities_for
from tests.integration.conftest import TEST_PASSWORD


pytestmark = pytest.mark.integration


# (método, ruta, cuerpo, permiso que exige)
PERMISSION_PROTECTED = [
    ("GET", "/api/roles", None, "roles.read"),
    ("GET", "/api/roles/pagination", None, "roles.read"),
    ("GET", "/api/permissions", None, "permissions.read"),
    ("GET", "/api/permissions/feature-map", None, "permissions.read"),
    ("GET", "/api/rolepermissions", None, "rolepermissions.read"),
    ("GET", "/api/rolepermissionsapprovals/pagination", None, "rolepermissionsapprovals.read"),
    ("GET", "/api/users/pagination", None, "users.read"),
    ("GET", "/api/regions", None, "regions.read"),
    ("GET", "/api/regions/catalog", None, "regions.read"),
    ("GET", "/api/companies/profile", None, "companies.read"),
]

# Lo que concede el rol `viewer` sale del catálogo, no de una lista copiada:
# una capacidad nueva concedida a `viewer` habría dejado esta matriz mintiendo
# sin que nada lo indicara.
VIEWER_CAPABILITIES = set(
    capabilities_for(next(t for t in DEFAULT_ROLES if t.name == "viewer"))
)

ADMIN_PAGES = [
    "/admin/clients/list",
    "/admin/security/users/list",
    "/admin/security/roles/list",
    "/admin/security/permissions/list",
    "/admin/security/role-permission-requests/list",
    "/admin/companies/profile",
    "/admin/locations/states",
]


@pytest.mark.parametrize("method,path,body,permission", PERMISSION_PROTECTED)
async def test_anonymous_is_rejected(seeded, alpha_client, method, path, body, permission):
    response = await alpha_client.get(path) if method == "GET" else await alpha_client.post(path, json=body)
    assert response.status_code == 401, f"{method} {path} debería exigir sesión"


@pytest.mark.parametrize("method,path,body,permission", PERMISSION_PROTECTED)
async def test_viewer_only_reaches_what_its_role_grants(
    seeded, alpha_client, method, path, body, permission,
):
    """`viewer` solo alcanza lo que su rol concede en el catálogo."""
    await alpha_client.login(seeded.alpha.users["viewer"].email)

    response = await alpha_client.get(path)

    if permission in VIEWER_CAPABILITIES:
        assert response.status_code == 200, (
            f"{path} exige {permission}, que viewer tiene: debería pasar."
        )
    else:
        assert response.status_code == 403, (
            f"{path} exige {permission}, que viewer NO tiene: debería ser 403."
        )


@pytest.mark.parametrize("method,path,body,permission", PERMISSION_PROTECTED)
async def test_owner_reaches_everything(seeded, alpha_client, method, path, body, permission):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get(path)
    assert response.status_code == 200, f"owner debería poder con {path}"


# ── Compañías: tenant frente a plataforma ───────────────────────────────────


async def test_company_list_is_platform_only(seeded, alpha_client):
    """Devuelve TODOS los tenants: no es una operación de tenant (D6)."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.get("/api/companies")
    assert response.status_code == 403, (
        "El owner de un tenant no debe poder listar todas las compañías de la "
        "plataforma."
    )


async def test_platform_admin_can_list_companies(seeded, alpha_client):
    await alpha_client.login(seeded.platform_admin.email)

    response = await alpha_client.get("/api/companies")
    assert response.status_code == 200

    names = {row["name"] for row in response.json()}
    assert {"Alpha Company", "Beta Company"} <= names


async def test_company_profile_update_requires_the_update_capability(seeded, alpha_client):
    """Antes bastaba con estar autenticado: hasta un viewer podía editarlo."""
    await alpha_client.login(seeded.alpha.users["viewer"].email)

    response = await alpha_client.put(
        "/api/companies/profile",
        json={"name": "Renamed by a viewer"},
    )
    assert response.status_code == 403


async def test_owner_can_update_the_company_profile(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.put(
        "/api/companies/profile",
        json={"name": "Alpha Company Renamed"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Alpha Company Renamed"


async def test_subdomain_cannot_be_changed_from_the_company_profile(seeded, alpha_client):
    """Cambiarlo dejaba la compañía inalcanzable para todos sus usuarios (D5)."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.put(
        "/api/companies/profile",
        json={"name": "Alpha Company", "subdomain": "hijacked"},
    )

    assert response.status_code == 422, (
        "El schema debe rechazar `subdomain`: es configuración de plataforma."
    )

    from sqlalchemy import select

    from app.database import async_session_maker
    from app.routers_api.companies.models import Company

    async with async_session_maker() as session:
        subdomain = await session.scalar(
            select(Company.subdomain).where(Company.id == seeded.alpha.id)
        )
    assert subdomain == "alpha"


# ── Escalada de privilegios ─────────────────────────────────────────────────


async def test_tenant_admin_cannot_grant_platform_privilege(seeded, alpha_client):
    """`is_superuser` no se acepta en el alta de usuarios (D6, AUD-SEC-012)."""
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.post(
        "/api/users",
        json={
            "username": "sneaky",
            "email": "sneaky@alpha.example.com",
            "first_name": "Sneaky",
            "last_name": "User",
            "password": TEST_PASSWORD,
            "role_id": seeded.alpha.roles["viewer"],
            "is_superuser": True,
        },
    )

    assert response.status_code == 422, (
        "El schema debe rechazar `is_superuser`: es privilegio de plataforma."
    )


async def test_created_users_are_never_platform_admins(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.post(
        "/api/users",
        json={
            "username": "regular",
            "email": "regular@alpha.example.com",
            "first_name": "Regular",
            "last_name": "User",
            "password": TEST_PASSWORD,
            "role_id": seeded.alpha.roles["viewer"],
        },
    )

    assert response.status_code == 200
    assert response.json()["is_superuser"] is False


async def test_tenant_admin_cannot_promote_an_existing_user(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)

    response = await alpha_client.put(
        f"/api/users/{seeded.alpha.users['viewer'].id}",
        json={"is_superuser": True},
    )
    assert response.status_code == 422


# ── Páginas ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ADMIN_PAGES)
async def test_admin_pages_redirect_anonymous_visitors(seeded, alpha_client, path):
    """`next=` (RTE03, D-09) vuelve a donde estaba quien perdió la sesión.

    Antes redirigía a un `/login` seco; ahora recuerda la ruta para que
    reautenticarse no deje a nadie varado en el panel de Admin cuando
    trabajaba en otra pantalla (por ejemplo, `/route`).
    """
    response = await alpha_client.get(path)
    assert response.status_code == 303
    assert response.headers["location"] == f"/login?next={quote(path, safe='')}"


@pytest.mark.parametrize(
    "path",
    [
        "/admin/security/roles/list",
        "/admin/security/permissions/list",
        "/admin/security/role-permission-requests/list",
    ],
)
async def test_admin_pages_deny_users_without_the_capability(seeded, alpha_client, path):
    """Antes servían el HTML a cualquier usuario con sesión (AUD-BE-001).

    Escribir la URL a mano tiene que dar 403, no una pantalla a medio pintar.
    """
    await alpha_client.login(seeded.alpha.users["viewer"].email)

    response = await alpha_client.get(path)
    assert response.status_code == 403


async def test_company_list_page_is_platform_only(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["owner"].email)
    assert (await alpha_client.get("/admin/companies/list")).status_code == 403

    await alpha_client.login(seeded.platform_admin.email)
    assert (await alpha_client.get("/admin/companies/list")).status_code == 200


async def test_pages_the_viewer_can_open(seeded, alpha_client):
    await alpha_client.login(seeded.alpha.users["viewer"].email)

    assert (await alpha_client.get("/admin/companies/profile")).status_code == 200
    assert (await alpha_client.get("/admin/locations/states")).status_code == 200
    assert (await alpha_client.get("/admin/security/users/list")).status_code == 200
