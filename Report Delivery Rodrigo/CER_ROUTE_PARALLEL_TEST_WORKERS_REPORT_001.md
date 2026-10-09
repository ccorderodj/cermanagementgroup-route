# CER Route · La suite de pruebas en tres workers

**Reporte 001** · 8–9 de octubre de 2026
**Alcance:** ejecutar la suite en paralelo. Sólo infraestructura de pruebas:
ningún cambio en `app/`, en permisos ni en aserciones.
**Rama:** `chore/parallel-test-workers`

---

## Status

`COMPLETED WITH PENDING ITEMS`

La configuración está implementada y validada sobre la suite completa. Quedan
dos hallazgos ajenos a este cambio que necesitan decisión (§5).

---

## 1 · Resultado

| | Antes (1 worker) | Ahora (3 workers) |
|---|---|---|
| Sin navegador (1089 tests) | **17 min 19 s** | **10 min 6 s** · 1,7× |
| Suite completa (1252 tests) | no medida; ≈ 70 min estimados | **58 min 15 s** |
| Resultado | 1073 PASS · 1 fallo | **idéntico** |

La ganancia está casi entera en la parte sin navegador. En la suite completa la
duración la marcan las 163 pruebas de navegador, que siguen en serie (§3).

---

## 2 · Qué cambió

| Archivo | Cambio |
|---|---|
| `pyproject.toml` | `pytest-xdist` en desarrollo; `addopts` con `-n 3 --dist loadgroup` |
| `uv.lock` | `pytest-xdist 3.8.0`, `execnet 2.1.2` |
| `tests/conftest.py` | una base por worker; las pruebas de navegador, a un solo worker |

### 2.1 · Una base por worker — el requisito

Los workers no pueden compartir base: `seeded` vacía **todas** las tablas al
empezar cada test y vuelve a sembrar `alpha` y `beta` con nombres fijos, y la
sesión hace `DROP SCHEMA public`. Dos workers se borrarían los datos a mitad de
test.

Cada worker usa ahora la base de `TEST_DATABASE_URL` con su nombre detrás
(`cer_time_test_gw0`, `_gw1`, `_gw2`) y la crea si no existe. Se fija en
`settings` y en `os.environ` antes de que nada importe `app.database`, de modo
que la heredan Alembic, el `uvicorn` de navegador y las pruebas de migración
sin tocar ninguno.

**Requisito nuevo:** el rol de pruebas necesita `CREATEDB` la primera vez. En
local lo tiene.

### 2.2 · Las pruebas de navegador, en un solo worker

Medido con las 163 repartidas entre tres workers:

```
73 min 12 s · 155 PASS · 8 fallos      (en serie: ≈ 34 min estimados)
```

**Más lento y con dos fallos más**, que repetidos con un solo worker
**pasan** (`CONFIRMED`): `rte08 … sin_la_capacidad` y `rte07 … freshness`.
Cada test arranca su `uvicorn` y su Edge, y tres arranques a la vez en dos
núcleos físicos se estorban.

Se agrupan con `xdist_group("browser")` y `--dist loadgroup`: van todas a un
worker mientras los otros dos hacen integración.

**Un defecto propio, corregido antes de entregar:** la primera versión del hook
corría *después* del de `xdist`, y las pruebas de navegador se repartían igual
(`gw0` y `gw2`). Con `tryfirst=True` quedaron las seis de la prueba en `gw0`.

### 2.3 · `-n 0`

Vuelve a un proceso sobre la base compartida, como antes. Es lo que hace falta
para depurar con `pdb`.

---

## 3 · Validación

### 3.1 · Sin navegador · 3 workers · exit 1

```
1073 PASS · 1 FAILED (test_provisioning_alignment, preexistente) · 0 errores · 15 skipped
10 min 6 s
```

### 3.2 · Suite completa, configuración final · exit 1

```
1228 PASS · 9 FAILED · 0 errores · 15 skipped · 58 min 15 s
sin caídas de worker · 0 procesos huérfanos al terminar
```

Los 9 fallos son **exactamente** los conocidos antes de lanzarla:

| # | Fallo | Origen |
|---|---|---|
| 1 | `test_provisioning_alignment` · 14 capacidades frente a 12 | preexistente; espera decisión de CER |
| 2–3 | E2E de R-1, escritorio y móvil | §5.2 · depende de la hora |
| 4 | `rte04 … rejected_end_work_does_not_come_back` | §5.1 · ya falla en `dev` |
| 5 | `rte06 … location_captured_offline_is_not_lost` | §5.1 · ya falla en `dev` |
| 6–9 | `rte06 recovery_accuracy` G1, G2, G3, G5 | §5.1 · ya falla en `dev` |

