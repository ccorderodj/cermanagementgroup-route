"""
Identidad del proyecto: nombre, marca, entorno y página de inicio.

Una aplicación construida sobre esta base se llama distinto sin tocar
plantillas ni componentes: declara `APP_*` en el entorno (ver `.env.example`).
Esto es lo único que las plantillas Jinja y el cookie `app_data` leen para
pintar la marca, así que las dos superficies no pueden contradecirse.
"""

from __future__ import annotations

from app.config import settings


def app_identity() -> dict[str, str]:
    return {
        "app_name": settings.APP_NAME,
        "app_title": settings.APP_TITLE,
        "brand_label": settings.APP_BRAND_LABEL,
        "brand_tagline": settings.APP_BRAND_TAGLINE,
        "logo_path": settings.APP_LOGO_PATH,
        "icon_path": settings.APP_ICON_PATH,
        "environment_label": settings.environment_label,
        "default_path": settings.DEFAULT_AUTHENTICATED_PATH,
    }
