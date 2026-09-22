"""
Sesión de base de datos y unidad de trabajo.

El problema que resuelve
------------------------
Cada método de DAO abría su propia sesión y hacía su propio `commit`. Una
operación que tocaba varias tablas —crear un usuario y vincularlo a una
compañía, actualizar sus datos y luego su rol— no era atómica: si el segundo
paso fallaba, el primero ya estaba confirmado.

La solución que NO se ha tomado
-------------------------------
Reescribir los ocho DAO para que reciban una sesión por parámetro. Habría
tocado cada firma del proyecto para arreglar un problema que solo se manifiesta
en tres endpoints.

La solución adoptada
--------------------
Una transacción **ambiental**, guardada en un `ContextVar`:

* Un DAO invocado suelto abre y cierra su sesión como siempre. Nada cambia.
* Un DAO invocado dentro de `async with transaction():` reutiliza la sesión de
  esa transacción, y su `commit()` se degrada a `flush()`. Quien decide cuándo
  se confirma es el bloque exterior, que confirma una sola vez al final o
  deshace todo si algo falla.

Así el router o el servicio puede envolver varias llamadas a DAO en una
operación atómica sin que los DAO tengan que enterarse.

    async with transaction():
        await UserManagementDAO.update_user_by_company(...)
        await UserManagementDAO.assign_role_in_company(...)
    # un solo commit; si la segunda falla, la primera no queda escrita
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker


_ambient_session: ContextVar[AsyncSession | None] = ContextVar(
    "ambient_session",
    default=None,
)


class _AmbientSession:
    """Vista de la sesión en curso cuyo ciclo de vida NO controla el DAO.

    Delega todo en la sesión real salvo `commit` y `rollback`: dentro de una
    transacción, esas dos decisiones pertenecen al bloque que la abrió.
    """

    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def commit(self) -> None:
        # Se propagan los cambios para que las lecturas posteriores dentro de la
        # misma transacción los vean, pero no se confirma nada todavía.
        await self._session.flush()

    async def rollback(self) -> None:
        # El DAO relanza la excepción tras llamar aquí; deshacer es cosa del
        # bloque `transaction()`, que lo hará con el alcance correcto.
        return None


@asynccontextmanager
async def db_session() -> AsyncIterator[Any]:
    """Sesión para una operación de DAO.

    Devuelve la sesión de la transacción ambiental si la hay; si no, abre una
    nueva y la cierra al salir.
    """
    ambient = _ambient_session.get()
    if ambient is not None:
        yield _AmbientSession(ambient)
        return

    async with async_session_maker() as session:
        yield session


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """Agrupa varias operaciones de DAO en una sola transacción.

    Confirma una vez al salir sin error; deshace todo si algo se lanza.
    Anidar es seguro: el bloque interior se apunta a la transacción exterior y
    no confirma por su cuenta.
    """
    existing = _ambient_session.get()
    if existing is not None:
        yield existing
        return

    async with async_session_maker() as session:
        token = _ambient_session.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _ambient_session.reset(token)


def in_transaction() -> bool:
    """Si el código actual corre dentro de una transacción ambiental."""
    return _ambient_session.get() is not None