### 3.3 · Memoria y CPU durante la ejecución

| | |
|---|---|
| Suite completa en memoria | ≈ 1,4 GB (workers 0,7 · `uvicorn` + Edge 0,3 · PostgreSQL 0,34) |
| RAM libre | 11,9 GB de 31,8 |
| CPU del test de navegador en curso | ≈ 0 %: espera, no calcula |

**La memoria no limita; la CPU sí** (2 núcleos físicos, PostgreSQL en la misma
máquina).

### 3.4 · Un error mío durante la validación · `CONFIRMED`

Con la primera regresión en marcha hice `git stash` para comparar el lint, y los
cambios desaparecieron del disco unos dos segundos. No se puede descartar que un
worker los leyera en ese instante. Por eso la suite completa (§3.2) se ejecutó
después, sin tocar el árbol, y su resultado coincide.

### 3.5 · Lint

`black` pasa sobre el código añadido. `black --check` e `isort` ya fallaban en
`tests/conftest.py` antes del cambio, por una línea en blanco ajena; no se toca.

---

## 4 · Lo que no se cambió

Ningún archivo de `app/`. Ninguna aserción, ningún test, ningún permiso. Los
tests siguen sembrando con los mismos nombres: cada base es independiente.

---

## 5 · Hallazgos incidentales

### 5.1 · Seis pruebas de navegador ya fallan en `dev` · `CONFIRMED`, origen `UNVERIFIED`

Fallan igual con `xdist` desactivado del todo (`-p no:xdist`), así que no las
causa este cambio.

| Prueba | Síntoma |
|---|---|
| `rte04 … rejected_end_work_does_not_come_back` | tras un End Work rechazado no aparece `What's next?` |
| `rte06 … location_captured_offline_is_not_lost` | coordenada `33.9519` donde espera `43.7311` |
| `rte06 recovery_accuracy` G1, G2, G3, G5 | la ubicación recuperada no se acepta (`0 == 1`) |

Todas tocan el cierre de jornada y la ubicación sin conexión: los flujos que
cambiaron el odómetro de cierre y la puerta de ubicación (RTE10-A02). **Es una
hipótesis, no una causa.** Las entregas de esos flujos ejecutaron sus pruebas
de navegador dirigidas, no la batería completa; no consta una ejecución completa
desde entonces, y eso explicaría que no se hubieran visto (`LIKELY`).

**Importa:** son pruebas de durabilidad de datos de campo. Merecen diagnóstico
propio antes de certificar nada que toque esos flujos.

### 5.2 · La E2E de R-1 depende de la hora · `CONFIRMED`, error mío

Fija la jornada con `CURRENT_DATE` de PostgreSQL, que está en
`America/Guatemala`, y la pantalla abre «hoy» en UTC cuando no hay desfase
registrado. **Entre las 18:00 y las 24:00 hora local las dos fechas difieren y la
prueba falla.** Al entregar R-1 la ejecuté fuera de esa franja.

El producto no cambia por esto. Es una línea en la prueba. **No se corrige
aquí**: el Product Owner pidió no tocar R-1 sin autorización. Afecta también a
la evidencia de R-1 001 y del reporte de certificación: aquellas ejecuciones
fueron válidas, pero la prueba no es repetible a cualquier hora.

---

## 6 · Estimación

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Análisis de capacidad y medición | — | — | 0,8 |
| Base por worker y agrupamiento | ~85 LoC | determinista | 0,6 |
| Validación: 3 regresiones, repeticiones, diagnóstico de fallos | ≈ 2 h 40 min de máquina | navegador | 2,8 |
| Reporte y entrega | — | — | 0,6 |
| **Total** | | | **≈ 4,8 h** |

Estimado antes: 2–3 h. Volvió a irse en la verificación —la batería de navegador
completa dos veces, 131 minutos entre ambas— y no en el cambio, que es el mismo
sesgo de H-2 y R-1.

---

## 7 · Git

| | |
|---|---|
| Rama | `chore/parallel-test-workers` |
| Base | `dev` en `103617c` |
| Fusionado | **No** |

---

## 8 · Siguiente paso, sin empezarlo

1. **Diagnosticar los seis fallos de §5.1**: son de durabilidad de campo.
2. **Autorizar la corrección de §5.2**, una línea en la prueba de R-1.
3. Si se quiere ganar en la parte de navegador: probar **2** workers de
   navegador, sabiendo que la saturación está en los arranques. No se propone
   sin medir.
