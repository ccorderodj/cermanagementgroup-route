"""Cómo el adaptador de Tesseract convierte una salida de OCR en una sugerencia.

Por qué estos tests no necesitan Tesseract
-------------------------------------------
Lo que puede equivocarse aquí no es el reconocimiento —eso es del binario y se
valida en campo— sino **la interpretación de su salida**: qué se acepta como
lectura, qué se descarta por ruido, y sobre todo qué se decide cuando hay más de
un número plausible en la foto. Esa lógica es pura y se prueba sobre el TSV que
Tesseract emite, sin instalar nada. Un test que dependiera del binario sólo
correría en las máquinas que lo tienen, que es como no tenerlo.

La decisión que estos tests defienden
--------------------------------------
Ante dos candidatos —el odómetro total y el cuentaparcial, que es lo que tiene
cualquier salpicadero— **no se sugiere nada**. Elegir uno por tamaño o posición
sería adivinar, y los dos errores no cuestan lo mismo: no sugerir hace teclear,
y sugerir mal puede entrar como kilometraje confirmado si alguien lo acepta sin
mirar. El test `ambiguo` es el que impide que una optimización futura "mejore"
esto eligiendo el número más grande.
"""

from __future__ import annotations

import sys
from decimal import Decimal

import pytest

from app.routers_api.odometer.ocr_tesseract import (
    MAX_LECTURA,
    TesseractReader,
    TesseractUnavailable,
    _a_lectura,
    _candidatos,
    tesseract_disponible,
)


_CABECERA = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    "left\ttop\twidth\theight\tconf\ttext"
)

def foto_decodificable() -> bytes:
    """Un PNG que Pillow puede **abrir**, no sólo reconocer por su cabecera.

    Hace falta uno de verdad: el adaptador preprocesa la imagen antes de
    invocar el binario, así que una cabecera PNG seguida de bytes cualquiera
    fallaría en el decodificador y el test no probaría lo que dice probar. El
    PNG de un píxel que usan otros tests sirve para que el servidor resuelva el
    tipo por sniffing, pero su flujo está truncado y no se puede decodificar.
    """
    import io

    from PIL import Image

    salida = io.BytesIO()
    Image.new("RGB", (64, 24), "white").save(salida, format="PNG")
    return salida.getvalue()


def tsv(*tokens: tuple[float, str]) -> str:
    """El TSV que emite `tesseract ... tsv`, con una fila por palabra."""
    filas = [
        "\t".join(
            ["5", "1", "1", "1", "1", str(i), "0", "0", "10", "10", str(conf), texto]
        )
        for i, (conf, texto) in enumerate(tokens, start=1)
    ]
    return "\n".join([_CABECERA, *filas])


def leer(*tokens: tuple[float, str]) -> Decimal | None:
    return _a_lectura(_candidatos(tsv(*tokens)))


# ── Lo que sí es una sugerencia ─────────────────────────────────────────────


def test_una_lectura_limpia_se_sugiere():
    assert leer((92.0, "128437")) == Decimal("128437.0")


def test_las_decimas_se_conservan():
    """La columna es `Numeric(10, 1)`: la décima es parte de la lectura."""
    assert leer((88.0, "128437.5")) == Decimal("128437.5")


def test_la_escala_se_fija_a_una_decima():
    """Lo que se guarda es exactamente lo que se sugirió, sin redondeos luego."""
    assert str(leer((90.0, "4512"))) == "4512.0"


# ── Lo que no lo es ─────────────────────────────────────────────────────────


def test_por_debajo_de_la_confianza_minima_no_se_sugiere():
    """Un token de baja confianza es reflejo o poca luz, no una lectura."""
    assert leer((31.0, "128437")) is None


def test_un_digito_suelto_no_es_una_lectura():
    """En una foto de salpicadero, casi siempre es un trozo de otro indicador."""
    assert leer((95.0, "7")) is None


