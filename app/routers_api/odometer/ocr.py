"""
La frontera del OCR. **El dominio no conoce ningún proveedor.**

Por qué es un puerto y no una llamada directa
----------------------------------------------
La instrucción de RTE04 pide evitar acoplar el dominio a un proveedor concreto,
y hay una razón de fondo: el OCR es **asistivo**. Nunca establece por sí solo un
hecho de millaje — sugiere, y una persona confirma. Un dominio que dependiera de
una biblioteca concreta acabaría tratando su salida como autoridad, que es
exactamente lo que no puede pasar.

Que devuelva `None` es un resultado normal
-------------------------------------------
No sugerir nada **no es un error** y no convierte una foto válida en un caso de
excepción. El supervisor teclea lo que ve y confirma: eso sigue siendo evidencia
fotográfica normal, sin aprobación de nadie. Por eso el proveedor por defecto no
sugiere nada y el camino manual funciona igual: el dominio está completo sin OCR.

Sobre PaddleOCR
---------------
Se evaluó con mediciones en un entorno aislado: acertó en odómetro de rodillo
mecánico y en texto impreso limpio, y **no detectó nada** en un display de siete
segmentos. Pesa ~760 MB instalado, descarga modelos en el primer arranque y
necesita `enable_mkldnn=False` para no romper en CPU. CER aceptó dejarlo
**desactivado por defecto**: enchufarlo es escribir un adaptador que cumpla este
protocolo y registrarlo, sin tocar una línea del dominio.

La calidad sobre fotografías reales de flota sigue siendo `PENDING VALIDATION`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class OdometerReader(Protocol):
    """Lo que el dominio le pide a un OCR, y nada más."""

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        """La lectura que cree ver, o `None` si no ve ninguna con confianza.

        Devolver `None` es legítimo y frecuente. Quien llama nunca debe tratar
        la sugerencia como un hecho: es un borrador para que el supervisor
        teclee menos.
        """
        ...


class NoSuggestionReader:
    """El proveedor por defecto: no sugiere nada.

    No es un hueco por rellenar. Es la implementación honesta de "este
    despliegue no tiene OCR": el supervisor lee la foto y teclea, que es el
    camino normal y suficiente. Preferible a una sugerencia que falla justo en
    los salpicaderos digitales y que alguien podría acabar aceptando sin mirar.
    """

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        return None


_lector: OdometerReader = NoSuggestionReader()


def get_odometer_reader() -> OdometerReader:
    return _lector


def set_odometer_reader(lector: OdometerReader) -> None:
    """Enchufa un adaptador. Lo usan el arranque y los tests.

    Los tests lo aprovechan para comprobar las dos ramas que importan: que una
    sugerencia se guarda **separada** de la lectura confirmada, y que su
    ausencia no bloquea la confirmación manual.
    """
    global _lector  # noqa: PLW0603 - un único registro de proveedor por proceso
    _lector = lector
