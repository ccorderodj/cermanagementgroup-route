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


def test_dos_candidatos_son_una_ambiguedad_y_no_se_sugiere_nada():
    """El odómetro y el cuentaparcial, los dos en la foto: el caso normal.

    Si este test empieza a fallar porque alguien decidió elegir "el más largo"
    o "el de arriba", lo que se habrá perdido es la honestidad de la
    sugerencia: el supervisor vería un número con aspecto de detectado que en
    realidad salió de un desempate inventado.
    """
    assert leer((90.0, "128437"), (87.0, "4512")) is None


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
