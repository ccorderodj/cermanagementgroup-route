# CER Route — Jerarquía V1.5: la historia sigue al puesto; CEO y COO solo por «Replace manager»

**Reporte de implementación 001** · 14 de octubre de 2026
**Origen:** decisión del PO, transmitida por el desarrollador: «prevalece la relación más que relación + tiempo», con la matización de los traslados de mandos medios, y «CEO y COO solo con Replace manager».
**Status: COMPLETED WITH PENDING VALIDATION.** Validado en local, en la base de tests. Pendiente: la certificación de CER y el despliegue. Una decisión de datos sobre el caso concreto de Rodrigo (§4).

---

## 1. Base y entornos

| Elemento | Valor |
|---|---|
| Base | `dev` @ `975b13e` (incluye V1.4, MR !93, ya desplegado en DigitalOcean) |
| Rama | `feature/hierarchy-history-follows-position`. **No fusionada ni desplegada** |
| Migración nueva | `0020_org_replaces_user`, aditiva y reversible; head único |
| Base local | Sin tocar; sigue en la 0018 por las incoherencias del gate de V1.4 |
| DigitalOcean | No accedido. Al fusionar, el job PRE_DEPLOY aplicará la 0020 y `converge` |

---

## 2. La regla nueva de historial

Sustituye a D-3 en **dos** casos y la conserva en el tercero:

| Situación | Quién ve el historial anterior | Por qué |
|---|---|---|
| **Sustitución** («Replace manager») | El **sucesor hereda** todo lo que veía su antecesor hasta el relevo | El historial es del **puesto**: un CEO, COO o RM nuevo entiende la operación que recibe |
| **Carga inicial** (primera asignación de cada persona) | Su **primer jefe** y la cadena por encima ven **todo su pasado** | Antes de la jerarquía nadie era su jefe: no hay a quién quitárselo |
| **Traslado lateral** (p. ej. un supervisor de RM-A, Texas, a RM-B, Georgia) | **Por periodo**: RM-A, hasta el traslado; RM-B, desde el traslado; COO y CEO, todo | Cada zona conserva su histórico; nadie ve operaciones ajenas ni se reescriben informes pasados |

**Lo que no cambia:**
- Today sigue usando la relación **vigente**.
- Sales solo es visible para el CEO.
- Ninguna compañía ve datos de otra.
- Las capacidades de cada rol siguen igual.
- Pedir un id directamente fuera de la rama sigue dando 404.
- Quien tiene alcance de compañía (Administrador de Route, owner, admin) sigue igual.

**Lo que no se hereda:** el sucesor **no** hereda las jornadas **propias** del antecesor (lo que él mismo ejecutó), solo las de su rama. Es una decisión a confirmar (§5).

**Cómo:**
- La herencia y la carga inicial se **calculan** al leer (`organization/scope.py`, `ventanas_del_puesto`). **Ninguna fila se reescribe.**
- «Replace manager» guarda en la fila del sucesor a quién sustituye (`org_assignment.replaces_user_id`).

## 3. CEO y COO solo por «Replace manager»

**En el servidor**, la respuesta es **409** con el código `use_replace_manager` cuando una **edición**:
- cambia el rol o el superior de un CEO o un COO;
- hace a alguien CEO o COO desde la lista de roles;
- cambia o quita un cargo CEO o COO por la API de organización.

**Lo que sigue permitido:**
- El **alta** del **primer CEO** de una compañía vacía.
- El alta de un **COO nuevo**, que es otro puesto y no un relevo.
- Editar nombre, correo y contraseña de un CEO o COO, mandando el mismo rol y el mismo superior.
- Para RM, Supervisor, OSM y Sales, la lista funciona como hasta ahora.

**En la pantalla** (CER Route → Users → Edit):
- Para un CEO o COO, el rol y «Reports to» aparecen **bloqueados**, con el aviso «CEO and COO change only through “Replace manager”».
- A los demás, la lista **ya no ofrece** CEO ni COO.

**Sobre uno mismo** se mantiene el 403 previo: nadie cambia su propio cargo.

