# CER Route · «Keep working» no funcionaba tras un End Work accidental

**Reporte 001** · 9 de octubre de 2026
**Origen:** reporte de campo — «presioné sin querer *End Work* mientras manejaba
y no me deja darle a *Keep working*».
**Alcance:** opción 1 del diagnóstico: que «Keep working» retire de verdad la
intención de cerrar. **Sin** diálogo de confirmación (opción 2), sin cambios de
pantalla.
**Rama:** `fix/keep-working-withdraws-end-of-day`

---

## Status

`COMPLETED WITH PENDING VALIDATION`

Implementado y validado con pruebas automáticas y de navegador. Queda la
validación de campo de CER y una decisión de producto sobre un caso límite (§5).

---

## 1 · Causa raíz · `CONFIRMED`

1. `End Work` con el vehículo en uso crea la lectura de cierre `PENDING` en el
   servidor (`end_requirement`) **antes** de rechazar el cierre con 409. La
   jornada sigue abierta.
2. La pantalla decide la fase leyendo esa fila: con ella viva enseña la captura
   de cierre. Es deliberado —ODO-03, 01/10— para que la tarea sobreviva a que
   Android recree la pestaña al volver de la cámara.
3. «Keep working» **sólo releía el estado**. La fila seguía ahí, y la pantalla
   volvía a la misma captura. No existía ninguna forma de retirar la intención
   de cerrar: la única salida era cerrar el día.

Una de las 6 pruebas de navegador que ya fallaban en `dev`
(`test_rte04 … rejected_end_work_does_not_come_back_from_the_queue`) era
exactamente este defecto, y nadie la había conectado con él.

---

## 2 · La corrección

### 2.1 · Servidor

`POST /api/odometer/sessions/{id}/end/withdraw` — `OdometerService.withdraw_end`.

| Estado de la lectura de cierre | Qué hace |
|---|---|
| `PENDING`, **sin foto y sin excepción** — el caso reportado | **la retira** y deja traza en auditoría (`end_withdrawn`) |
| no existe, o ya resuelta | nada; responde el estado (idempotente) |
| con foto subida, o excepción pedida | **409, no toca nada** (§5) |
| jornada ya cerrada | **409**: no reabre el día por esta vía |

**Por qué borrar la fila es seguro en el primer caso:** una lectura `PENDING`
sin foto ni excepción no contiene ningún hecho; es la marca de «falta la
lectura». Nada la referencia y no tiene disparadores. El siguiente `End Work` la
vuelve a crear. La traza queda en `audit_event`, que es append-only.

**Concurrencia:** la jornada se bloquea (`FOR UPDATE`) antes de mirar la
lectura, así que un `End Work` simultáneo no puede colarse entre la
comprobación y la retirada.

**Autorización y tenant:** el mismo permiso que el resto de acciones del
supervisor (`route.worksession.execute`) y sólo sobre **su** jornada. Otra
persona u otra compañía reciben 404, sin distinguir. Ningún permiso nuevo.

### 2.2 · Pantalla

«Keep working» llama a la retirada y después reconcilia. Si el servidor la
rechaza (foto o excepción), muestra el motivo y se queda en la captura. **La
pantalla no cambia**: mismo botón, mismo texto, mismo lugar.

ODO-03 se conserva: la captura de cierre sigue sobreviviendo a una recarga.
Ahora sólo desaparece cuando el supervisor lo pide.

### 2.3 · Archivos

| Archivo | Cambio |
|---|---|
| `app/routers_api/odometer/service.py` | `withdraw_end` |
| `app/routers_api/odometer/router.py` | el endpoint |
| `entities/RouteOdometer/model/services/odometerService.ts`, `index.ts` | `withdrawOdometerEnd`, validado con Zod |
| `pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx` | `seguirTrabajando`; el botón la usa |
| `tests/integration/test_odometer_end_work.py` | 7 pruebas nuevas |
| `tests/e2e/test_keep_working_browser.py` | E2E nueva del caso reportado |
| `tests/e2e/test_rte04_closure_browser.py` | expectativa de recarga actualizada (§3.3) |

Ninguna migración. Ningún cambio de esquema.

---

## 3 · Validación

### 3.1 · Integración · 7/7 PASS

| Prueba | Qué demuestra |
|---|---|
| `…withdraws_the_end_reading_and_work_goes_on` | **el caso reportado**: se retira, la jornada sigue abierta, puede salir a otro destino, y al terminar de verdad la lectura se vuelve a pedir |
| `…without_a_pending_end_changes_nothing` | idempotente |
| `…does_not_discard_an_end_photo` | con foto: 409 y la fila intacta |
| `…does_not_discard_an_end_exception` | con excepción: 409 |
| `…cannot_reopen_an_ended_day` | cerrado el día: 409 y la lectura se conserva |
| `…only_on_your_own_day` | otra persona y otro tenant: 404 |
| `…is_audited` | quién, cuándo y por qué |

### 3.2 · Reproducen el defecto · `CONFIRMED`

Contra el servidor anterior **fallan 6 de 7**. La séptima
(`only_on_your_own_day`) pasa también antes, porque sin el endpoint la ruta da
404 igual: es un control, no una reproducción, y se dice para no inflar la cifra.

### 3.3 · Navegador · 2/2 PASS · móvil

