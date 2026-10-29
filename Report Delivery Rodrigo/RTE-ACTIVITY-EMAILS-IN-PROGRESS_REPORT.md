# RTE · Correos de actividad: actividades en curso

**Fecha:** 2026-10-29 · **Rama:** `fix/activity-emails-in-progress` · **MR:** !__MR__
**Instrucción:** `_cer_delivery/RTE_ACTIVITY_EMAILS_IN_PROGRESS_PROMPT.md`
**Estado:** COMPLETED WITH PENDING ITEMS (validado en local; sin desplegar; decisión de producto abierta, ver riesgo 1)

## Qué cambia

Los cuatro correos (motivacional de mediodía, fin de día del usuario,
estratégico de mediodía y de las 19:00) ya calculaban la foto **al corte**.
Lo que faltaba:

1. **Conteos mezclados.** En el estratégico, una actividad abierta al corte
   contaba en «Eventos» como si estuviera hecha. Ahora la columna dice
   `2 (+1)`: 2 finalizadas, 1 iniciada sin finalizar. Una leyenda explica el
   `(+N)` debajo de la tabla. Las abiertas no suman tiempo.
2. **Estado falso.** Una actividad abierta al corte salía siempre «En curso»,
   aunque su jornada hubiera cerrado antes del corte (defecto CONFIRMED,
   `_al_corte` forzaba `session_ended=False`). Ahora sale «En curso» solo si
   **su** jornada seguía abierta en ese instante. Si no, sale «Sin cierre
   registrado», el estado que ya existía y que equivale a *Started / Not Completed*.
3. **El motivacional las omitía.** Ahora añade «- N actividad(es) en curso.» o
   «- N actividad(es) iniciada(s) sin finalizar.», decidido por la jornada de
   cada actividad.
4. **Snapshot y resumen del equipo:** «Actividades registradas: N» pasa a
   «Actividades finalizadas: N | Iniciadas sin finalizar: M».

## Archivos

| Archivo | Por qué |
|---|---|
| `app/routers_api/activityemails/strategic.py` | `Fila.abiertas`; `eventos` = solo finalizadas; columna `N (+M)` y leyenda; `_cierres()` da la hora real de cierre de cada jornada; `_al_corte` decide «En curso» o «Sin cierre registrado» con ella; vista previa ficticia con un `0 (+1)` |
| `app/routers_api/activityemails/real_reports.py` | `_abiertas()` y `_lineas_de_abiertas()`: líneas aparte en los motivacionales; la semana sigue contando solo finalizadas |
| `tests/integration/test_mail_close_cp1.py` | `_al_corte` recibe `cierres`; se añade el caso de jornada cerrada antes del corte |
| `tests/integration/test_activity_emails_in_progress.py` | Nuevo: los criterios de aceptación (8 tests) |

Sin migraciones, sin frontend, sin endpoints nuevos. No se tocan el motor de
actividades, GPS, millaje, routing, horarios, disparadores, RBAC, tenant,
envío, reenvío, idempotencia ni auditoría.

## Expected vs Implemented

| Criterio | Implementado | Evidencia |
|---|---|---|
| 11:40–12:15: a las 12:00 *In Progress*, al cierre *Completed* | Mediodía: «En curso», `0 (+1)`, sin fin ni duración. Cierre: «Finalizada», 35m, una sola fila | `test_1140_a_1215_…` PASS |
| Iniciada después de las 12:00 no aparece, aunque se genere tarde | Excluida (el corte es fijo; reenviar usa el mismo corte) | `test_iniciada_despues_del_corte_…` PASS |
| Abierta a las 19:00 con jornada abierta: *In Progress* | «En curso», `0 (+1)` | `test_abierta_a_las_19_…` PASS |
| Jornada cerrada sin finalizar: *Started / Not Completed* | «Sin cierre registrado», sin fin ni duración | `test_jornada_cerrada_…` PASS; `test_al_corte_…` PASS |
| Completadas sin cambios, sin duplicados | Igual que antes; los tests existentes de cp1/cp2/entrega pasan | Lote de correo |
| Motivacional: abiertas aparte, por la jornada de cada una | Líneas «en curso» y «sin finalizar», separadas | 3 tests `test_motivacional_…` PASS + `test_sin_ninguna_finalizada_…` PASS |
| Vista previa, envío manual y reenvío | Usan el mismo constructor (`delivery.evaluar` → `real_reports`) | Tests de vista previa y reenvío existentes PASS |
| Permisos y tenant | Sin cambios | `test_permission_catalog`, `test_public_surface`, alcance cp1 PASS |

