"""
Autorización de las páginas administrativas.

Antes ninguna ruta de página comprobaba permisos: bastaba con tener sesión para
recibir el HTML de cualquier pantalla de seguridad (AUD-BE-001). No se filtraban
datos —la API sí estaba protegida— pero un usuario sin permisos aterrizaba en una
pantalla rota en lugar de en un "no tienes acceso", y cada pantalla nueva iba a
heredar el mismo hueco.

Esto es **la mitad backend** del control. La otra mitad es que el sidebar no
muestre lo que no se puede abrir, y vive en `AppSidebar.tsx`. El orden importa:
el frontend es experiencia de usuario, el backend es la seguridad. Nunca al revés.

Los permisos no se vuelven a consultar: `LoggedinMiddleware` ya los dejó
resueltos en `request.state` al construir la cookie `user_data`.
"""

from collections.abc import Callable

from fastapi import HTTPException, Request, status


def require_page_permissions(required: list[str]) -> Callable:
    async def _dependency(request: Request) -> None:
        user = getattr(request.state, "user", None)

        if user is None:
            # `AuthMiddleware` redirige antes de llegar aquí; esto es una red
            # por si alguien registra una página fuera de esa aplicación.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        if user.is_superuser:
            return

        granted = getattr(request.state, "permissions", set()) or set()
        missing = set(required) - granted

        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this section.",
            )

    return _dependency


def require_platform_admin_page() -> Callable:
    """Pantallas de administración de plataforma (D6)."""

    async def _dependency(request: Request) -> None:
        user = getattr(request.state, "user", None)
        if user is None or not user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This section is restricted to platform administrators.",
            )

    return _dependency
