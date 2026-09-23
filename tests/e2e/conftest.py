"""
Fixtures para los tests de navegador.

`seeded` vive en `tests/integration/conftest.py` y pytest solo la ofrece a los
tests de ese directorio. Reexportarla aquí evita duplicar la siembra: un segundo
sembrado divergiría del primero en cuanto uno de los dos cambiara, y los tests
de navegador estarían comprobando un tenant que no es el que comprueba el resto
de la suite.
"""

from tests.integration.conftest import seeded  # noqa: F401
