# {{PROYECTO}} — <Título de la entrega>

**Fecha:** AAAA-MM-DD · **Rama:** `<rama>` → `{{RAMA_BASE}}` · **MR:** !NN · **Entorno de la evidencia:** local / compartido
**Estado:** `COMPLETED` / `COMPLETED WITH PENDING ITEMS` / `BLOCKED`

<!-- Nombre del archivo: <CODIGO>_<TEMA>_REPORT.md en {{CARPETA_REPORTES}}.
     Si la instrucción reserva una numeración, respetarla. Un informe intermedio
     usa nombre propio (..._PROGRESS_REPORT_001.md) en vez de consumir ese número. -->

## Qué pasaba
<El problema o el objetivo, en 2–4 líneas. Con la causa etiquetada:
CONFIRMED / LIKELY / UNVERIFIED.>

## Qué cambia
- <Cambio 1, y por qué>
- <Cambio 2, y por qué>
- <Lo que NO cambia, si alguien podría suponerlo>

**Archivos:** <rutas principales, agrupadas por backend / frontend / migraciones / tests / docs>

## Expected → Implemented → Evidence → Gap
<!-- Usar esta tabla cuando la instrucción tiene criterios de aceptación.
     Si no, basta con «Cómo se comprobó». -->
| Expected | Implemented | Evidence | Gap / Impact |
|---|---|---|---|
| | | | |

## Cómo se comprobó
| Prueba | Resultado |
|---|---|
| Tests dirigidos `<comando>` | N/N PASS |
| Typecheck / lint / build | exit 0 |
| Migración (sube, baja, sube) | OK · 1 head |
| Regresión completa | N passed · N failed (cuáles y si ya existían) |
| Validación en el entorno compartido | NOT RUN / PENDING |

## Hallazgos
- <Hallazgo, causa (CONFIRMED / LIKELY / UNVERIFIED), impacto, acción>
- <Errores propios durante el trabajo y cómo se corrigieron>

## Lo que necesito de ti
| Qué | Por qué |
|---|---|
| Revisar y fusionar el MR | No se fusiona desde aquí |

## Pendientes operativos
<Lo que tiene que ocurrir en otro sitio: migración en el despliegue, permisos,
configuración, datos.>

## Esfuerzo
| Tarea | Estado | Volumen | Horas-agente |
|---|---|---|---|
| | Hecho | ~N LoC | N h |
| Restante | | | N h |