- **`test_keep_working_browser`** (nueva): `End Work` accidental → captura de
  cierre → `Keep working` → workbench → **puede salir de nuevo** → recargar no
  hace reaparecer la captura.
- **`test_rte04 … rejected_end_work_does_not_come_back_from_the_queue`**: **la
  que fallaba en `dev`, ahora en verde.**

**Corrección a lo que dije en el diagnóstico:** escribí que esta prueba «debería
volver a pasar» con el arreglo. No bastaba. Esperaba que **sólo recargar**
devolviera al workbench, y eso contradice ODO-03, que está aprobada. Se actualizó
con el patrón que la propia prueba ya usa —*old expectation / approved decision /
new expectation*—: recargar mantiene la captura y no reenvía el `End Work`;
`Keep working` la retira; y después, recargar ya no la resucita. Lo que la
prueba defendía —que la cola queda limpia y nadie cierra el día por detrás— se
sigue comprobando entero.

Capturas en `var/screenshots/keep-working/`: la pantalla de cierre **sin cambios
visuales** y el workbench después de `Keep working`.

### 3.4 · Comprobaciones

```
uv run python -c "import app.main"      OK
npm run typecheck                         0 errores
npm run lint:ts                           0 errores
npm run build:prod                        compilado (2 avisos de tamaño, preexistentes)
test_permission_catalog + public_surface  21/21 PASS
black (archivos tocados)                  limpio
```

### 3.5 · Regresión

| Lote | Tests | PASS | Fallos | Exit | Duración |
|---|---|---|---|---|---|
| Sin navegador, 3 workers | 1096 | 1080 | 1 preexistente | 1 | 9 min 14 s |
| Navegador, flujos de My Route | 14 | 14 | 0 | 0 | 3 min 14 s |

- **Sin navegador:** 7 PASS más que la última regresión de `dev` (1073), que
  son las 7 nuevas. El único fallo es `test_provisioning_alignment` (14 frente
  a 12 capacidades), que espera decisión de CER y no se toca.
- **Navegador:** los archivos completos de cierre (RTE04), odómetro de inicio y
  cierre, restauración de la captura de cierre (ODO-03) y la E2E nueva. Que
  ODO-03 siga verde es lo que demuestra que la captura **sigue** sobreviviendo a
  la recreación de la pestaña.
- **No se ejecutó** la batería completa de navegador (≈ 58 min): el cambio sólo
  toca la fase de cierre de My Route, y los archivos que la cubren están todos
  arriba. `NOT RUN` para el resto.

---

## 4 · Qué puede hacer el usuario afectado **hoy**

El arreglo no está desplegado. Hasta entonces, la salida que no inventa datos:
hacer la **lectura de cierre real**, que cierra la jornada, y pulsar **Start
Work** de nuevo. Today consolida las dos jornadas del día en una fila (H-2) y el
kilometraje es por viaje, así que no se pierde ni duplica nada.

**Después de desplegar**, si su jornada sigue en la captura de cierre sin foto,
`Keep working` le devolverá al trabajo sin más.

---

## 5 · Decisión pendiente del PO

Si el supervisor **ya hizo la foto** del cierre, o **pidió la excepción**, y
después pulsa `Keep working`, hoy el servidor responde 409 y el supervisor sigue
sin poder trabajar sin cerrar el día. Es raro —hace falta pulsar `End Work` y
además empezar la lectura— pero existe.

Resolverlo exige decidir qué pasa con esa evidencia: **conservarla marcada como
descartada** (recomendado; necesita un estado nuevo y una migración) o
descartarla. No se decide aquí.

---

## 6 · Hallazgos incidentales

1. **`End Work` sin conexión tampoco tiene salida.** Se encola y la pantalla
   muestra *Ending your day… this will sync*, sin `Keep working`. Al sincronizar
   llega el mismo 409 y el supervisor cae en la captura de cierre, donde ahora
   sí puede seguir. `UNVERIFIED` en navegador.
2. **Quedan 5 pruebas de navegador fallando en `dev`**, de ubicación sin
   conexión y recuperación de ubicación (reporte de workers, §5.1). Ésta no
   explica esas cinco.

---

## 7 · Estimación

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Diagnóstico | — | — | 0,8 |
| Servicio, endpoint y auditoría | ~125 LoC | dominio | 0,8 |
| Cliente y botón | ~45 LoC | UI | 0,7 |
| Pruebas de integración (7) y verificación contra el código anterior | ~165 LoC | integración | 1,8 |
| E2E nueva y actualización de RTE04, con capturas | ~110 LoC | navegador | 1,6 |
| Regresión, reporte y entrega | — | — | 1,2 |
| **Total** | | | **≈ 6,9 h** |

Estimado en el diagnóstico: 5–7 h. Dentro del rango.

---

## 8 · Git

| | |
|---|---|
| Rama | `fix/keep-working-withdraws-end-of-day` |
| Base | `dev` en `af194f6` |
| Commit | `4b8fb06` |
| MR | **!80** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/80 |
| Árbol | limpio |
| Fusionado | **No.** CER certifica |
| Despliegue | código de servidor y bundle; **sin migraciones** |

---

## 9 · Siguiente paso, sin empezarlo

1. **Validación de campo (CER)** con el supervisor que lo reportó, tras desplegar.
2. **Decisión del §5** si se quiere cubrir el caso con evidencia.
3. La **opción 2** —confirmar antes de `End Work`— sigue disponible si los
   cierres accidentales se repiten.