def test_entre_odometro_y_cuentaparcial_gana_el_de_mas_digitos():
    """El caso normal de cualquier salpicadero, y el que antes no se resolvía.

    La versión anterior devolvía `None` ante más de un candidato. Era seguro y
    resultó ser demasiado: medido sobre un tablero corriente, el OCR encontraba
    los dos números al 96% de confianza y la pantalla no enseñaba nada, así que
    el supervisor tecleaba siempre.

    Lo que desempata no es la apariencia —ni tamaño, ni posición, ni "el número
    más grande"— sino lo que cada uno cuenta: el odómetro acumula y el
    cuentaparcial se pone a cero, así que el primero tiene más dígitos durante
    casi toda la vida del vehículo.
    """
    assert leer((90.0, "128437"), (87.0, "241.6")) == Decimal("128437.0")
    # Y da igual en qué orden los devuelva Tesseract.
    assert leer((87.0, "241.6"), (90.0, "128437")) == Decimal("128437.0")


def test_un_empate_de_digitos_sigue_siendo_ambiguo():
    """Si no hay un ganador estricto, no se sugiere nada.

    Es lo que queda de la regla anterior, y es lo que impide que esto se
    convierta en "elige uno". Dos números con los mismos dígitos no se pueden
    distinguir por lo que cuentan, y callarse sigue siendo la respuesta
    correcta: una sugerencia equivocada es peor que ninguna.
    """
    assert leer((90.0, "128437"), (88.0, "451278")) is None
    assert leer((90.0, "1234"), (88.0, "567.8")) is None


def test_sin_texto_no_hay_sugerencia():
    assert leer((95.0, "")) is None


def test_el_ruido_no_numerico_se_descarta():
    assert leer((95.0, "ABC")) is None


def test_por_encima_del_maximo_del_contrato_no_se_sugiere():
    """El mismo techo que `OdometerReadingConfirm` y que la base.

    No se inventa un rango de negocio nuevo —§8 lo prohíbe—: se usa el que ya
    existe. Un número de nueve dígitos no cabe en `Numeric(10, 1)` con una
    décima, así que sugerirlo sería ofrecer algo que la confirmación va a
    rechazar.
    """
    assert leer((95.0, "999999999")) is None
    assert MAX_LECTURA == Decimal("99999999.9")


def test_las_filas_de_estructura_del_tsv_no_estorban():
    """Tesseract emite filas de página y bloque con `conf = -1` y sin texto."""
    crudo = "\n".join([
        _CABECERA,
        "\t".join(["1", "1", "0", "0", "0", "0", "0", "0", "100", "100", "-1", ""]),
        "\t".join(["5", "1", "1", "1", "1", "1", "0", "0", "10", "10", "93", "77240"]),
    ])
    assert _a_lectura(_candidatos(crudo)) == Decimal("77240.0")


def test_una_salida_truncada_no_revienta():
    """Si el TSV llega a medias, se descarta la fila y no se levanta nada."""
    crudo = f"{_CABECERA}\n5\t1\t1\t1"
    assert _a_lectura(_candidatos(crudo)) is None


# ── La presencia del binario ────────────────────────────────────────────────


def test_un_binario_que_no_existe_no_esta_disponible():
    """Lo que decide en el arranque si se enchufa el lector o no."""
    assert tesseract_disponible("tesseract-que-no-existe-en-ninguna-parte") is False


def test_estar_en_el_path_no_basta_para_estar_disponible():
    """El caso intermedio que el piloto destapó, y que antes pasaba por bueno.

    Allí el binario estaba instalado y en el `PATH` —`shutil.which` decía que
    sí— y no podía leer nada: primero por una biblioteca ausente y luego porque
    los datos de idioma estaban fuera de donde los busca. Con la comprobación
    anterior el arranque escribía "lector activo" mientras cada foto fallaba.

    Se usa el intérprete de Python como impostor porque existe en cualquier
    máquina donde corra esta suite: pasa el `which` y no sabe listar idiomas,
    que es exactamente la forma del caso real. Un binario de mentira creado en
    un temporal probaría lo mismo con más ceremonia y menos portabilidad.
    """
    assert tesseract_disponible(sys.executable) is False


def test_invocar_un_binario_ausente_se_declara_indisponible():
    """Y si se invoca igualmente, el error es del tipo que el puerto espera.

    Importa que sea `TesseractUnavailable` y no un `FileNotFoundError` suelto:
    `suggest_safely` los convierte los dos en "sin sugerencia", pero un tipo
    propio deja claro en la traza que el problema es el adaptador y no la foto.
    """
    lector = TesseractReader(binary="tesseract-que-no-existe-en-ninguna-parte")
    with pytest.raises(TesseractUnavailable):
        lector.suggest(image=foto_decodificable(), content_type="image/png")


