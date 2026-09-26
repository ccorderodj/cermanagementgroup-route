"""
Qué autoridad tiene de verdad un Route Admin sobre los roles (diagnóstico 006, §5).

Por qué este archivo existe
---------------------------
El diagnóstico pide comprobar **contra la API** si quien sólo tiene los permisos
de `route_admin` puede asignar roles del núcleo más poderosos que el suyo, y
advierte de algo importante: las protecciones que ya existen —no aceptar
`is_superuser`, no poder crear ni editar roles, rechazar un rol de otro tenant—
**no demuestran por sí solas** que no pueda conceder un rol que ya existe.

No lo demuestran. Y el resultado es que sí puede.

Lo que sí está bien cerrado
---------------------------
Se comprueba también el otro lado, porque un diagnóstico que sólo enseñe lo roto
da una idea falsa de dónde está el problema: el supervisor no administra nada, el
rol de otro tenant se rechaza, y `is_superuser` no entra por el cuerpo.

Sobre los `xfail`
-----------------
Los cuatro casos de escalada se marcan `xfail(strict=True)`. Es deliberado y no
es un adorno:

* dicen en el propio código lo que **debería** ocurrir, no lo que ocurre;
* mantienen la suite en verde, porque el hueco está reportado y su arreglo es
  una decisión de CER, no una omisión de ingeniería;
* con `strict=True`, el día que alguien lo arregle **este test falla** y obliga a
  quitar la marca. Un `xfail` que se queda en verde para siempre sería una forma
  elegante de olvidar el problema.
"""

from __future__ import annotations

import pytest

from app.routers_api.users.permissions import get_user_permissions
from tests.integration.conftest import TEST_PASSWORD, TenantClient


pytestmark = pytest.mark.integration


#: La razón que llevan los cuatro `xfail`, para que quien la lea sepa a qué
#: espera el arreglo.
PENDIENTE_DE_CER = (
    "SECURITY GAP reportado en CER_ROUTE_RTE02_A01_VALUES_AND_ROLES_DIAGNOSTIC_001: "
    "un route_admin puede conceder un rol del núcleo más poderoso que el suyo. "
    "El arreglo cambia el contrato de administración de usuarios compartido, así "
    "que espera decisión de CER (§11 del diagnóstico 006)."
)


async def _crear_usuario_con_rol(cliente, *, sufijo: str, role_id: int):
    return await cliente.post(
        "/api/users",
        json={
            "username": f"asignado_{sufijo}",
            "email": f"asignado_{sufijo}@alpha.example.com",
            "first_name": "Asignado",
            "last_name": sufijo,
            "password": TEST_PASSWORD,
            "role_id": role_id,
        },
    )


# ── Lo que un Route Admin debería poder asignar, y puede ─────────────────────


@pytest.mark.parametrize("rol", ["route_admin", "supervisor"])
async def test_a_route_admin_can_assign_the_two_route_roles(
    seeded, alpha_client, rol,
):
    """Los dos roles operativos de CER Route son suyos, y eso está bien."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear_usuario_con_rol(
        alpha_client, sufijo=rol, role_id=seeded.alpha.roles[rol]
    )
    assert respuesta.status_code == 200


# ── Lo que no debería poder, y sí puede ──────────────────────────────────────


@pytest.mark.xfail(strict=True, reason=PENDIENTE_DE_CER)
@pytest.mark.parametrize("rol", ["owner", "admin"])
async def test_a_route_admin_cannot_create_a_user_with_a_core_management_role(
    seeded, alpha_client, rol,
):
    """Crear una cuenta `owner` o `admin` desde el formulario de Route.

    Hoy devuelve 200. La cuenta resultante tiene capacidades que el propio Route
    Admin no tiene, así que la concesión es una escalada por persona interpuesta.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear_usuario_con_rol(
        alpha_client, sufijo=rol, role_id=seeded.alpha.roles[rol]
    )
    assert respuesta.status_code == 403, (
        f"un route_admin no debería poder conceder '{rol}'"
    )


@pytest.mark.xfail(strict=True, reason=PENDIENTE_DE_CER)
@pytest.mark.parametrize("rol", ["owner", "admin"])
async def test_a_route_admin_cannot_promote_a_supervisor_to_a_core_role(
    seeded, alpha_client, rol,
):
    """Y tampoco ascender a alguien que ya existe."""
    supervisor = seeded.alpha.users["supervisor"]
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    respuesta = await alpha_client.put(
        f"/api/users/{supervisor.id}",
        json={"role_id": seeded.alpha.roles[rol]},
    )
    assert respuesta.status_code == 403, (
        f"un route_admin no debería poder ascender a '{rol}'"
    )


