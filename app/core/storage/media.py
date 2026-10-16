"""
Multimedia de documentos: qué es un archivo y qué se deriva de él (WP-6).

Llegan fotos de teléfono (HEIC en iPhone, WEBP en algunos Android), capturas de
webcam, escaneos en PDF de varias páginas. Tres reglas:

* **El tipo sale de los bytes.** Un navegador de escritorio manda un `.heic`
  como `application/octet-stream`, y el tipo declarado lo escribe quien sube el
  archivo. Si se declara uno concreto, los bytes tienen que coincidir.
* **El original no se toca.** Es la evidencia y su huella es la que se guardó.
  Lo que se genera —la versión normalizada y la miniatura— son objetos
  **derivados**, con huella propia y la huella del original del que salen.
* **Nada se descodifica antes del escáner.** Abrir una imagen es ejecutar un
  descodificador sobre contenido que nadie ha analizado. Antes del escáner sólo
  se miran la firma y, en un PDF, si está cifrado o tiene demasiadas páginas,
  que es lo que se le puede decir al trabajador en el momento. Los derivados se
  generan cuando el documento sale limpio.

La versión normalizada quita los metadatos EXIF —una foto de teléfono lleva la
ubicación GPS de la casa del trabajador—, aplica la orientación de la cámara y
limita las dimensiones.
"""

from __future__ import annotations

import hashlib
import io
import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field

#: Lo que un navegador manda cuando no sabe qué es el archivo.
GENERIC_TYPES = frozenset({"", "application/octet-stream", "binary/octet-stream"})

IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"})
PDF_TYPE = "application/pdf"

