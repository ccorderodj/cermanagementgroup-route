"""Las páginas piden el bundle del build vigente y se revalidan siempre."""

from __future__ import annotations

import re

import pytest

from app.core.build import build_id

pytestmark = pytest.mark.integration


async def test_la_pagina_versiona_el_bundle_y_no_se_cachea(seeded, alpha_client):
    respuesta = await alpha_client.get("/login")
    html = respuesta.text
    build = build_id()

    assert respuesta.headers["cache-control"] == "no-cache"
    assert f'<meta name="cer-build" content="{build}">' in html
    assert f'/static/javascript/main.js?v={build}"' in html
    assert f'/static/javascript/css/main.css?v={build}"' in html
    assert not re.search(r'/static/javascript/main\.js"', html), "ninguna URL del bundle sin versión"


async def test_el_bundle_lleva_el_build_y_se_revalida(seeded, alpha_client):
    respuesta = await alpha_client.get("/static/javascript/main.js?check=1")
    assert respuesta.status_code == 200
    assert respuesta.headers["x-cer-build"] == build_id()
    assert respuesta.headers["cache-control"] == "no-cache"
