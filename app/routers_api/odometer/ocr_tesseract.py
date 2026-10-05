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
import os
import re
import shutil
import subprocess
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

#: Texto disperso (`--psm 11`): busca lo que haya, esté donde esté.
#:
#: Antes era `7`, "una sola línea de texto", y era el modo equivocado para esto.
#: Un salpicadero no es una línea: es el odómetro, el cuentaparcial, la
#: velocidad y lo que el fabricante haya querido, repartidos por el encuadre.
#: Medido sobre un tablero con dos grupos numéricos, el contraste es total —
#: con `7` no se reconoce **nada**, con `11` salen los dos al 96% de confianza:
#:
#:     psm=7  -> []
#:     psm=11 -> [('128437', 96.2), ('241.6', 96.6)]
#:
#: El modo `7` funcionaba con una imagen que fuera exactamente una línea de
#: dígitos, que es la forma de las sondas sintéticas de verificación. Por eso
#: pasaban mientras las fotografías de campo no producían ni una sugerencia.
_PSM_TEXTO_DISPERSO = "11"
_CARACTERES = "0123456789."

#: Las escalas a las que se intenta leer, en orden.
#:
#: No hay una resolución buena, y eso se midió antes de decidirlo. Sobre fotos
#: de 4000 px con el odómetro ocupando poco del encuadre:
#:
#:     odómetro al 8%     1600 -> sólo el velocímetro
#:                        2400 -> 128437  (correcto)
#:                        3200 -> 128497  (un 3 leído como 9)
#:     odómetro con desenfoque
#:                        1600 -> sólo el velocímetro
#:                        3200 -> 128437  (correcto)
#:
#: Reducir mucho borra los dígitos pequeños; reducir poco deja ruido que el
#: motor confunde. Por eso se lee a varias y **se exige que dos coincidan**:
#: dos escalas distintas que leen el mismo número es una señal de confianza
#: real, no un umbral inventado, y cuando discrepan la respuesta honesta es que
#: no se sabe. Es lo que convierte `128437` frente a `128497` en "sin
#: sugerencia" en vez de en una lectura equivocada.
#:
#: El orden importa: las dos primeras son las que más aciertan, así que la foto
#: bien encuadrada —el caso normal— se resuelve en dos pasadas y no en tres.
ESCALAS = (2400, 3200, 1600)

#: Coincidencias necesarias para aceptar una lectura.
COINCIDENCIAS_NECESARIAS = 2

#: Confianza mínima por token, en la escala 0-100 que devuelve Tesseract.
#: Por debajo, el token se descarta: es ruido de reflejo o de poca luz.
MIN_CONFIANZA = 60.0

#: Mínimo de dígitos de una lectura de odómetro.
#:
#: Era 2, con el argumento de que un dígito suelto en una foto de salpicadero es
#: casi siempre un trozo de otro indicador. El argumento era bueno y el número
#: era corto: un salpicadero está lleno de números de dos y tres dígitos —la
#: velocidad, la temperatura, la marcha, el nivel— y con el umbral en 2 el
#: velocímetro se colaba como lectura de odómetro en cuanto el odómetro no se
#: leía bien. Medido: una foto donde el odómetro queda ilegible sugería `60`.
#:
#: Cuatro dígitos significan que se descarta un vehículo con menos de 1.000
#: millas. En una flota en operación eso no ocurre, y cuando ocurra el coste es
#: que el supervisor teclea — que es el coste barato. El caro es sugerirle la
#: velocidad como si fuera el kilometraje.
MIN_DIGITOS = 4

#: El mismo techo que el contrato de entrada (`OdometerReadingConfirm`) y la
#: restricción de la base. **No se inventa un rango de negocio nuevo**: §8 lo
#: prohíbe de forma explícita.
MAX_LECTURA = Decimal("99999999.9")

#: Un número con dígitos y, como mucho, una parte decimal de un dígito: es lo
#: que cabe en `Numeric(10, 1)`.
_CANDIDATO = re.compile(r"^\d{1,8}(?:\.\d)?$")

