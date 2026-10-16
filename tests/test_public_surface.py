"""
La superficie pública de la API es una lista blanca cerrada.

Por qué existe este test
------------------------
El router público incluía los routers **enteros** de `users` y `regions`, así
que publicaba sin autenticación `register`, `change-password`, el perfil y tres
endpoints que devolvían datos del tenant a cualquiera que conociera el
subdominio (AUD-SEC-002).

Lo peligroso no era la lista de endpoints publicados: era que **crecía sola**.
Cualquier endpoint añadido a esos módulos quedaba publicado sin que nadie lo
decidiera ni lo revisara.

Este test convierte esa lista en algo explícito. Añadir un endpoint público pasa
a exigir editar `EXPECTED_PUBLIC_ENDPOINTS`, que es justo el momento en que
alguien tiene que justificarlo.

No necesita base de datos: es introspección de las rutas registradas.
"""

from __future__ import annotations

import pytest


# Los ÚNICOS endpoints que pueden servirse sin sesión.
# Cambiar esta lista es una decisión de seguridad, no de implementación.
EXPECTED_PUBLIC_ENDPOINTS: set[tuple[str, str]] = {
    ("POST", "/public/auth/login"),
    ("POST", "/public/auth/logout"),
    ("POST", "/public/auth/password-reset"),
    ("POST", "/public/auth/password-reset/confirm"),
}

#: La API versionada entre aplicaciones (`/api/v1`). Tampoco lleva sesión de
#: usuario: cada endpoint trae su propia autenticación —la firma HMAC del
#: webhook— o no expone datos del tenant (`/meta`). Crecer aquí es la misma
#: decisión de seguridad que crecer en `EXPECTED_PUBLIC_ENDPOINTS`.
EXPECTED_VERSIONED_ENDPOINTS: set[tuple[str, str]] = {
    ("GET", "/v1/meta"),
    ("POST", "/v1/webhooks/inbound/{public_id}"),
}


def _api_routes() -> list[tuple[str, str, str]]:
    """`(método, path, nombre)` de cada ruta registrada bajo /api."""
    from app.main import api

    routes: list[tuple[str, str, str]] = []

    def walk(collected, prefix: str = "") -> None:
        for route in collected:
            if type(route).__name__ == "_IncludedRouter":
                context = route.include_context
                walk(
                    route.original_router.routes,
                    prefix + (getattr(context, "prefix", "") or ""),
                )
                continue

            path = prefix + (getattr(route, "path", "") or "")
            for method in sorted(getattr(route, "methods", None) or []):
                routes.append((method, path, getattr(route, "name", "")))

    walk(api.routes)
    return routes


def public_endpoints() -> set[tuple[str, str]]:
    return {
        (method, path)
        for method, path, _ in _api_routes()
        if path.startswith("/public")
    }


def test_public_surface_matches_the_whitelist():
    actual = public_endpoints()

    unexpected = sorted(actual - EXPECTED_PUBLIC_ENDPOINTS)
    assert not unexpected, (
        "Estos endpoints se sirven SIN autenticación y no están en la lista "
        "blanca. Si es intencionado, hay que añadirlos a "
        f"EXPECTED_PUBLIC_ENDPOINTS y justificarlo:\n{unexpected}"
    )

    missing = sorted(EXPECTED_PUBLIC_ENDPOINTS - actual)
    assert not missing, (
        "Estos endpoints deberían ser públicos y no están registrados. "
        f"El login dejaría de funcionar:\n{missing}"
    )


def test_versioned_integration_surface_matches_the_whitelist():
    actual = {(m, p) for m, p, _ in _api_routes() if p.startswith("/v1/")}
    assert actual == EXPECTED_VERSIONED_ENDPOINTS


def test_every_other_endpoint_requires_a_session():
    """Fuera de `/public` y `/v1`, todo cuelga del router privado con sesión."""
    from app.routers_api.api import api_router
    from app.routers_api.users.dependencies import get_current_user

    assert get_current_user in {d.dependency for d in api_router.dependencies}
    documentacion = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    privados = {p for _, p, _ in _api_routes()} - documentacion
    sueltos = sorted(
        p for p in privados
        if not p.startswith(("/public/", "/v1/")) and p not in _private_router_paths()
    )
    assert not sueltos, f"Endpoints fuera del router privado y sin whitelist: {sueltos}"