@pytest.mark.xfail(strict=True, reason=PENDIENTE_DE_CER)
async def test_the_granted_account_cannot_exceed_the_granters_authority(
    seeded, alpha_client,
):
    """La consecuencia completa, que es lo que convierte esto en escalada.

    No es que el rol quede "mal asignado": es que la cuenta nueva **se puede
    usar**. El Route Admin fija su contraseña, entra con ella, y hace cosas que
    su propio rol le niega — borrar un rol, entre otras, que el catálogo le
    retira incluso al `admin` porque es la forma más rápida de dejar una
    compañía sin quien la administre.
    """
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    concedente = await get_user_permissions(
        user_id=seeded.alpha.users["route_admin"].id, company_id=seeded.alpha.id
    )
    assert "roles.delete" not in concedente, "el route_admin no puede borrar roles"

    creado = await _crear_usuario_con_rol(
        alpha_client, sufijo="escalada", role_id=seeded.alpha.roles["owner"]
    )
    assert creado.status_code == 403, (
        "la cuenta no debería haberse podido crear con ese rol"
    )


# ── Lo que sí está bien cerrado ──────────────────────────────────────────────


async def test_a_supervisor_administers_nothing(seeded, alpha_client):
    """El rol de campo tiene exactamente una capacidad, y no es administrar."""
    supervisor = seeded.alpha.users["supervisor"]
    concedidas = await get_user_permissions(
        user_id=supervisor.id, company_id=seeded.alpha.id
    )
    assert concedidas == {"route.worksession.execute"}

    await alpha_client.login(supervisor.email)
    assert (await alpha_client.get("/api/users/pagination")).status_code == 403
    assert (await alpha_client.get("/api/roles")).status_code == 403
    creacion = await _crear_usuario_con_rol(
        alpha_client, sufijo="porsup", role_id=seeded.alpha.roles["supervisor"]
    )
    assert creacion.status_code == 403


async def test_a_role_from_another_tenant_is_rejected(seeded, alpha_client):
    """404, no 403: no se confirma que el rol del otro tenant exista."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await _crear_usuario_con_rol(
        alpha_client, sufijo="cruzado", role_id=seeded.beta.roles["owner"]
    )
    assert respuesta.status_code == 404


async def test_is_superuser_is_not_accepted_from_the_request_body(
    seeded, alpha_client,
):
    """Privilegio de plataforma: no está en ningún schema de entrada del tenant."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)
    respuesta = await alpha_client.post(
        "/api/users",
        json={
            "username": "intento_su",
            "email": "intento_su@alpha.example.com",
            "first_name": "I", "last_name": "S",
            "password": TEST_PASSWORD,
            "role_id": seeded.alpha.roles["supervisor"],
            "is_superuser": True,
        },
    )
    assert respuesta.status_code == 422
    assert "extra_forbidden" in respuesta.text


async def test_a_route_admin_cannot_create_or_edit_roles(seeded, alpha_client):
    """No puede fabricarse un rol a medida: sólo asignar los que ya hay."""
    await alpha_client.login(seeded.alpha.users["route_admin"].email)

    creacion = await alpha_client.post(
        "/api/roles", json={"name": "inventado", "description": "x", "category": "management"}
    )
    assert creacion.status_code == 403

    borrado = await alpha_client.delete(f"/api/roles/{seeded.alpha.roles['viewer']}")
    assert borrado.status_code == 403


# ── El modelo de roles, tal como CER lo definió ──────────────────────────────


def test_exactly_two_role_templates_are_specific_to_cer_route():
    """`route_admin` y `supervisor`. Los otros cuatro son del núcleo.

    Se comprueba por la capacidad, no por el nombre: un rol es de Route si
    concede algo de Route. `owner` y `admin` reciben capacidades de Route por ser
    "todo" y "casi todo", que es otra cosa y el diagnóstico pide distinguirla.
    """
    from app.core.rbac.catalog import DEFAULT_ROLES, capabilities_for

    DE_ROUTE = {"route_admin", "supervisor"}
    DEL_NUCLEO = {"owner", "admin", "manager", "viewer"}

    plantillas = {p.name for p in DEFAULT_ROLES}
    assert plantillas == DE_ROUTE | DEL_NUCLEO, "seis roles por defecto, ni más ni menos"

    for plantilla in DEFAULT_ROLES:
        capacidades = capabilities_for(plantilla)
        de_route = [c for c in capacidades if c.startswith("route.")]
        if plantilla.name in DE_ROUTE:
            assert de_route, f"'{plantilla.name}' es de Route y no concede nada de Route"
        elif plantilla.name in ("manager", "viewer"):
            assert not de_route, (
                f"'{plantilla.name}' es del núcleo y no debería conceder nada de Route"
            )


def test_the_supervisor_template_grants_no_administration():
    """El rol de campo no administra: ni usuarios, ni roles, ni configuración."""
    from app.core.rbac.catalog import DEFAULT_ROLES, capabilities_for

    supervisor = next(p for p in DEFAULT_ROLES if p.name == "supervisor")
    capacidades = set(capabilities_for(supervisor))

    prohibidas = {
        c for c in capacidades
        if c.startswith(("users.", "roles.", "rolepermissions", "permissions."))
        or c.endswith(".manage")
    }
    assert prohibidas == set(), f"el supervisor no debería administrar: {prohibidas}"
