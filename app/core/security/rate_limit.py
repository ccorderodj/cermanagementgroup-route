"""
Limitador de tasa en memoria: primera línea de defensa para escritura pública.

Simplificación deliberada, documentada. Vive en el proceso, no en Redis ni en
la base de datos. Con un único proceso `uvicorn` —el despliegue actual— eso
basta para frenar el abuso automatizado más obvio sin exigir infraestructura
que nadie ha configurado todavía: el mismo principio de "un valor de trabajo
en vez de un bloqueo" que el resto de la plataforma sigue para lo que aún no
está configurado (ver `app/core/email/backends.py`, `app/core/storage/`).

Si la aplicación llega a correr con varios workers o varias instancias, cada
uno cuenta por su cuenta y esto deja de ser una defensa real — hay que
moverlo a un almacén compartido (Redis ya es dependencia del proyecto). Se
anota aquí para que ese límite no se dé por resuelto sin querer.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock


class InMemoryRateLimiter:
    """Ventana deslizante por clave. Sin persistencia: un reinicio la vacía."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def allow(self, key: str, *, limit: int, window_seconds: float) -> bool:
        """`True` si esta llamada cabe en el límite; ya queda contada si cabe."""
        ahora = time.monotonic()
        corte = ahora - window_seconds
        with self._lock:
            ventana = self._hits[key]
            while ventana and ventana[0] < corte:
                ventana.pop(0)
            if len(ventana) >= limit:
                return False
            ventana.append(ahora)
            return True

    def reset(self) -> None:
        """Vacía todo el estado. Para tests: el límite es un singleton del
        proceso, y sin esto una suite entera compartiría cupo entre casos."""
        with self._lock:
            self._hits.clear()


#: Instancia única del proceso, compartida por todo lo que necesite frenar
#: escritura pública. Cada consumidor prefija sus propias claves (p. ej.
#: `f"public-form:{ip}"`) para no compartir cupo con otro limitador.
public_write_limiter = InMemoryRateLimiter()
