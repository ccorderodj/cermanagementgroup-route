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
    assert falso.pasadas == 3, (
        "se leen todas las variantes antes de decidir: cortar en la segunda "
        "hacía que el resultado dependiera del orden de la tupla"
    )


def test_tres_variantes_donde_dos_coinciden_sugieren_ese_valor(monkeypatch):
    """La mayoría vale aunque una preparación discrepe.

    Es el caso corriente de la clase de imagen que reportó CER: en el
    salpicadero de 524 px una de las cuatro preparaciones no encuentra nada y
    las otras tres leen lo mismo. Exigir unanimidad dejaría sin sugerencia
    justo las fotos que sí se pueden leer.
    """
    valor, _ = _con_variantes(
        monkeypatch, Decimal("151517.0"), None, Decimal("151517.0")
    )
    assert valor == Decimal("151517.0")


def test_el_orden_de_las_variantes_no_cambia_el_resultado(monkeypatch):
    """El defecto de la regla anterior, fijado.

    Con "devuelve en cuanto un valor llega a dos", dos lecturas empatadas a dos
    hacían que **el orden de la tupla** decidiera cuál se sugería. Medido sobre
    un salpicadero de 1400 px donde la verdad era `151517`:

        primero-en-llegar -> `191517` o `191817`, según el orden
        un-solo-ganador   -> sin sugerencia

    Las mismas lecturas y el mismo repertorio; sólo cambia la regla. La primera
    entrega un número equivocado con cara de confirmado.
    """
    import itertools

    lecturas = (Decimal("191517.0"), Decimal("191517.0"),
                Decimal("191817.0"), Decimal("191817.0"))

    resultados = {
        _con_variantes(monkeypatch, *orden, n_variantes=4)[0]
        for orden in itertools.permutations(lecturas)
    }

    assert resultados == {None}, (
        f"el resultado depende del orden de las variantes: {resultados}"
    )


def test_dos_valores_con_acuerdo_son_un_conflicto_no_una_mayoria(monkeypatch):
    """Si dos valores distintos alcanzan el acuerdo, no se elige ninguno.

    No se escoge "el más confiado" para tener algo que enseñar: que dos
    preparaciones confirmen `A` y otras dos `B` significa que la foto no
    distingue, y entonces el campo vacío es la respuesta correcta.
    """
    valor, _ = _con_variantes(
        monkeypatch,
        Decimal("151517.0"), Decimal("151517.0"),
        Decimal("161617.0"), Decimal("161617.0"),
        n_variantes=4,
    )
    assert valor is None


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

    monkeypatch.setattr(
        m, "VARIANTES",
        (("a", 1.2, 180), ("b", 1.2, 180), ("c", 1.2, 180)),
    )
    assert len(m._variantes(odometro_rodillo())) == 1


def test_configuraciones_distintas_que_dan_la_misma_imagen_se_colapsan():
    """El duplicado que no se ve en los parámetros, medido.

    Sobre una superficie casi plana —un salpicadero donde no hay nada legible—
    realzar el contraste local no cambia nada, y las cuatro preparaciones
    producen **los mismos bytes exactos**. Deduplicar por el nombre de la
    variante, o por su dimensión, habría dejado pasar las cuatro como evidencia
    independiente justo en la imagen donde no hay ninguna evidencia.

    Por eso la clave del deduplicado es el hash del PNG preparado: es la única
    definición de "entrada distinta" que no se puede satisfacer por accidente.
    """
    from app.routers_api.odometer.ocr_tesseract import _variantes
    from tests.fixtures_odometer import salpicadero

    plano = salpicadero(odometro=None, parcial=None, velocidad=None)

    assert len(_variantes(plano)) == 1, (
        "cuatro configuraciones distintas sobre una imagen sin contraste local "
        "dan la misma entrada, y sólo puede contar una vez"
    )


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
    """Y cada preparación del repertorio es de verdad otra entrada.

    No basta con que los parámetros difieran: lo que tiene que diferir son los
    píxeles. Si dos preparaciones dieran la misma imagen, contarlas como dos
    pasadas sería la misma mentira que este checkpoint viene a corregir en su
    otra forma.
    """
    from app.routers_api.odometer.ocr_tesseract import VARIANTES, _preprocesar
    from tests.fixtures_odometer import odometro_rodillo

    foto = odometro_rodillo()
    sin, _ = _preprocesar(foto, 2400, radio=None)
    preparadas = {
        nombre: _preprocesar(foto, 2400, radio=radio, porcentaje=pct)[0]
        for nombre, radio, pct in VARIANTES
    }

    assert len(set(preparadas.values())) == len(VARIANTES), (
        f"dos preparaciones del repertorio dan la misma imagen: "
        f"{[n for n in preparadas]}"
    )
    assert sin not in preparadas.values(), "alguna variante no realza nada"


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
def test_el_salpicadero_de_referencia_produce_la_lectura_esperada():
    """La otra clase que reportó CER: salpicadero completo a 524 px de ancho.

    Es la que devolvía `ocr_suggestion: null` en el piloto. Con el repertorio
    anterior las variantes discrepaban —una leía la verdad, la ampliación ×2
    leía otro número por encima del umbral de confianza— y el acuerdo no se
    alcanzaba. Con cuatro preparaciones a resolución nativa, tres coinciden.
    """
    from app.routers_api.odometer.ocr_tesseract import TesseractReader
    from tests.fixtures_odometer import LECTURA_DE_REFERENCIA, salpicadero

    lectura = TesseractReader().suggest(
        image=salpicadero(reducir_a=524), content_type="image/jpeg"
    )

    assert lectura == Decimal(f"{LECTURA_DE_REFERENCIA}.0"), (
        f"la clase de salpicadero debía leerse como {LECTURA_DE_REFERENCIA}, "
        f"salió {lectura}"
    )