## 4. El caso de Rodrigo (`test`) — DECISION REQUIRED

| Hecho (consola de DigitalOcean, 14-10) | Consecuencia con V1.5 |
|---|---|
| `test` = COO, con 270 (Supervisor) y 269 (RM) debajo **desde el 14-10** | — |
| Esos dos dependían antes de **ftijerino** (COO), según la auditoría de las 15:43–15:44 | Moverlos a mano es un **traslado lateral** |
| Sus 16 jornadas son anteriores al 14-10 | Quedan atribuidas a su **primera** relación (ftijerino y su cadena), **no** a `test` |

**Rodrigo seguirá sin ver esas 16 jornadas solo con desplegar V1.5.** Las verá si su llegada se registra como **sustitución de ftijerino**. Hay dos formas:
1. **Si ftijerino debe salir:** que el Administrador de Route haga «Replace manager» sobre ftijerino con `test` como sucesor (ya en V1.4).
2. **Si el relevo ya ocurrió de hecho** (los subordinados se movieron a mano), hay que hacer una **corrección de datos puntual**: poner `replaces_user_id = ftijerino` en la asignación vigente de `test`. Es un script aparte, con modo de prueba y auditoría, que solo se ejecuta con autorización expresa. **No está hecho.**

## 5. Decisiones pendientes

- **R-1:** ¿hereda el sucesor también las jornadas **propias** de su antecesor? Hoy no.
- **R-2:** para Rodrigo, ¿opción 1, opción 2, o dejarlo así?
- **R-3** (de V1.4, sigue abierta): las 27 capacidades del rol CEO.

## 6. Pruebas

| Lote | Resultado |
|---|---|
| Jerarquía, V1.4, V1.5 y migraciones (`test_org_hierarchy`, `test_hierarchy_integrity_v14`, migraciones 0018/0019) | **138/138 PASS** |
| Tests nuevos V1.5 | herencia en la sustitución (15,0 millas, frente a 5,0 en V1.4); carga inicial (el primer jefe ve el pasado sin retrofechar); traslado lateral por periodo (RM-A 10,0 · RM-B 5,0 · CEO 15,0); bloqueo CEO/COO (4 vías por usuarios + 2 por organización, sin cambios); lo permitido (edición inocua, COO nuevo, lista para el resto) |
| E2E de jerarquía (V1.3 + V1.4 + bloqueo V1.5) | **13/13 PASS** |
| `npm run check` | 0 errores |
| Regresión completa: integración + contratos | **1314 PASS, 15 skipped, 1 FAIL** (preexistente desde RTE09: `test_provisioning_alignment` espera 12 capacidades para `route_admin` y hay 16; decisión de CER), 1237 s |
| Regresión completa: E2E | **200 PASS, 5 FAIL** (los 5 preexistentes de ubicación sin conexión de RTE06, idénticos a la vuelta de V1.4; mi *diff* no toca ubicación ni la cola sin conexión), 3554 s |

**Error propio, corregido antes de probar (`CONFIRMED`):** la primera versión extendía hacia atrás también la fila de relevo de un sucesor nuevo, y así perdía el instante del relevo. Ahora los relevos se leen de las filas sin extender.

## 7. Despliegue y rollback

- **Al fusionar:** PRE_DEPLOY aplica la 0020 (columna nula, sin datos que migrar). Que todos recarguen la aplicación.
- **Rollback:** `alembic downgrade 0019_org_single_ceo` quita la columna, y se revierte el código. La regla vuelve a D-3, sin pérdida de asignaciones.

## 8. Esfuerzo

| Tarea | Estado | Horas-agente |
|---|---|---|
| Alcance (herencia y carga inicial) + migración | Hecho | 2,0 |
| Bloqueo CEO/COO (servidor y pantalla) | Hecho | 1,5 |
| Tests y E2E | Hecho | 2,5 |
| Regresión, informe, MR | En curso | 1,0 |
| **Total** | | **≈ 7 h** (estimado: 7) |
| Corrección de datos del caso de Rodrigo (opción 2), si se autoriza | Pendiente | 1,0 + 10 % |
