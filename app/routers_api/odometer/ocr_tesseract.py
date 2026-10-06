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

#: Lado mayor de la imagen. Por encima se reduce; por debajo **no se amplía**,
#: y eso ya no es sólo una precaución: ver `VARIANTES`.
TOPE_BASE = 2400

#: Umbral de la máscara de enfoque, común a todas las pasadas: por debajo de
#: esta diferencia local no se realza nada, que es lo que evita amplificar el
#: grano del sensor en las zonas planas del salpicadero.
NITIDEZ_UMBRAL = 2

#: Las pasadas, como `(nombre, radio, porcentaje)` de la máscara de enfoque.
#: Todas a **resolución nativa**: la diversidad está en la preparación.
#:
#: Qué se midió para elegir estas cuatro
#: --------------------------------------
#: Se puntuaron todos los subconjuntos de un repertorio de diez preparaciones
#: sobre 25 imágenes con verdades distintas (no sólo la de referencia), 20
#: positivas y 5 negativas, con Tesseract 5.5.3. El criterio fue primero el
#: número de **consensos equivocados** y sólo después el de aciertos, porque una
#: sugerencia errónea que el supervisor acepta sin mirar cuesta más que un
#: campo vacío.
#:
#:     conjunto                              aciertos  equivocados  callados
#:     r1.0-180 r1.5-180 r1.2-240 r2.0-240       17          1          7
#:     r1.0-180 r1.2-180 r1.5-180 (el de §7)     13          2          6
#:     r1.2-180 sin-nitidez x2 (MR !54)          12          1          8
#:
#: Por qué no la familia de un solo radio
#: ---------------------------------------
#: La dirección de partida de la instrucción —tres radios al 180%— rinde peor
#: en las dos columnas que importan. Variar sólo el radio produce errores
#: **correlacionados**: medido sobre un salpicadero de 1400 px con el odómetro
#: al 18% del encuadre, `r1.0` y `r1.5` leían *los dos* `191517` donde la
#: verdad era `151517`, y al coincidir se confirmaban. Un acuerdo entre dos
#: preparaciones que fallan igual no es evidencia independiente; es el mismo
#: fallo contado dos veces, que es exactamente lo que PR-04 prohíbe en su otra
#: forma. Estas cuatro mueven radio **y** porcentaje, y en ese caso se reparten
#: entre dos valores erróneos distintos, que es lo que deja al sistema callado.
VARIANTES: tuple[tuple[str, float, int], ...] = (
    ("r1.0-p180", 1.0, 180),
    ("r1.5-p180", 1.5, 180),
    ("r1.2-p240", 1.2, 240),
    ("r2.0-p240", 2.0, 240),
)

#: Variantes distintas que deben coincidir para aceptar una lectura.
#:
#: Dos, y no se baja. Si sólo hay una variante distinta disponible no hay
#: acuerdo posible y no se sugiere nada: relajar esto para que una sola
#: observación bastara convertiría el control en una formalidad justo en las
#: imágenes más difíciles, que son las que lo necesitan.
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


def _preprocesar(
    image: bytes,
    max_dimension: int = TOPE_BASE,
    *,
    radio: float | None = 1.0,
    porcentaje: int = 180,
) -> tuple[bytes, tuple[int, int]]:
    """Deja la foto como Tesseract la lee mejor, y dice a qué tamaño quedó.

    La orientación importa más de lo que parece: un teléfono guarda la foto
    girada con una etiqueta EXIF, y Tesseract no mira la etiqueta. Una foto de
    costado no produce una lectura mala — no produce ninguna. Eso lo resuelve
    `normalize_image`, que además limita el lado mayor y quita el EXIF.

    Gris y contraste automático rescatan las fotos con poca luz y las que
    tienen el reflejo en una esquina. No se binariza con un umbral fijo a
    propósito: uno que va bien a mediodía deja en negro la foto de un parking.

    La **nitidez** separa los bordes de los dígitos, que es lo que necesita un
    odómetro de rodillo fotografiado de lejos. No inventa detalle: realza el
    contraste local que ya existe, y por eso sigue siendo preprocesado y no
    evidencia nueva. `radio=None` la desactiva, que es lo que permite medir
    cuánto aporta en vez de suponerlo.

    No se añadió ningún suavizado previo: se probó, y con él una de las
    imágenes pasó a producir `191817` en vez de `151517` —una lectura
    **equivocada**, que es peor que ninguna.

    Devuelve también la dimensión efectiva porque es parte de lo que se
    registra por variante cuando hay que diagnosticar una foto de campo.
    """
    import io

    from PIL import Image, ImageFilter, ImageOps

    from app.core.storage.media import normalize_image

    normalizada = normalize_image(
        image, max_dimension=max_dimension, jpeg_quality=90
    )

    imagen = Image.open(io.BytesIO(normalizada.data))
    imagen.load()
    gris = ImageOps.autocontrast(imagen.convert("L"))
    if radio is not None:
        gris = gris.filter(
            ImageFilter.UnsharpMask(
                radius=radio, percent=porcentaje, threshold=NITIDEZ_UMBRAL
            )
        )

    salida = io.BytesIO()
    gris.save(salida, format="PNG", optimize=False)
    return salida.getvalue(), gris.size


