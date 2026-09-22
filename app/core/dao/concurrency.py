"""
Comprobación de versión para las escrituras concurrentes.

El cliente que lee una ficha recibe su `version`. Al guardar la devuelve; si
entre la lectura y la escritura otro la cambió, el número ya no coincide y aquí
se corta con 409. La alternativa —el último que guarda gana— pierde trabajo sin
avisar a nadie.

La respuesta 409 lleva la versión actual para que la interfaz pueda recargar y
enseñar qué cambió, en vez de limitarse a decir "vuelve a intentarlo".
"""

from __future__ import annotations

from fastapi import HTTPException, status


class VersionConflict(HTTPException):
    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This record was modified by someone else. Reload it and apply "
                "your changes again."
            ),
            headers={"X-Current-Version": str(current_version)},
        )
        self.current_version = current_version


def ensure_version(*, current: int, expected: int | None) -> None:
    """Corta con 409 si la versión enviada no es la que hay guardada.

    `expected=None` significa que quien llama no participa en el control de
    concurrencia (una migración, un proceso interno). Se acepta a propósito:
    obligar a todo el mundo a leer antes de escribir convertiría cualquier tarea
    de mantenimiento en dos consultas.
    """
    if expected is None:
        return
    if expected != current:
        raise VersionConflict(current_version=current)