# ── El fallo silencioso que costó el campo ─────────────────────────────────


def test_una_salida_que_no_es_tsv_se_declara_indisponible():
    """El defecto que hacía que **ninguna** fotografía produjera sugerencia.

    Tesseract acepta `tsv` como nombre de fichero de configuración. Cuando ese
    fichero no está en la instalación, avisa por stderr —"Can't open tsv"—,
    **devuelve 0** y cae a salida de texto plano. El texto plano tiene una
    columna y el parser espera doce, así que no se reconocía ningún candidato y
    el adaptador devolvía `None` con cualquier imagen, sin un solo error.

    Ahora el TSV se pide por parámetro, que no depende de ningún fichero, y una
    salida que no lo sea se declara indisponible en vez de confundirse con "no
    vi nada". Son cosas distintas: una es la fotografía y la otra es la
    instalación, y sólo la segunda se arregla.
    """
    import subprocess

    from app.routers_api.odometer import ocr_tesseract

    class _Plano:
        returncode = 0
        stdout = b"128437\n"
        stderr = b"read_params_file: Can't open tsv\n"

    original = subprocess.run
    subprocess.run = lambda *a, **k: _Plano()  # noqa: E731
    try:
        with pytest.raises(ocr_tesseract.TesseractUnavailable):
            ocr_tesseract.TesseractReader().suggest(
                image=foto_decodificable(), content_type="image/png"
            )
    finally:
        subprocess.run = original


def test_el_modo_de_segmentacion_es_texto_disperso():
    """Fija el modo, porque volver a `7` reproduce el fallo de campo entero.

    Con `--psm 7` —"una sola línea de texto"— un salpicadero con dos grupos
    numéricos no produce **ningún** token. Medido: `psm=7 -> []` frente a
    `psm=11 -> [('128437', 96.2), ('241.6', 96.6)]`.
    """
    from app.routers_api.odometer.ocr_tesseract import _PSM_TEXTO_DISPERSO

    assert _PSM_TEXTO_DISPERSO == "11"


# ── Las variantes y el acuerdo ─────────────────────────────────────────────


class _VariantesFijas:
    """Un lector que devuelve una lectura distinta por variante, sin Tesseract.

    Se sustituye `_leer_variante` porque lo que se prueba aquí no es el
    reconocimiento —eso depende del binario y de la fotografía— sino **la regla
    de decisión**: cuándo se acepta una lectura y cuándo se calla.
    """

    def __init__(self, *por_variante):
        self.por_variante = list(por_variante)
        self.pasadas = 0

    def __call__(self, png):
        indice = min(self.pasadas, len(self.por_variante) - 1)
        self.pasadas += 1
        return self.por_variante[indice]


def _con_variantes(monkeypatch, *valores, n_variantes=3):
    """Fija las lecturas por variante y cuántas variantes distintas hay."""
    from app.routers_api.odometer import ocr_tesseract as m

    falso = _VariantesFijas(*valores)
    monkeypatch.setattr(m.TesseractReader, "_leer_variante",
                        lambda self, png: falso(png))
    monkeypatch.setattr(
        m, "_variantes",
        lambda image: [(f"v{i}", (100 + i, 50), b"x") for i in range(n_variantes)],
    )
    lector = m.TesseractReader()
    return lector.suggest(image=b"irrelevante", content_type="image/jpeg"), falso


def test_dos_variantes_que_coinciden_producen_la_sugerencia(monkeypatch):
    """El caso normal: la foto está bien y dos preparaciones dicen lo mismo."""
    valor, falso = _con_variantes(
        monkeypatch, Decimal("151517.0"), Decimal("151517.0")
    )
    assert valor == Decimal("151517.0")
    assert falso.pasadas == 2, "con acuerdo a la segunda no hace falta la tercera"


