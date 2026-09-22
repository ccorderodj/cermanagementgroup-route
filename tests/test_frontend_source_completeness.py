"""
Que el árbol del repositorio baste para compilar.

Por qué existe este test
------------------------
El frontend compiló durante toda la fase 12 en la máquina donde se escribió, y
falló en un checkout limpio con `Module not found: '../lib/estados'`. El módulo
existía en disco, pero `.gitignore` traía del bloque de empaquetado de Python
una regla `lib/` **sin anclar**, que no significa «el directorio lib del
empaquetado» sino *cualquier* directorio llamado `lib` en cualquier nivel. El
frontend organiza sus módulos justo así.

Lo que hace peligroso a este fallo es que no deja rastro: un fichero ignorado
no aparece en `git status`, no rompe la compilación local —el fichero está ahí—
y no lanza ningún aviso. Sólo se manifiesta cuando otra persona clona
(AUD-GIT-001).

Estos dos tests cierran la clase entera, no el caso concreto:

- el primero, porque un import relativo que no resuelve **contra ficheros
  versionados** es exactamente el síntoma que vio César;
- el segundo, porque la causa fue un `.gitignore` tragándose fuente, y eso puede
  repetirse con `dist/`, `build/` o cualquier otra regla sin anclar.

No necesita base de datos ni node: es lectura del árbol y consulta a git.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "app" / "components" / "react"

#: Extensiones que webpack resuelve cuando el import no las escribe.
EXTENSIONES = (".ts", ".tsx", ".js", ".jsx", ".d.ts")

#: `import ... from '../algo'` y `export ... from './otro'`, sólo relativos:
#: los alias (`@/…`) los resuelve tsconfig y los cubre el typecheck.
_IMPORT_RELATIVO = re.compile(
    r"""(?:import|export)\s
        (?:[^'"]*?\sfrom\s)?      # `import x from` o `import 'efecto'`
        ['"](\.{1,2}/[^'"]+)['"]""",
    re.X,
)


def _versionados() -> set[Path]:
    """Los ficheros que git tiene. **La pregunta no es si el fichero existe en
    disco, sino si viaja en el repositorio**, que es justo donde falló.

    Fuera de un repositorio git (un checkout extraído de un archivo, que ya
    contiene sólo lo versionado) se usan los ficheros del disco."""
    try:
        salida = subprocess.run(
            ["git", "ls-files", "-z", "--", "app/components/react"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout
        versionados = {REPO_ROOT / p for p in salida.split("\0") if p}
        if versionados:
            return versionados
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return {
        p.resolve() for p in FRONTEND.rglob("*")
        if p.is_file() and "node_modules" not in p.parts
    }


def _resuelve(origen: Path, destino_rel: str, versionados: set[Path]) -> bool:
    base = (origen.parent / destino_rel).resolve()
    candidatos = [base, *(base.with_suffix(ext) for ext in EXTENSIONES)]
    candidatos += [base.parent / f"{base.name}{ext}" for ext in EXTENSIONES]
    candidatos += [base / f"index{ext}" for ext in EXTENSIONES]
    return any(c in versionados for c in candidatos)


def test_every_relative_import_resolves_to_a_versioned_file():
    """Un import relativo tiene que llevar a un fichero que git conozca.

    Si resuelve sólo en el disco de quien lo escribió, compila aquí y rompe en
    todas las demás máquinas.
    """
    versionados = _versionados()
    fuentes = [p for p in versionados if p.suffix in (".ts", ".tsx")]
    assert fuentes, "no se encontró fuente de frontend versionada"

    rotos: list[str] = []
    for archivo in fuentes:
        try:
            texto = archivo.read_text(encoding="utf-8")
        except OSError:
            continue
        for destino in _IMPORT_RELATIVO.findall(texto):
            if not _resuelve(archivo, destino, versionados):
                rotos.append(f"{archivo.relative_to(REPO_ROOT)} -> {destino}")

    assert not rotos, (
        "Imports relativos que no resuelven contra ficheros versionados.\n"
        "El módulo puede existir en tu disco y aun así no estar en el "
        "repositorio: comprueba `git check-ignore -v <ruta>`.\n  "
        + "\n  ".join(sorted(rotos))
    )


def test_no_frontend_source_file_is_git_ignored():
    """Ninguna regla de `.gitignore` puede tragarse fuente del frontend.

    Es la causa raíz, no el síntoma: mientras una regla sin anclar pueda
    ocultar un módulo, el fallo vuelve con otro nombre.
    """
    candidatos = [
        p for p in FRONTEND.rglob("*")
        if p.is_file() and p.suffix in (".ts", ".tsx", ".scss", ".css")
        and "node_modules" not in p.parts
    ]
    assert candidatos, "no se encontró fuente de frontend en disco"

    comprobacion = subprocess.run(
        ["git", "check-ignore", "--stdin", "-v"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        input="\n".join(str(p) for p in candidatos),
    )
    ignorados = [l for l in comprobacion.stdout.splitlines() if l.strip()]

    assert not ignorados, (
        "Hay fuente de frontend que `.gitignore` está ocultando. No aparece en "
        "`git status` y compila en local, pero no viaja en el repositorio:\n  "
        + "\n  ".join(ignorados)
    )