def _private_router_paths() -> set[str]:
    from app.routers_api.api import api_router

    paths: set[str] = set()

    def walk(collected, prefix: str = "") -> None:
        for route in collected:
            if type(route).__name__ == "_IncludedRouter":
                walk(route.original_router.routes, prefix + (getattr(route.include_context, "prefix", "") or ""))
                continue
            paths.add(prefix + (getattr(route, "path", "") or ""))

    walk(api_router.routes)
    return paths


def test_no_registration_endpoint_exists():
    """No hay auto-registro (D2).

    El endpoint existía, era público y fallaba por un error de columna, no por
    un control de acceso: arreglar el nombre de la columna —un cambio de
    apariencia inocente— habría abierto la creación anónima de cuentas
    (AUD-SEC-003).
    """
    paths = {path for _, path, _ in _api_routes()}
    registration = sorted(p for p in paths if "register" in p or "signup" in p)

    assert not registration, (
        "Hay endpoints de registro publicados. Las altas las hace "
        f"administración desde POST /users, con el permiso users.create: {registration}"
    )


def test_regions_is_not_exposed_publicly():
    """Los datos del tenant no salen sin sesión.

    Verificado antes de la remediación: `GET /api/public/regions/operating`
    devolvía 200 con los estados de operación y la sede principal de la
    compañía.
    """
    leaked = sorted(
        path for _, path in public_endpoints()
        if "region" in path or "compan" in path or "role" in path or "user" in path
    )
    # `/public/auth/*` contiene "auth", no datos de negocio.
    leaked = [p for p in leaked if not p.startswith("/public/auth/")]

    assert not leaked, (
        f"Estos endpoints exponen datos del tenant sin autenticación: {leaked}"
    )


@pytest.mark.parametrize(
    "path",
    ["/auth/profile", "/companies", "/companies/profile", "/regions", "/roles", "/users/pagination"],
)
def test_private_endpoints_are_registered_outside_public(path: str):
    """Los endpoints privados existen y NO tienen gemelo bajo /public."""
    paths = {route_path for _, route_path, _ in _api_routes()}

    assert path in paths, f"{path} debería estar registrado en la API privada."
    assert f"/public{path}" not in paths, (
        f"{path} tiene un duplicado público. Ese era exactamente el patrón que "
        "publicaba routers enteros sin autenticación."
    )


# ── Paginas servibles sin sesion interna ────────────────────────────────────

#: Las UNICAS paginas que el middleware sirve sin cookie de sesion.
#: Igual que la lista de endpoints, crecer aqui es una decision de seguridad y
#: por eso exige editar esta lista, que es el momento en que alguien tiene que
#: justificarlo.
EXPECTED_PUBLIC_PAGES: set[str] = {
    "/login",
    "/password-reset",
    "/change-password",
}


def test_public_pages_match_the_whitelist():
    from app.core.middleware.auth_middleware import AuthMiddleware

    assert set(AuthMiddleware.PUBLIC_PATHS) == EXPECTED_PUBLIC_PAGES


#: Como `EXPECTED_PUBLIC_PAGES`, pero para prefijos (páginas anónimas con un
#: identificador en el path). La base no publica ninguna.
EXPECTED_PUBLIC_PAGE_PREFIXES: tuple[str, ...] = ()


def test_public_page_prefixes_match_the_whitelist():
    from app.core.middleware.auth_middleware import AuthMiddleware

    assert AuthMiddleware.PUBLIC_PATH_PREFIXES == EXPECTED_PUBLIC_PAGE_PREFIXES


def test_the_root_path_is_not_public():
    """`/` no sirve nada sin sesión: lleva al login, y con sesión a la página por defecto."""
    from app.core.middleware.auth_middleware import AuthMiddleware

    assert "/" not in AuthMiddleware.PUBLIC_PATHS
    assert "/" in AuthMiddleware.AUTHENTICATED_REDIRECT_PATHS
