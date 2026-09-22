"""
WP-6: qué es un archivo y qué se deriva de él, sin base de datos.

Lo que se congela:

* el tipo sale de los bytes, también para HEIC/HEIF/WEBP, y un tipo declarado
  que no coincide se rechaza;
* la versión normalizada de una foto está orientada, **no lleva EXIF** (ni la
  ubicación GPS) y respeta el límite de dimensiones;
* HEIC se convierte a JPEG; la transparencia no se vuelve negra;
* un PDF cifrado o con demasiadas páginas se rechaza; uno que el analizador no
  entiende no se rechaza por eso;
* la miniatura de un PDF es su primera página y sabe cuántas tiene;
* una bomba de descompresión no se descodifica.

Los fixtures se generan aquí con las mismas librerías, así que son archivos de
verdad y no cabeceras con relleno.
"""

from __future__ import annotations

import io

import pytest
from PIL import ExifTags, Image

from app.config import settings
from app.core.storage import base as storage_base
from app.core.storage import media


def _jpeg_de_telefono(ancho=1200, alto=800, orientacion=6) -> bytes:
    imagen = Image.new("RGB", (ancho, alto), (200, 30, 30))
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientacion
    exif[ExifTags.Base.Make] = "PhoneMaker"
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps[ExifTags.GPS.GPSLatitude] = (33.0, 57.0, 0.0)
    gps[ExifTags.GPS.GPSLongitudeRef] = "W"
    gps[ExifTags.GPS.GPSLongitude] = (83.0, 22.0, 0.0)
    salida = io.BytesIO()
    imagen.save(salida, format="JPEG", exif=exif)
    return salida.getvalue()


def _heic(ancho=640, alto=480) -> bytes:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    salida = io.BytesIO()
    Image.new("RGB", (ancho, alto), (20, 120, 200)).save(salida, format="HEIF", quality=60)
    return salida.getvalue()


def _webp() -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 200, 10)).save(salida, format="WEBP")
    return salida.getvalue()


def _png_transparente() -> bytes:
    salida = io.BytesIO()
    Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(salida, format="PNG")
    return salida.getvalue()


def _pdf(paginas: int, *, clave: str | None = None) -> bytes:
    from pypdf import PdfWriter

    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=612, height=792)
    if clave:
        escritor.encrypt(clave)
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


# ── Tipo ────────────────────────────────────────────────────────────────────────


def test_each_accepted_type_is_recognised_by_its_bytes():
    assert media.sniff_content_type(_jpeg_de_telefono()) == "image/jpeg"
    assert media.sniff_content_type(_png_transparente()) == "image/png"
    assert media.sniff_content_type(_pdf(1)) == "application/pdf"
    assert media.sniff_content_type(_webp()) == "image/webp"
    assert media.sniff_content_type(_heic()) == "image/heic"
    heif_generico = b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00mif1miaf"
    assert media.sniff_content_type(heif_generico) == "image/heif"
    assert media.sniff_content_type(b"MZ\x90\x00 an executable") is None


def test_a_generic_declared_type_is_resolved_from_the_bytes():
    assert (
        media.resolve_content_type(data=_heic(), declared="application/octet-stream")
        == "image/heic"
    )
    with pytest.raises(media.MediaRejected, match="could not be recognised"):
        media.resolve_content_type(data=b"MZ\x90\x00", declared="")


def test_a_declared_type_must_match_the_bytes():
    with pytest.raises(media.MediaRejected, match="not a valid image/png"):
        media.resolve_content_type(data=_jpeg_de_telefono(), declared="image/png")
    # HEIC y HEIF son el mismo contenedor con otra etiqueta.
    assert media.resolve_content_type(data=_heic(), declared="image/heif") == "image/heic"


