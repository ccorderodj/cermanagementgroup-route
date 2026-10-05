"""
El adaptador de OCR que sí sugiere: Tesseract, dentro de la infraestructura.

Por qué Tesseract y no otro
----------------------------
`ocr.py` define el puerto y deja la elección al desarrollo (RTE10-A01 §11). Las
cuatro opciones consideradas, y por qué esta:

* **Tesseract, en el servidor** — la elegida. La foto no sale de la
  infraestructura de CER, no hay coste por llamada, no hay contrato con nadie y
  la licencia es Apache 2.0. Cuesta una dependencia de sistema en la imagen
  (~15 MB de binario y ~15 MB de datos de idioma).
* **PaddleOCR** — medido en el preflight: acertó en rodillo mecánico, **no
  detectó nada** en display de siete segmentos, pesa ~760 MB instalado y
  descarga modelos en el primer arranque. No cabe en el nodo del ambiente de
  prueba.
* **`tesseract.js` en el navegador** — descarta §9 por sí sola: añadir ~12 MB
  de WASM y datos de idioma, y ejecutar el reconocimiento en el renderer, es
  justo lo contrario de reducir la presión de memoria en un teléfono al que
  Android ya está matando la página.
* **Un servicio externo** (Vision, Textract) — mejor precisión, incluida la de
  los salpicaderos digitales, pero la foto **sale** de CER, aparece un coste por
  llamada y una clave que gestionar. §5 y §10 lo condicionan a una decisión de
  CER, y como el camino manual ya cumple el requisito, no se adopta sin ella.
  Queda anotado como la vía si CER quiere precisión en display digital.

El límite conocido, dicho por delante
--------------------------------------
Tesseract está entrenado sobre texto, no sobre displays de siete segmentos. En
odómetro de rodillo mecánico y en salpicadero con dígitos tipográficos funciona;
en un display LCD de segmentos es **probable** que no sugiera nada. Eso no es
una avería: es el camino manual de PR-02, que sigue siendo evidencia
fotográfica normal.

Ser conservador es parte del diseño
------------------------------------
Ante dos candidatos plausibles en la misma foto —el odómetro y el cuentaparcial,
que es exactamente lo que tiene un salpicadero— **no se sugiere nada**. Una
sugerencia equivocada que el supervisor acepta sin mirar es peor que ninguna
sugerencia: la primera entra como evidencia confirmada por una persona, y la
segunda sólo le hace teclear.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

#: El binario mira una sola línea de texto (`--psm 7`) y sólo puede devolver
#: dígitos y el punto de las décimas. La lista blanca es lo que más sube el
#: acierto en un odómetro: sin ella, un `0` se confunde con `O` y un `1` con `l`.
_PSM_LINEA_UNICA = "7"
_CARACTERES = "0123456789."

#: Lado mayor al que se reduce la foto antes de reconocer. Una foto de teléfono
#: viene a 4000 px y Tesseract no gana nada con eso: tarda más y come memoria
#: que el nodo del ambiente de prueba no tiene de sobra.
MAX_DIMENSION = 1600

#: Confianza mínima por token, en la escala 0-100 que devuelve Tesseract.
#: Por debajo, el token se descarta: es ruido de reflejo o de poca luz.
MIN_CONFIANZA = 60.0

#: Una lectura de odómetro tiene al menos dos dígitos. Un dígito suelto en una
#: foto de salpicadero es casi siempre un trozo de otro indicador.
MIN_DIGITOS = 2

#: El mismo techo que el contrato de entrada (`OdometerReadingConfirm`) y la
#: restricción de la base. **No se inventa un rango de negocio nuevo**: §8 lo
#: prohíbe de forma explícita.
MAX_LECTURA = Decimal("99999999.9")

#: Un número con dígitos y, como mucho, una parte decimal de un dígito: es lo
#: que cabe en `Numeric(10, 1)`.
_CANDIDATO = re.compile(r"^\d{1,8}(?:\.\d)?$")


class TesseractUnavailable(RuntimeError):
    """El binario no está instalado, o no contestó."""


def tesseract_disponible(binario: str = "tesseract") -> bool:
    """Si hay un binario que invocar.

    Se consulta al arrancar para decidir qué lector se registra. Un despliegue
    sin el paquete de sistema se queda con `NoSuggestionReader` y **se comporta
    exactamente como antes**, que es lo que mantiene verde la línea base
    certificada.
    """
    return shutil.which(binario) is not None


def _preprocesar(image: bytes) -> bytes:
    """Deja la foto como Tesseract la lee mejor: derecha, gris y contrastada.

    La orientación importa más de lo que parece: un teléfono guarda la foto
    girada con una etiqueta EXIF, y Tesseract no mira la etiqueta. Una foto de
    costado no produce una lectura mala — no produce ninguna.

    Reutiliza `normalize_image`, que ya aplica la orientación, limita el lado
    mayor y quita el EXIF. Escribir aquí un segundo abridor de imágenes sería
    duplicar código con límites de bomba de descompresión propios.
    """
    import io

    from PIL import Image, ImageOps

    from app.core.storage.media import normalize_image

    normalizada = normalize_image(
        image, max_dimension=MAX_DIMENSION, jpeg_quality=90
    )

    imagen = Image.open(io.BytesIO(normalizada.data))
    imagen.load()
    # Gris y contraste automático: es lo que rescata las fotos con poca luz y
    # las que tienen el reflejo en una esquina. No se binariza con un umbral
    # fijo a propósito —un umbral que va bien a mediodía deja en negro la foto
    # de un parking cubierto.
    gris = ImageOps.autocontrast(imagen.convert("L"))

    salida = io.BytesIO()
    gris.save(salida, format="PNG", optimize=False)
    return salida.getvalue()


def _candidatos(tsv: str) -> list[str]:
    """Los tokens que superan la confianza mínima y parecen una lectura.

    Tesseract devuelve TSV con una fila por palabra; `conf` es la confianza y
    `text` el token. Las filas de estructura —página, bloque, línea— traen
    `conf = -1` y no tienen texto, así que caen solas.
    """
    encontrados: list[str] = []

    for linea in tsv.splitlines()[1:]:
        columnas = linea.split("\t")
        if len(columnas) < 12:
            continue
        try:
            confianza = float(columnas[10])
        except ValueError:
            continue
        if confianza < MIN_CONFIANZA:
            continue

        token = columnas[11].strip().strip(".")
        if not _CANDIDATO.match(token):
            continue
        if len(token.replace(".", "")) < MIN_DIGITOS:
            continue
        encontrados.append(token)

    return encontrados


def _a_lectura(candidatos: list[str]) -> Decimal | None:
    """Un solo candidato plausible es una sugerencia; dos son una ambigüedad.

    El salpicadero de un vehículo tiene el odómetro total **y** el parcial, y
    casi siempre los dos están en la foto. Elegir uno de los dos por tamaño o
    por posición sería adivinar, y la sugerencia equivocada tiene mucho más
    coste que la sugerencia ausente: ésta hace teclear, y aquélla puede entrar
    como kilometraje confirmado si alguien la acepta sin mirar.
    """
    if len(candidatos) != 1:
        if len(candidatos) > 1:
            logger.info(
                "ODOMETER OCR | %d candidatos plausibles: ambiguo, sin sugerencia",
                len(candidatos),
            )
        return None

    try:
        lectura = Decimal(candidatos[0])
    except InvalidOperation:
        return None

    if lectura < 0 or lectura > MAX_LECTURA:
        return None

    # La columna es `Numeric(10, 1)`: se fija la escala aquí para que lo que se
    # guarda sea exactamente lo que se sugirió.
    return lectura.quantize(Decimal("0.1"))


class TesseractReader:
    """El puerto de `ocr.py`, implementado sobre el binario de Tesseract.

    Invoca el proceso con la foto por `stdin` y lee el TSV por `stdout`: la
    imagen **no se escribe en disco** en ningún momento. Un archivo temporal con
    el salpicadero y la matrícula del vehículo sería evidencia fuera del almacén
    privado, sin dueño y sin borrado garantizado.

    El tiempo límite lo aplica el propio `subprocess`, así que un Tesseract
    colgado se **mata**; no basta con dejar de esperarlo desde fuera, porque el
    proceso seguiría ocupando el nodo.
    """

    name = "tesseract"

    def __init__(
        self,
        *,
        binary: str = "tesseract",
        timeout_seconds: float = 8.0,
        language: str = "eng",
    ) -> None:
        self.binary = binary
        self.timeout = timeout_seconds
        self.language = language

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        preparada = _preprocesar(image)

        orden = [
            self.binary,
            "stdin",
            "stdout",
            "-l", self.language,
            "--psm", _PSM_LINEA_UNICA,
            "-c", f"tessedit_char_whitelist={_CARACTERES}",
            "tsv",
        ]

        try:
            resultado = subprocess.run(
                orden,
                input=preparada,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise TesseractUnavailable(f"{self.binary} is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise TesseractUnavailable(
                f"{self.binary} did not finish in {self.timeout}s"
            ) from exc

        if resultado.returncode != 0:
            detalle = resultado.stderr.decode("utf-8", "replace").strip()[:200]
            raise TesseractUnavailable(
                f"{self.binary} exited {resultado.returncode}: {detalle}"
            )

        tsv = resultado.stdout.decode("utf-8", "replace")
        return _a_lectura(_candidatos(tsv))
