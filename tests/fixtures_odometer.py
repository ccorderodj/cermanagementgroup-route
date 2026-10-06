"""
Odómetros sintéticos que reproducen las características de las fotos de campo.

Por qué no se guardan las fotos de CER
--------------------------------------
Las imágenes reales llevan salpicadero, y a veces matrícula y kilometraje de un
vehículo concreto. §6 de la instrucción pide explícitamente no commitear
evidencia de campo que CER no autorizó a guardar, así que lo que vive aquí son
**reconstrucciones** con las propiedades técnicas que hacen difícil el caso, no
las fotografías.

Lo que se reproduce, medido sobre la referencia de CER
-------------------------------------------------------
* 185 × 72 px — resolución baja frente a una captura de teléfono moderna;
* dígitos **claros sobre fondo oscuro**, que es lo contrario del texto impreso
  sobre papel con el que Tesseract se entrenó;
* rodillos mecánicos con costuras verticales entre ruedas;
* desenfoque suave y compresión.

Qué no reproduce, y por eso no sustituye a la validación de campo
------------------------------------------------------------------
El reflejo del cristal, el ángulo real, la fuente concreta del fabricante y el
ruido del sensor. Un sintético limpio pasa pruebas que una foto real no pasa —
ya ocurrió en este checkpoint— así que estos fixtures sirven para fijar
regresión, no para declarar que el motor lee salpicaderos.
"""

from __future__ import annotations

import io

#: La lectura que enseña la referencia de CER.
LECTURA_DE_REFERENCIA = "151517"


def odometro_rodillo(
    texto: str = LECTURA_DE_REFERENCIA,
    *,
    ancho: int = 185,
    alto: int = 72,
    desenfoque: float = 0.5,
    formato: str = "PNG",
) -> bytes:
    """Un recorte ajustado de odómetro de rodillo, claro sobre oscuro."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    img = Image.new("RGB", (ancho, alto), (16, 18, 22))
    d = ImageDraw.Draw(img)
    paso = ancho / len(texto)
    fuente = ImageFont.load_default(size=int(alto * 0.68))

    for i, ch in enumerate(texto):
        # Cada rueda es su propio cilindro, con su costura. Las líneas
        # verticales entre dígitos son parte de lo que confunde al motor.
        d.rectangle([paso * i, 0, paso * (i + 1) - 1, alto], fill=(26, 29, 35))
        d.text((paso * i + paso * 0.2, alto * 0.14), ch,
               fill=(224, 231, 238), font=fuente)
        d.line([(paso * (i + 1), 0), (paso * (i + 1), alto)],
               fill=(6, 7, 9), width=1)

    if desenfoque:
        img = img.filter(ImageFilter.GaussianBlur(desenfoque))

    salida = io.BytesIO()
    if formato == "JPEG":
        img.save(salida, format="JPEG", quality=72)
    else:
        img.save(salida, format=formato)
    return salida.getvalue()


def salpicadero(
    *,
    odometro: str | None = LECTURA_DE_REFERENCIA,
    parcial: str | None = "241.6",
    velocidad: str | None = "60",
    ancho: int = 1400,
    alto: int = 1050,
    fraccion_odometro: float = 0.18,
    desenfoque: float = 0.0,
) -> bytes:
    """Un salpicadero completo con el odómetro ocupando poco del encuadre.

    `odometro=None` produce el caso de falso positivo: el odómetro no se lee y
    sólo queda visible un número corto de otro indicador, que **no** debe
    convertirse en una sugerencia.
    """
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    img = Image.new("RGB", (ancho, alto), (62, 64, 72))
    d = ImageDraw.Draw(img)
    alto_digito = int(ancho * fraccion_odometro / 6 * 1.6)

    if odometro:
        caja_x = ancho * 0.30
        caja_y = alto * 0.42
        d.rounded_rectangle(
            [caja_x, caja_y,
             caja_x + ancho * fraccion_odometro * 1.2, caja_y + alto_digito * 1.7],
            radius=10, fill=(22, 24, 29),
        )
        d.text((caja_x + 8, caja_y + 6), odometro, fill=(228, 234, 240),
               font=ImageFont.load_default(size=alto_digito))
        if parcial:
            d.text((caja_x + 8, caja_y + alto_digito * 1.05), parcial,
                   fill=(168, 172, 178),
                   font=ImageFont.load_default(size=int(alto_digito * 0.55)))

    if velocidad:
        d.text((ancho * 0.07, alto * 0.45), velocidad, fill=(230, 232, 236),
               font=ImageFont.load_default(size=int(alto_digito * 1.4)))

    if desenfoque:
        img = img.filter(ImageFilter.GaussianBlur(desenfoque))

    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=84)
    return salida.getvalue()