def test_upload_validation_follows_the_policy_and_stores_the_real_type(monkeypatch):
    monkeypatch.setattr(
        settings, "UPLOAD_ALLOWED_TYPES", "image/jpeg,image/heic,application/pdf"
    )
    assert (
        storage_base.validate_upload(data=_heic(), content_type="application/octet-stream")
        == "image/heic"
    )
    with pytest.raises(storage_base.UnsupportedFileType, match="image/webp is not an accepted"):
        storage_base.validate_upload(data=_webp(), content_type="application/octet-stream")
    with pytest.raises(storage_base.UnsupportedFileType, match="Password-protected"):
        storage_base.validate_upload(data=_pdf(1, clave="secreto"), content_type="application/pdf")


# ── Fotos ───────────────────────────────────────────────────────────────────────


def test_a_phone_photo_is_oriented_stripped_of_exif_and_bounded():
    derivado = media.normalize_image(
        _jpeg_de_telefono(1200, 800, orientacion=6), max_dimension=800, jpeg_quality=85
    )

    imagen = Image.open(io.BytesIO(derivado.data))
    assert derivado.content_type == "image/jpeg" and imagen.format == "JPEG"
    # Orientación 6 = girada 90°: la foto apaisada se ve vertical.
    assert (imagen.width, imagen.height) == (533, 800)
    assert (derivado.width, derivado.height) == (533, 800)
    exif = imagen.getexif()
    assert len(exif) == 0
    assert not exif.get_ifd(ExifTags.IFD.GPSInfo)


def test_an_iphone_heic_photo_becomes_a_viewable_jpeg():
    derivados = media.build_derivatives(_heic(), "image/heic", max_dimension=3000, jpeg_quality=85)

    tipos = {d.kind: d for d in derivados}
    assert set(tipos) == {"normalized", "thumbnail"}
    assert Image.open(io.BytesIO(tipos["normalized"].data)).format == "JPEG"
    assert max(tipos["thumbnail"].width, tipos["thumbnail"].height) <= media.THUMBNAIL_SIZE


def test_transparency_becomes_white_not_black():
    derivado = media.normalize_image(_png_transparente(), max_dimension=800, jpeg_quality=90)
    r, g, b = Image.open(io.BytesIO(derivado.data)).getpixel((20, 20))
    assert min(r, g, b) > 240


def test_a_decompression_bomb_is_not_decoded(monkeypatch):
    monkeypatch.setattr(media, "MAX_PIXELS", 1_000)
    with pytest.raises((Image.DecompressionBombError, Image.DecompressionBombWarning)):
        media.normalize_image(_webp(), max_dimension=800, jpeg_quality=85)


# ── PDF ─────────────────────────────────────────────────────────────────────────


def test_an_encrypted_pdf_is_rejected():
    with pytest.raises(media.MediaRejected, match="Password-protected"):
        media.inspect_pdf(_pdf(1, clave="secreto"), max_pages=20)


def test_a_pdf_with_only_editing_restrictions_is_accepted():
    """Un formulario estatal descargado: contraseña de propietario, se abre sin contraseña."""
    from pypdf import PdfWriter

    escritor = PdfWriter()
    escritor.add_blank_page(width=612, height=792)
    escritor.add_blank_page(width=612, height=792)
    escritor.encrypt(user_password="", owner_password="restricciones")
    salida = io.BytesIO()
    escritor.write(salida)

    assert media.inspect_pdf(salida.getvalue(), max_pages=20) == 2


def test_the_pdf_page_limit_is_enforced():
    assert media.inspect_pdf(_pdf(3), max_pages=5) == 3
    with pytest.raises(media.MediaRejected, match="3 pages; the limit is 2"):
        media.inspect_pdf(_pdf(3), max_pages=2)


def test_a_pdf_the_parser_cannot_read_is_not_rejected_for_that():
    assert media.inspect_pdf(b"%PDF-1.7\nnot really a pdf", max_pages=20) is None


def test_a_pdf_thumbnail_is_its_first_page_and_knows_the_page_count():
    derivado = media.pdf_thumbnail(_pdf(2))

    assert derivado.kind == "thumbnail" and derivado.page_count == 2
    imagen = Image.open(io.BytesIO(derivado.data))
    assert imagen.format == "JPEG" and max(imagen.size) <= media.THUMBNAIL_SIZE