#: Marcas ISO-BMFF. `heic`/`heix` son HEVC; `mif1`/`msf1`, HEIF genérico.
_HEIC_BRANDS = frozenset({b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis"})
_HEIF_BRANDS = frozenset({b"mif1", b"msf1"})

#: Tipos que se consideran el mismo: el mismo contenedor, distinta etiqueta.
_FAMILIES = ({"image/heic", "image/heif"}, {"image/jpeg", "image/jpg", "image/pjpeg"})

#: Por encima de esto, una imagen es una bomba de descompresión, no una foto.
#: Un teléfono de 200 MP produce 200 millones de píxeles; nada de lo que se
#: sube aquí lo necesita.
MAX_PIXELS = 120_000_000

THUMBNAIL_SIZE = 320


class MediaRejected(Exception):
    """El archivo no se puede aceptar. El mensaje es para quien lo subió."""


@dataclass(frozen=True)
class Derivative:
    kind: str
    data: bytes = field(repr=False)
    content_type: str
    width: int | None = None
    height: int | None = None
    page_count: int | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


# ══ Tipo ═════════════════════════════════════════════════════════════════════════


def sniff_content_type(data: bytes) -> str | None:
    """El tipo por la firma de sus primeros bytes, o `None` si no se reconoce."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"%PDF-"):
        return PDF_TYPE
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        caja = int.from_bytes(data[:4], "big")
        fin = min(max(caja, 16), len(data), 256)
        marcas = {data[8:12]} | {data[i : i + 4] for i in range(16, fin - 3, 4)}
        if marcas & _HEIC_BRANDS:
            return "image/heic"
        if marcas & _HEIF_BRANDS:
            return "image/heif"
    return None


def _normalize_declared(declared: str | None) -> str:
    return (declared or "").split(";", 1)[0].strip().lower()


def same_family(a: str, b: str) -> bool:
    return a == b or any(a in f and b in f for f in _FAMILIES)


def resolve_content_type(*, data: bytes, declared: str | None) -> str:
    """El tipo con el que se guarda el archivo.

    Declarado genérico: manda lo que dicen los bytes, y si no dicen nada se
    rechaza. Declarado concreto: los bytes tienen que ser de ese tipo, salvo que
    sea un tipo sin firma conocida, que se acepta como se aceptaba.
    """
    declarado = _normalize_declared(declared)
    real = sniff_content_type(data)
    if declarado in GENERIC_TYPES:
        if real is None:
            raise MediaRejected("The file type could not be recognised.")
        return real
    conocidos = IMAGE_TYPES | {PDF_TYPE, "image/jpg", "image/pjpeg"}
    if declarado in conocidos:
        if real is None or not same_family(declarado, real):
            raise MediaRejected(f"The file contents are not a valid {declarado}.")
        return real
    return declarado


# ══ PDF ══════════════════════════════════════════════════════════════════════════


def inspect_pdf(data: bytes, *, max_pages: int) -> int | None:
    """Páginas del PDF. Rechaza los cifrados y los que pasan del límite.

    Un PDF que `pypdf` no consigue leer no se rechaza aquí: se guarda como
    evidencia, pasa por el escáner y se queda sin vista previa. Rechazarlo
    sería decidir con un analizador lo que no le corresponde.
    """
    from pypdf import PasswordType, PdfReader

    try:
        lector = PdfReader(io.BytesIO(data), strict=False)
        cifrado = lector.is_encrypted
        # Con sólo contraseña de propietario —restricciones de edición, habitual
        # en formularios estatales— se abre sin contraseña y no es un problema.
        if cifrado and lector.decrypt("") != PasswordType.NOT_DECRYPTED:
            cifrado = False
        paginas = None if cifrado else len(lector.pages)
    except Exception:
        return None
    if cifrado:
        raise MediaRejected(
            "Password-protected PDFs cannot be accepted. Save an unlocked copy and upload it again."
        )
    if paginas is not None and paginas > max_pages:
        raise MediaRejected(f"The PDF has {paginas} pages; the limit is {max_pages}.")
    return paginas


# ══ Derivados ════════════════════════════════════════════════════════════════════


@contextmanager
def _pixel_limit():
    """El límite de píxeles sólo mientras se descodifica.

    `Image.MAX_IMAGE_PIXELS` es global de Pillow. Fijarlo y dejarlo puesto
    cambiaría el comportamiento de cualquier otro código que abra imágenes en el
    mismo proceso.
    """
    from PIL import Image

    anterior = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            yield
    finally:
        Image.MAX_IMAGE_PIXELS = anterior


def _open_image(data: bytes):
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()
    with _pixel_limit():
        imagen = Image.open(io.BytesIO(data))
        imagen.load()
    return imagen


def _to_rgb(imagen):
    from PIL import Image

    if imagen.mode in ("RGBA", "LA", "P", "PA"):
        con_alfa = imagen.convert("RGBA")
        fondo = Image.new("RGB", con_alfa.size, "white")
        fondo.paste(con_alfa, mask=con_alfa.getchannel("A"))
        return fondo
    return imagen.convert("RGB") if imagen.mode != "RGB" else imagen


def _jpeg(imagen, *, quality: int) -> bytes:
    salida = io.BytesIO()
    # Sin `exif=` ni `icc_profile=`: Pillow sólo escribe los metadatos que se le
    # pasan al guardar, así que la salida no lleva ni la ubicación ni la cámara.
    imagen.save(salida, format="JPEG", quality=quality, optimize=True, progressive=True)
    return salida.getvalue()


def normalize_image(data: bytes, *, max_dimension: int, jpeg_quality: int) -> Derivative:
    """JPEG orientado, sin EXIF y con el lado mayor limitado."""
    from PIL import Image, ImageOps

    imagen = _to_rgb(ImageOps.exif_transpose(_open_image(data)))
    imagen.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return Derivative(
        "normalized", _jpeg(imagen, quality=jpeg_quality), "image/jpeg", imagen.width, imagen.height
    )


def image_thumbnail(data: bytes) -> Derivative:
    from PIL import Image, ImageOps

    imagen = _to_rgb(ImageOps.exif_transpose(_open_image(data)))
    imagen.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
    return Derivative(
        "thumbnail", _jpeg(imagen, quality=80), "image/jpeg", imagen.width, imagen.height
    )


def pdf_thumbnail(data: bytes) -> Derivative:
    """La primera página, renderizada con PDFium."""
    import pypdfium2 as pdfium
    from PIL import Image

    documento = pdfium.PdfDocument(data)
    try:
        paginas = len(documento)
        pagina = documento[0]
        escala = min(THUMBNAIL_SIZE / max(pagina.get_width(), 1), 2.0)
        with _pixel_limit():
            imagen = pagina.render(scale=escala).to_pil()
        pagina.close()
    finally:
        documento.close()
    imagen = _to_rgb(imagen)
    imagen.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
    return Derivative(
        "thumbnail",
        _jpeg(imagen, quality=80),
        "image/jpeg",
        imagen.width,
        imagen.height,
        page_count=paginas,
    )


def build_derivatives(
    data: bytes, content_type: str, *, max_dimension: int, jpeg_quality: int
) -> list[Derivative]:
    """Los derivados de un documento **ya limpio**. Vacío si no aplica."""
    if content_type in IMAGE_TYPES:
        return [
            normalize_image(data, max_dimension=max_dimension, jpeg_quality=jpeg_quality),
            image_thumbnail(data),
        ]
    if content_type == PDF_TYPE:
        return [pdf_thumbnail(data)]
    return []