## Validación

| Comprobación | Resultado |
|---|---|
| `uv run python -c "import app.main"` | OK |
| Tests nuevos (`test_activity_emails_in_progress.py`) | 8/8 PASS |
| Lote de correo + permisos + superficie pública (12 archivos), con el código final | 132/132 PASS, exit 0, 183 s |
| Regresión completa (local, `-n 3`) | 1755 passed, 1 failed, 1 error, 15 skipped · 1 h 48 min. **F**: `test_provisioning_alignment` (16 vs 12 capacidades de `route_admin`), fallo previo conocido y no relacionado. **E**: `test_activity_explorer::test_el_numero_de_consultas…`, `fixture 'caplog' not found`, causado por el flag `-p no:logging` con el que la lancé (CONFIRMED); relanzado sin el flag: 1/1 PASS |
| flake8 en los archivos tocados | 0 avisos nuevos (los de `content.py`, `delivery.py` y `service.py` ya existían) |
| `npm run check` | NOT APPLICABLE (sin cambios de frontend) |
| Migraciones | NOT APPLICABLE |
| Entorno compartido (DO) | NOT RUN: el cambio es local hasta que se fusione y despliegue |

## Riesgos y decisiones

1. **La regla de envío motivacional no cambia.** Sin ninguna actividad
   finalizada no hay correo, aunque haya una en curso (es el caso de Xochilt).
   Cambiarlo es decisión de producto; el código lo deja explícito y un test lo
   fija.
2. **«Sin cierre registrado» no es alcanzable hoy por la app.** End Work
   rechaza cerrar con una actividad sin resolver (`has_unresolved_work`).
   Solo aparece con datos anteriores a esa guarda o corregidos a mano. Se
   reutiliza la etiqueta existente en vez de crear una nueva.
3. **Cancelaciones:** una actividad «left» (abandonada con resultado) tiene
   hora de fin y sigue contando como finalizada, igual que antes.
4. **Cambio de texto visible:** «Actividades registradas» pasa a «Actividades
   finalizadas | Iniciadas sin finalizar». Quien compare correos antiguos y
   nuevos verá el cambio.
5. **Incidente propio durante la validación:** con la regresión en curso hice
   `git stash` / `stash pop` unos segundos para comparar avisos de lint. El
   impacto probable es nulo (LIKELY: los workers ya habían cargado los
   módulos). Además, durante la regresión refiné el motivacional (decidir por la
   jornada de **cada** actividad, con un test del caso mixto). Por eso el lote de
   correo se volvió a ejecutar después con el código final: 132/132.

## Estimación

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Lógica de corte y conteos | Hecho | 110 LoC (`git diff --stat`) | Backend | 0,6 |
| Tests de aceptación | Hecho | 195 LoC | Backend/integración | 1,0 |
| Validación y entrega | Hecho | regresión de 1 h 48 min de reloj | — | 0,4 |
| **Total** | | | | **≈2,0 h (+10% → 2,2 h)** |

Restante para esta entrega: 0 h de ingeniería. Queda la revisión, la fusión y
el despliegue.

## Pendientes operativos

- Revisar y fusionar el MR; desplegar en DO. Hasta entonces producción manda
  los correos con el formato anterior.
- Decisión de producto sobre el punto 1 de los riesgos.