def _variantes(image: bytes) -> list[tuple[str, tuple[int, int], bytes]]:
    """Las entradas realmente distintas que se le van a dar al motor.

    Por qué se compara el contenido y no los parámetros
    ----------------------------------------------------
    Dos configuraciones distintas pueden producir **la misma imagen**. Medido:
    sobre un salpicadero sin nada legible —una superficie casi plana— las
    dieciséis preparaciones del repertorio dieron los mismos bytes exactos,
    porque realzar el contraste local de una zona sin contraste local no cambia
    nada. Deduplicar por el nombre de la variante, o por su dimensión, habría
    dejado pasar esas dieciséis como evidencia independiente.

    Así que la clave es el **hash del PNG ya preparado**. Es la única definición
    de "entrada distinta" que no se puede satisfacer por accidente, y es la
    forma honesta de la regla que ya estaba escrita: repetir la misma evidencia
    no es confianza.
    """
    import hashlib

    salida: list[tuple[str, tuple[int, int], bytes]] = []
    vistas: set[str] = set()

    for nombre, radio, porcentaje in VARIANTES:
        png, dim = _preprocesar(
            image, TOPE_BASE, radio=radio, porcentaje=porcentaje
        )
        huella = hashlib.sha256(png).hexdigest()
        if huella in vistas:
            logger.debug(
                "ODOMETER OCR | variante %s produce una entrada ya vista: "
                "se descarta",
                nombre,
            )
            continue
        vistas.add(huella)
        salida.append((nombre, dim, png))

    return salida


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

    def _leer_variante(self, png: bytes) -> Decimal | None:
        """Una pasada: invocar el binario sobre esa entrada e interpretar."""
        orden = [
            self.binary,
            "stdin",
            "stdout",
            "-l", self.language,
            "--psm", _PSM_TEXTO_DISPERSO,
            "-c", f"tessedit_char_whitelist={_CARACTERES}",
            # El TSV se pide por **parámetro**, no por el fichero de
            # configuración `tsv`: donde ese fichero no está, Tesseract avisa
            # por stderr, devuelve 0 y cae a texto plano, y el parser no
            # reconocía ningún candidato con **ninguna** fotografía.
            "-c", "tessedit_create_tsv=1",
        ]

        try:
            resultado = subprocess.run(
                orden,
                input=png,
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
            raise TesseractUnavailable(
                f"{self.binary} no devolvió TSV: {tsv.splitlines()[:1]}"
            )
        return _a_lectura(_candidatos(tsv))

    def suggest(self, *, image: bytes, content_type: str) -> Decimal | None:
        """Lee todas las variantes y sugiere sólo si **un** valor tiene acuerdo.

        Por qué se leen todas antes de decidir
        ---------------------------------------
        La versión anterior devolvía en cuanto un valor llegaba a dos
        coincidencias. Con eso, el resultado dependía del **orden de la tupla**
        de variantes, y no en teoría: medido sobre un salpicadero de 1400 px
        donde la verdad era `151517`, dos preparaciones leían `191517` y otras
        dos `191817`.

            primero-en-llegar -> `191517` o `191817`, según el orden
            un-solo-ganador   -> sin sugerencia

        Las mismas lecturas y el mismo repertorio; sólo cambia la regla. La
        primera entrega un número equivocado con cara de confirmado y la
        segunda se calla, que es lo correcto cuando la foto no distingue.

        Así que ahora se leen todas las variantes y se exige que exactamente un
        valor alcance el acuerdo. Si lo alcanzan dos, hay conflicto y no se
        sugiere nada: no se escoge "el más confiado" para tener algo que
        enseñar. Cuesta una invocación más en el caso bueno —se midió— y el
        precio compra un resultado que no depende de cómo esté escrita una
        constante.
        """
        lecturas: list[Decimal] = []
        variantes = _variantes(image)

        for nombre, dim, png in variantes:
            lectura = self._leer_variante(png)
            # A nivel INFO a propósito: cuando el piloto devuelve
            # `ocr_suggestion: null` esto es lo único que explica por qué, y
            # sin él la única respuesta posible era "no sugirió". No lleva la
            # imagen, ni el vehículo, ni la sesión: sólo la variante, el tamaño
            # efectivo y el número.
            logger.info(
                "ODOMETER OCR | variante %s %sx%s -> %s",
                nombre, dim[0], dim[1], lectura,
            )
            if lectura is not None:
                lecturas.append(lectura)

        if len(variantes) < COINCIDENCIAS_NECESARIAS:
            logger.info(
                "ODOMETER OCR | sólo %d variante distinta: sin acuerdo posible, "
                "sin sugerencia",
                len(variantes),
            )
            return None

        con_acuerdo = [
            valor
            for valor in dict.fromkeys(lecturas)
            if lecturas.count(valor) >= COINCIDENCIAS_NECESARIAS
        ]

        if len(con_acuerdo) == 1:
            logger.info(
                "ODOMETER OCR | acuerdo %d/%d -> %s",
                lecturas.count(con_acuerdo[0]), len(variantes), con_acuerdo[0],
            )
            return con_acuerdo[0]

        if len(con_acuerdo) > 1:
            logger.info(
                "ODOMETER OCR | acuerdo en conflicto (%s): sin sugerencia",
                ", ".join(str(v) for v in con_acuerdo),
            )
        else:
            logger.info(
                "ODOMETER OCR | sin acuerdo entre %d variantes (%s): "
                "sin sugerencia",
                len(variantes),
                ", ".join(str(v) for v in lecturas) or "ninguna leyó",
            )
        return None
