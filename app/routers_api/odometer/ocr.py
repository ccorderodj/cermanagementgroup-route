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

Qué adaptador hay enchufado
----------------------------
Desde RTE10-A01 hay uno productivo: `ocr_tesseract.TesseractReader`. Se
registra al arrancar **sólo si el binario de Tesseract existe** en la imagen
(ver `app/main.py`); si no, se queda este `NoSuggestionReader` y el despliegue
se comporta exactamente como antes. Las alternativas consideradas y descartadas
—PaddleOCR por tamaño, `tesseract.js` por la memoria del móvil, un servicio
externo por la frontera de privacidad— están razonadas en ese módulo.

PaddleOCR se evaluó antes con mediciones en un entorno aislado: acertó en
odómetro de rodillo mecánico y en texto impreso limpio, y **no detectó nada** en
un display de siete segmentos. Pesa ~760 MB instalado y descarga modelos en el
primer arranque, así que no cabe en el nodo del ambiente de prueba.

La calidad sobre fotografías reales de flota sigue siendo `PENDING VALIDATION`:
es validación de campo de CER y el desarrollo no la puede declarar.

Nadie llama a `suggest()` directamente
---------------------------------------
El dominio usa `suggest_safely()`. La diferencia importa: un OCR que falla o se
cuelga no puede costarle al supervisor la foto que ya hizo, y `suggest()` en el
camino crítico lo hacía posible. El detalle está en esa función.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)


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


#: Margen sobre el tiempo límite que el propio adaptador aplica.
#:
#: El adaptador mata su proceso cuando se le pasa el plazo; esta espera es la
#: red de debajo, para el caso en que no lo haga —una biblioteca en proceso que
#: se queda girando, por ejemplo—. Sin ella, `asyncio.to_thread` esperaría para
#: siempre y la foto no acabaría de subirse nunca.
TIMEOUT_DEL_PUERTO_SEGUNDOS = 15.0


async def suggest_safely(*, image: bytes, content_type: str) -> Decimal | None:
    """Pide una sugerencia, y **devuelve `None` ante cualquier problema**.

    Por qué esta función existe
    ---------------------------
    El dominio llamaba a `suggest()` directamente, y eso ponía al OCR en el
    camino crítico de la foto: con el proveedor por defecto no pasaba nada
    —`NoSuggestionReader` no puede fallar— pero con un adaptador real una
    excepción o un cuelgue dejaba la foto ya guardada en el almacén y la fila de
    evidencia **sin** su `storage_key`. El supervisor perdía la foto y quedaba
    bloqueado por un fallo del asistente.

    PR-02 de RTE10-A01 lo prohíbe en una línea: que el OCR no dé resultado no
    puede bloquear la operación. Aquí se cumple de la única forma que se sostiene
    —la ausencia de sugerencia y el fallo del OCR producen **el mismo** efecto
    visible— y por eso no se propaga nada: no hay un error de OCR que el
    supervisor pueda arreglar, y mostrárselo sólo le empujaría a pedir una
    excepción que no necesita.

    Fuera del bucle de eventos
    --------------------------
    `suggest()` es síncrono y puede tardar segundos. Llamado directamente
    bloquearía el worker entero —todas las demás peticiones, no sólo esta—, así
    que va a un hilo. Es también lo que permite que el plazo se cumpla.
    """
    lector = get_odometer_reader()
    proveedor = type(lector).__name__

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(lector.suggest, image=image, content_type=content_type),
            timeout=TIMEOUT_DEL_PUERTO_SEGUNDOS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "ODOMETER OCR | %s no contestó en %ss; se sigue sin sugerencia",
            proveedor,
            TIMEOUT_DEL_PUERTO_SEGUNDOS,
        )
        return None
    except Exception:
        # Deliberadamente todo: la lista de excepciones de un OCR depende del
        # proveedor, y una que se escape aquí le cuesta al supervisor la foto
        # que ya hizo. Se registra con traza para que el fallo sea investigable
        # sin ser visible para quien está en la calle.
        logger.exception(
            "ODOMETER OCR | %s falló; se sigue sin sugerencia", proveedor
        )
        return None
