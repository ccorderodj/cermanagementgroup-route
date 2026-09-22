"""
Utilidades compartidas del backend.

Se retiraron dos que no tenian ningun consumidor:

* `csv_line` (`util.py`) — documentada en `backend-utils-reference.md` como el
  helper estandar para escribir CSV, sin que ningun modulo lo usara.
* `generate_temp_password` — ademas duplicaba `bootstrap.generate_password`.

Que un helper este documentado no lo hace usado: la documentacion decia que
existia y era correcta, pero describia una convencion que nadie seguia porque
no habia nada que exportar a CSV (AUD-BE-019).
"""
