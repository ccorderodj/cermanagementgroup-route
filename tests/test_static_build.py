"""Bundle versionado: una pestaña recibe el build nuevo sin borrar la caché.

En producción el buildpack deja los archivos con fecha de 1980 y el bundle se
llama siempre `main.js`: sin estas cabeceras, el navegador lo daba por fresco
durante años (ver `app/core/build.py`).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.build import CABECERA_BUILD, INMUTABLE, REVALIDAR, StaticConBuild, build_id

_1980 = 315532801


def _bundle(tmp_path, main: bytes, css: bytes = b"body{}"):
    js = tmp_path / "javascript"
    (js / "css").mkdir(parents=True, exist_ok=True)
    (js / "main.js").write_bytes(main)
    (js / "css" / "main.css").write_bytes(css)
    (js / "140.0c734b9af5e82ad1b02f.js").write_bytes(b"chunk")
    for ruta in js.rglob("*.*"):
        os.utime(ruta, (_1980, _1980))
    return js


def _cliente(tmp_path, js):
    app = FastAPI()
    app.mount("/static", StaticConBuild(directory=tmp_path, bundle=js), "static")
    return TestClient(app)


def test_mismo_tamano_y_misma_fecha_distinto_build(tmp_path):
    a = build_id(_bundle(tmp_path / "a", b"console.log(1)"))
    b = build_id(_bundle(tmp_path / "b", b"console.log(2)"))
    assert len(a) == 12 and a != b, "el ETag de Starlette sería el mismo; el build no"


def test_entradas_se_revalidan_y_chunks_con_hash_son_inmutables(tmp_path):
    js = _bundle(tmp_path, b"console.log(1)")
    cliente = _cliente(tmp_path, js)

    main = cliente.get("/static/javascript/main.js")
    css = cliente.get("/static/javascript/css/main.css")
    chunk = cliente.get("/static/javascript/140.0c734b9af5e82ad1b02f.js")
    assert main.headers["cache-control"] == REVALIDAR == css.headers["cache-control"]
    assert chunk.headers["cache-control"] == INMUTABLE
    assert main.headers[CABECERA_BUILD.lower()] == build_id(js)


def test_el_head_de_la_sonda_trae_el_build_y_un_304_tambien(tmp_path):
    js = _bundle(tmp_path, b"console.log(1)")
    cliente = _cliente(tmp_path, js)

    sonda = cliente.head("/static/javascript/main.js", params={"check": 1})
    assert sonda.status_code == 200 and sonda.headers[CABECERA_BUILD.lower()] == build_id(js)
    no_cambio = cliente.get("/static/javascript/main.js", headers={"If-None-Match": sonda.headers["etag"]})
    assert no_cambio.status_code == 304 and no_cambio.headers["cache-control"] == REVALIDAR


def test_el_build_cambia_cuando_cambia_el_bundle(tmp_path):
    js = _bundle(tmp_path, b"console.log(1)")
    antes = build_id(js)
    (js / "main.js").write_bytes(b"console.log(2)")
    assert build_id(js) != antes


def test_sin_bundle_no_falla(tmp_path):
    assert len(build_id(tmp_path / "vacio")) == 12