def test_variantes_que_discrepan_no_sugieren_nada(monkeypatch):
    """El caso que esto existe para evitar.

    Una lectura equivocada que el supervisor confirma sin mirar entra como
    kilometraje confirmado por una persona, y ese daño no se deshace. Si las
    preparaciones no coinciden, la respuesta honesta es que no se sabe.
    """
    valor, falso = _con_variantes(
        monkeypatch, Decimal("151517.0"), Decimal("151577.0"), Decimal("151507.0")
    )
    assert valor is None
    assert falso.pasadas == 3


def test_una_sola_variante_que_lee_no_basta(monkeypatch):
    """Leer en una preparación y nada en las otras no es confianza suficiente."""
    valor, _ = _con_variantes(monkeypatch, Decimal("60000.0"), None, None)
    assert valor is None


def test_con_una_sola_variante_distinta_no_hay_acuerdo_posible(monkeypatch):
    """La regla conservadora cuando el deduplicado deja una sola pasada.

    Si sólo queda una entrada materialmente distinta no se baja el listón para
    que una observación baste: se calla. Relajarlo convertiría el control en una
    formalidad justo en las imágenes difíciles, que son las que lo necesitan.
    """
    valor, falso = _con_variantes(
        monkeypatch, Decimal("151517.0"), n_variantes=1
    )
    assert valor is None
    assert falso.pasadas == 1


def test_el_minimo_de_digitos_descarta_otros_indicadores():
    """Un salpicadero está lleno de números de dos y tres dígitos.

    La velocidad, la temperatura, la marcha, el nivel de combustible. Con el
    mínimo en 2 el velocímetro se colaba como lectura de odómetro en cuanto el
    odómetro no se leía bien.
    """
    assert leer((95.0, "60")) is None
    assert leer((95.0, "120")) is None
    assert leer((95.0, "1284")) == Decimal("1284.0")


# ── Las variantes son materialmente distintas ──────────────────────────────


def test_las_variantes_no_repiten_la_misma_entrada():
    """El defecto que corrige este checkpoint, fijado.

    Antes las pasadas se pedían por dimensión absoluta —2400, 3200, 1600— sobre
    un normalizador que **sólo reduce**. Con una imagen de 185 px las tres
    producían exactamente la misma imagen, y tres lecturas idénticas de la misma
    entrada se contaban como acuerdo multiescala. Medido entonces:

        escala 2400 -> (185, 72) -> 151517
        escala 3200 -> (185, 72) -> 151517
        escala 1600 -> (185, 72) -> 151517

    El resultado era correcto y el razonamiento no: repetir la misma evidencia
    no es confianza adicional.
    """
    from app.routers_api.odometer.ocr_tesseract import _variantes
    from tests.fixtures_odometer import odometro_rodillo

    variantes = _variantes(odometro_rodillo())

    assert len(variantes) >= 2, "una imagen pequeña debe dar más de una pasada"
    # Ninguna entrada se repite: ni los bytes ni la combinación de dimensión y
    # preparación.
    bytes_vistos = [png for _, _, png in variantes]
    assert len(set(bytes_vistos)) == len(bytes_vistos), (
        "dos variantes producen exactamente la misma imagen"
    )


def test_las_variantes_duplicadas_se_descartan(monkeypatch):
    """Y si alguien configurara dos variantes iguales, se colapsan.

    Es la red de debajo: la configuración actual no puede producir duplicados,
    pero una edición futura sí podría, y el acuerdo no debe poder satisfacerse
    por ahí.
    """
    from app.routers_api.odometer import ocr_tesseract as m
    from tests.fixtures_odometer import odometro_rodillo

    monkeypatch.setattr(m, "VARIANTES", ((1.0, True), (1.0, True), (1.0, True)))
    assert len(m._variantes(odometro_rodillo())) == 1


def test_el_preprocesado_devuelve_su_dimension_efectiva():
    """Sin ese dato no se puede saber si dos pasadas son distintas."""
    from app.routers_api.odometer.ocr_tesseract import _preprocesar
    from tests.fixtures_odometer import odometro_rodillo

    png, dim = _preprocesar(odometro_rodillo(), 2400)
    assert dim == (185, 72), "una imagen pequeña no se amplía en el preprocesado"
    assert png[:4] == bytes((0x89, 0x50, 0x4E, 0x47)), "sigue siendo un PNG"