@pytest.mark.skipif(not tesseract_disponible(), reason="Tesseract no está instalado aquí")
def test_el_cuentaparcial_no_desplaza_al_odometro_en_el_salpicadero():
    """Odómetro y cuentaparcial en el mismo encuadre, con el motor real.

    La regla de dígitos elige el que acumula frente al que se pone a cero, y
    tiene que seguir haciéndolo cuando el acuerdo se calcula sobre cuatro
    preparaciones en vez de tres.
    """
    from app.routers_api.odometer.ocr_tesseract import TesseractReader
    from tests.fixtures_odometer import LECTURA_DE_REFERENCIA, salpicadero

    lectura = TesseractReader().suggest(
        image=salpicadero(parcial="241.6", reducir_a=524),
        content_type="image/jpeg",
    )

    assert lectura == Decimal(f"{LECTURA_DE_REFERENCIA}.0")


@pytest.mark.skipif(not tesseract_disponible(), reason="Tesseract no está instalado aquí")
def test_un_odometro_pequeno_en_el_encuadre_no_produce_una_lectura_equivocada():
    """El límite conocido, y que al menos se calle en vez de equivocarse.

    Con el salpicadero a 1400 px y el odómetro ocupando el 18% del encuadre los
    dígitos quedan en unos pocos píxeles de alto, y el motor confunde el `5`
    con un `9`. Lo que este caso fija no es que lea —no lee— sino que **no
    sugiera un número equivocado**: las cuatro preparaciones se reparten entre
    `191517` y `191817`, dos valores con acuerdo, y eso es un conflicto.

    Con la regla anterior, el mismo reparto devolvía uno de los dos según el
    orden de la tupla de variantes.
    """
    from app.routers_api.odometer.ocr_tesseract import TesseractReader
    from tests.fixtures_odometer import LECTURA_DE_REFERENCIA, salpicadero

    lectura = TesseractReader().suggest(
        image=salpicadero(), content_type="image/jpeg"
    )

    assert lectura is None or lectura == Decimal(f"{LECTURA_DE_REFERENCIA}.0"), (
        f"se sugirió {lectura}, que no es la lectura real: un odómetro "
        f"demasiado pequeño en el encuadre debe quedarse sin sugerencia"
    )


@pytest.mark.skipif(not tesseract_disponible(), reason="Tesseract no está instalado aquí")
def test_un_desenfoque_destructivo_todavia_puede_enganar_al_acuerdo():
    """Un límite del mecanismo de acuerdo, medido y escrito, no disimulado.

    Con un desenfoque de σ=4.0 sobre el recorte, el `5` **se convierte** en un
    `6` dentro de la propia imagen. Las diez preparaciones que se probaron
    leyeron `161617` con confianzas de 84 a 91: no es que una variante falle,
    es que la imagen ya sostiene el número equivocado.

        sin-nitidez  161617 @ 89.71      r1.2-p240  161617 @ 91.23
        r1.0-p180    161617 @ 90.09      r2.0-p240  161617 @ 84.44

    De ahí la frase que importa para el piloto: **el acuerdo entre
    preparaciones detecta fragilidad del preprocesado, no ambigüedad de la
    imagen.** Ninguna composición de variantes lo resuelve, y subir el umbral
    de confianza a 92 para taparlo dejaría sin sugerencia todo lo demás. Es
    anterior a este checkpoint y sigue después: el control que queda es la
    confirmación del supervisor, que por esto no es una formalidad.

    Este test documenta el límite. Si algún día deja de cumplirse porque el
    motor mejora, se borra — no se ajusta para que siga pasando.
    """
    from app.routers_api.odometer.ocr_tesseract import TesseractReader
    from tests.fixtures_odometer import LECTURA_DE_REFERENCIA, odometro_rodillo

    lectura = TesseractReader().suggest(
        image=odometro_rodillo(desenfoque=4.0), content_type="image/png"
    )

    assert lectura != Decimal(f"{LECTURA_DE_REFERENCIA}.0"), (
        "si ahora se lee bien un desenfoque destructivo, este límite ya no "
        "existe y este test sobra"
    )


def test_el_repertorio_no_amplia_la_imagen():
    """Ninguna variante trabaja sobre una imagen ampliada, y es una decisión.

    La ampliación ×2 se midió y salió: sobre 25 imágenes no aportó **ningún**
    acierto que las preparaciones nativas no dieran ya, y por su cuenta produjo
    tres lecturas equivocadas —`191817`, `131517`, `161617`— dos de ellas con
    valores que ninguna variante nativa genera. Es decir, metía en el conjunto
    errores nuevos con los que otro error podría coincidir.

    Ampliar sigue siendo una opción de preprocesado, no una regla; lo que no es
    es evidencia adicional.
    """
    from app.routers_api.odometer.ocr_tesseract import TOPE_BASE, _variantes
    from tests.fixtures_odometer import odometro_rodillo

    for nombre, dim, _ in _variantes(odometro_rodillo()):
        assert dim == (185, 72), (
            f"la variante {nombre} trabaja a {dim}: el repertorio es nativo"
        )
        assert max(dim) <= TOPE_BASE


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