#: La primera columna de la cabecera que emite `tessedit_create_tsv`. Sirve
#: para distinguir una salida TSV de la de texto plano a la que Tesseract cae
#: cuando no encuentra lo que se le pidió.
_CABECERA_TSV = "level	page_num"


class TesseractUnavailable(RuntimeError):
    """El binario no está instalado, o no contestó."""


def tesseract_disponible(binario: str = "tesseract", *, idioma: str = "eng") -> bool:
    """Si hay un Tesseract que **de verdad pueda leer**, no sólo un binario.

    Se consulta al arrancar para decidir qué lector se registra. Un despliegue
    sin el paquete de sistema se queda con `NoSuggestionReader` y se comporta
    exactamente como antes, que es lo que mantiene verde la línea base
    certificada.

    Por qué no basta con `shutil.which`
    ------------------------------------
    Lo era hasta que el piloto enseñó el caso intermedio. Allí el binario estaba
    instalado y en el `PATH` —`which` decía que sí— y aun así no podía hacer
    nada, primero por una biblioteca que faltaba y después porque los datos de
    idioma estaban fuera de donde los busca:

        Error opening data file .../tessdata/eng.traineddata
        Tesseract couldn't load any languages!

    Con la comprobación anterior el arranque registraba el lector y escribía
    "lector activo" en el log mientras **cada foto fallaba**. No era peligroso
    —`suggest_safely` lo convierte en "sin sugerencia" y el supervisor teclea—
    pero el log afirmaba un control que no existía, que es justo lo que este
    repositorio no hace en ninguna otra frontera: el escáner de malware
    distingue "limpio" de "nadie pudo mirarlo" por la misma razón.

    Así que se pregunta lo que de verdad importa: ¿puedes cargar el idioma? Un
    `--list-langs` cuesta milisegundos una vez por proceso y convierte un log
    que miente en uno que se puede creer.
    """
    if shutil.which(binario) is None:
        return False

    try:
        resultado = subprocess.run(
            [binario, "--list-langs"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    if resultado.returncode != 0:
        logger.info(
            "ODOMETER OCR | %s está instalado pero no puede listar idiomas: %s",
            binario,
            resultado.stderr.decode("utf-8", "replace").strip()[:200],
        )
        return False

    # `--list-langs` escribe la cabecera por stderr y los idiomas por stdout en
    # unas versiones, y todo por stderr en otras. Se miran los dos.
    salida = (
        resultado.stdout.decode("utf-8", "replace")
        + resultado.stderr.decode("utf-8", "replace")
    )
    disponibles = {
        linea.strip() for linea in salida.splitlines() if linea.strip()
    }
    if idioma not in disponibles:
        logger.info(
            "ODOMETER OCR | %s no tiene el idioma '%s' (TESSDATA_PREFIX=%s)",
            binario,
            idioma,
            os.environ.get("TESSDATA_PREFIX", "<sin definir>"),
        )
        return False

    return True


def _preprocesar(image: bytes, max_dimension: int = 2400) -> bytes:
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
        image, max_dimension=max_dimension, jpeg_quality=90
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
    """Elige entre los candidatos, o no elige y no sugiere nada.

    El problema real
    ----------------
    Un salpicadero casi nunca enseña un solo número. Lo normal es el odómetro
    **y** el cuentaparcial, y a menudo algo más. La versión anterior devolvía
    `None` ante más de un candidato, lo cual era seguro y resultó ser demasiado:
    medido sobre un tablero corriente, el OCR encontraba `128437` y `241.6` al
    96% de confianza y la pantalla no enseñaba nada. El supervisor tecleaba
    siempre.

    Qué distingue al odómetro, y por qué no es adivinar
    ---------------------------------------------------
    El odómetro **acumula** y el cuentaparcial **se pone a cero**, así que el
    primero tiene más dígitos que el segundo durante casi toda la vida del
    vehículo. No es una heurística de apariencia —ni el tamaño, ni la posición,
    ni "el número más grande"— sino una propiedad de lo que cada uno cuenta.

    Se exige que el ganador tenga **estrictamente** más dígitos que todos los
    demás. Si dos empatan, no hay ganador y no se sugiere nada: un empate
    significa que la foto no distingue, y en ese caso callarse sigue siendo la
    respuesta correcta. Una sugerencia equivocada es peor que ninguna.
    """
    if not candidatos:
        return None

    def digitos(valor: str) -> int:
        return len(valor.replace(".", ""))

    ordenados = sorted(candidatos, key=digitos, reverse=True)
    if len(ordenados) > 1 and digitos(ordenados[0]) == digitos(ordenados[1]):
        logger.info(
            "ODOMETER OCR | %d candidatos empatados en dígitos: ambiguo, "
            "sin sugerencia",
            len(ordenados),
        )
        return None

    try:
        lectura = Decimal(ordenados[0])
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

    def _leer_una_escala(self, image: bytes, max_dimension: int) -> Decimal | None:
        """Una pasada: preparar a esa escala, invocar, interpretar."""
        preparada = _preprocesar(image, max_dimension=max_dimension)

        orden = [
            self.binary,
            "stdin",
            "stdout",
            "-l", self.language,
            "--psm", _PSM_TEXTO_DISPERSO,
            "-c", f"tessedit_char_whitelist={_CARACTERES}",
            # El TSV se pide por **parámetro**, no por el fichero de
            # configuración `tsv`.
            #
            # Son equivalentes cuando ese fichero existe, y la diferencia
            # importa cuando no: Tesseract avisa por stderr —"Can't open
            # tsv"—, **devuelve 0** y cae a texto plano. El texto plano tiene
            # una columna, el parser espera doce, así que no se reconocía
            # ningún candidato y el adaptador devolvía `None` con cualquier
            # fotografía, sin un solo error.
            "-c", "tessedit_create_tsv=1",
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
        if not tsv.startswith(_CABECERA_TSV):
            # Si la salida no es TSV, no hay candidatos que interpretar — y
            # devolver `None` aquí sería indistinguible de "no vi nada". Son
            # cosas distintas: una es la foto, la otra es la instalación, y
            # sólo la segunda se arregla.
            raise TesseractUnavailable(
                f"{self.binary} no devolvió TSV: {tsv.splitlines()[:1]}"
            )
        return _a_lectura(_candidatos(tsv))

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        """Lee a varias escalas y sugiere sólo cuando dos coinciden.

        Por qué no basta una pasada
        ----------------------------
        Medido sobre fotografías de teléfono con el odómetro ocupando poco del
        encuadre, que es lo que manda cualquiera: a 1600 px los dígitos
        pequeños desaparecen y lo único que sobrevive es el velocímetro; a
        3200 px aparece ruido que el motor confunde —un `3` leído como `9`—. No
        hay una resolución que acierte siempre.

        Dos escalas que leen el mismo número es una señal de confianza real, y
        cuando discrepan la respuesta honesta es que no se sabe. Eso convierte
        un `128437` frente a un `128497` en silencio en vez de en una lectura
        equivocada, que es lo que de verdad cuesta: el supervisor puede
        confirmarla sin mirar y entra como kilometraje de una persona.

        Se para en cuanto hay acuerdo, así que la foto bien encuadrada —el caso
        normal— cuesta dos pasadas y no tres.
        """
        lecturas: list[Decimal] = []
        for escala in ESCALAS:
            lectura = self._leer_una_escala(image, escala)
            if lectura is None:
                continue
            lecturas.append(lectura)
            if lecturas.count(lectura) >= COINCIDENCIAS_NECESARIAS:
                return lectura

        if lecturas:
            logger.info(
                "ODOMETER OCR | las escalas no coinciden (%s): sin sugerencia",
                ", ".join(str(v) for v in lecturas),
            )
        return None