def test_la_nitidez_es_determinista():
    """La misma entrada produce exactamente la misma salida.

    Importa porque el acuerdo entre variantes se apoya en que cada preparación
    sea reproducible: si el preprocesado tuviera cualquier aleatoriedad, dos
    ejecuciones del mismo caso podrían decidir cosas distintas.
    """
    from app.routers_api.odometer.ocr_tesseract import _preprocesar
    from tests.fixtures_odometer import odometro_rodillo

    foto = odometro_rodillo()
    assert _preprocesar(foto, 2400)[0] == _preprocesar(foto, 2400)[0]


def test_la_nitidez_cambia_la_imagen():
    """Y la variante sin nitidez es de verdad otra entrada, no la misma."""
    from app.routers_api.odometer.ocr_tesseract import _preprocesar
    from tests.fixtures_odometer import odometro_rodillo

    foto = odometro_rodillo()
    con, _ = _preprocesar(foto, 2400, nitidez=True)
    sin, _ = _preprocesar(foto, 2400, nitidez=False)
    assert con != sin, (
        "si la nitidez no cambiara nada, contarlas como dos pasadas "
        "distintas sería la misma mentira que se viene a corregir"
    )


def test_el_preprocesado_no_escribe_en_disco(tmp_path, monkeypatch):
    """Una foto de salpicadero no puede quedar en un temporal sin dueño."""
    from app.routers_api.odometer.ocr_tesseract import _preprocesar
    from tests.fixtures_odometer import odometro_rodillo

    monkeypatch.chdir(tmp_path)
    antes = set(tmp_path.rglob("*"))
    _preprocesar(odometro_rodillo(), 2400)
    assert set(tmp_path.rglob("*")) == antes


# ── Contra Tesseract de verdad ─────────────────────────────────────────────


@pytest.mark.skipif(
    not tesseract_disponible(),
    reason=(
        "Tesseract no está instalado aquí. El resto de este archivo prueba la "
        "lógica de decisión sin el binario; este caso necesita el motor y se "
        "ejecuta donde está, no se silencia en todas partes."
    ),
)
def test_el_recorte_de_referencia_produce_la_lectura_esperada():
    """La clase de imagen que CER reportó: recorte ajustado, baja resolución.

    Es el caso que motivó este checkpoint. El fixture reproduce sus propiedades
    técnicas —185×72, dígitos claros sobre rodillos oscuros con costuras,
    desenfoque suave— sin guardar la fotografía de campo, que lleva salpicadero
    y a veces matrícula.

    Lo que demuestra: que con el preprocesado y las variantes corregidas la
    lectura sale. Lo que **no** demuestra: que el motor lea un salpicadero real,
    con su reflejo, su ángulo y la fuente del fabricante. Eso es validación de
    campo y es de CER.
    """
    from app.routers_api.odometer.ocr_tesseract import TesseractReader
    from tests.fixtures_odometer import LECTURA_DE_REFERENCIA, odometro_rodillo

    lectura = TesseractReader().suggest(
        image=odometro_rodillo(), content_type="image/png"
    )

    assert lectura == Decimal(f"{LECTURA_DE_REFERENCIA}.0"), (
        f"la referencia debía leerse como {LECTURA_DE_REFERENCIA}, salió {lectura}"
    )


@pytest.mark.skipif(not tesseract_disponible(), reason="Tesseract no está instalado aquí")
def test_un_salpicadero_sin_odometro_legible_no_sugiere_el_velocimetro():
    """La protección contra falsos positivos, con el motor real.

    Un tablero donde el odómetro no se lee pero sí se ve una velocidad corta no
    puede convertirse en una sugerencia de kilometraje: el supervisor podría
    confirmarla sin mirar y entraría como un hecho confirmado por una persona.
    """
    from app.routers_api.odometer.ocr_tesseract import TesseractReader
    from tests.fixtures_odometer import salpicadero

    lectura = TesseractReader().suggest(
        image=salpicadero(odometro=None, parcial=None, velocidad="60"),
        content_type="image/jpeg",
    )

    assert lectura is None, f"se sugirió {lectura} sin odómetro legible"
