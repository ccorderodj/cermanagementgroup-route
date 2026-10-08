# CER Route · H-2 · Integridad de datos en Today / Live

**Reporte 001** · 8 de octubre de 2026
**Alcance:** consolidar Today por supervisor. Nada más.
**Rama:** `fix/h2-today-live-data-integrity`

---

## Status

`COMPLETED WITH PENDING VALIDATION`

Los ocho criterios de aceptación están implementados y validados con evidencia
nombrada. Queda la validación de campo de CER y una limitación declarada que
pertenece al checkpoint siguiente (§2).

---

## 1 · Qué se corrigió

Un supervisor con dos jornadas el mismo día salía **dos veces** en la lista, con
identificadores idénticos, sus millas partidas entre las filas y el panel
lateral describiendo la primera. La captura de campo lo mostraba así: dos filas
«Karina Aguirre», una `Work Ended` con `0.0 mi` y otra `Working` con 62,5 mi, y
el panel enseñando la cerrada mientras el administrador había pulsado la abierta.

El modelo permite ese estado **a propósito**: `uq_work_session_one_active` es un
índice parcial sobre `status = 'active'`, de modo que las jornadas cerradas se
repiten cuantas veces haga falta. Today asumía una por persona y nadie
reconcilió las dos cosas.

### La regla aplicada

| | Qué se hace | Por qué |
|---|---|---|
| Millas oficiales | **se suman** las del día | quien condujo en dos jornadas recorrió la suma; enseñar una parte bajo «miles today» afirma un dato falso |
| Actividades | **se suman** | ídem |
| Viajes sin cifra | **se suman** | ídem |
| `mileage_pending` | **O lógico** | si cualquier jornada tiene un viaje sin calcular, el total no es final |
| Estado y `since` | **se eligen** de una jornada | sumar un instante no significa nada |
| Vehículo y contexto del viaje | **se eligen** de la misma | deben describir el mismo hecho |

La jornada elegida es **la activa**; si no hay ninguna, **la última iniciada**.

---

## 2 · Validación previa de zona horaria — limitación declarada

La instrucción pedía identificar si existe una zona horaria confiable por
supervisor **antes** de cambiar la lógica de selección, e informar si no.

**No existe.** No hay campo de zona horaria en `SupervisorProfile`, en `Users`
ni en `Company`. Lo único almacenado es `WorkSession.start_utc_offset_minutes`:
el desfase que reportó el dispositivo **en esa jornada concreta**, no una
propiedad de la persona.

Consecuencia directa: para un supervisor **sin jornada hoy** no hay forma de
conocer su fecha local actual sin inventar una zona o tomar el desfase de otro
supervisor, y las dos cosas están prohibidas por las reglas temporales de este
checkpoint.

**Por lo tanto no se modificó la lógica de selección del día.** `business_day()`
queda exactamente como estaba, y la consolidación ocurre **dentro** del día que
esa función ya elige. Esto cumple el alcance de H-2 sin tocar lo que depende de
la decisión T-1, todavía pendiente.

Queda documentado en el código, para que nadie lo reabra por suposición:
[`live/dao.py`](app/routers_api/live/dao.py), docstring del módulo y de
`_consolidar`.

---

## 3 · Implementación

| Archivo | Cambio |
|---|---|
| [`app/routers_api/live/dao.py`](app/routers_api/live/dao.py) | `_consolidar()` y `_representante()`: agrupan por `user_id` tras las consultas existentes |
| [`RouteTodayLivePage.tsx`](app/components/react/pages/RouteTodayLivePage/ui/RouteTodayLivePage.tsx) | la selección ya no cae al primero cuando hay una elección explícita |

**Ninguna consulta se reescribió.** Las seis que ya existían —supervisores,
jornadas, viaje vigente, actividad en curso, cuentas y millaje— se conservan sin
un solo cambio, y la consolidación ocurre en el punto de ensamblaje. Era la
corrección más pequeña que resuelve el defecto completo: reescribir la
agregación en SQL habría tocado índices y planes sin ganar nada a esta escala.

### Lo que no se tocó

Contratos de la API, interfaces aprobadas, navegación, `Start Work` / `End Work`,
viajes, actividades, reglas de kilometraje, datos históricos, estructura de base
de datos, User Activity, My Activity y la semántica de *Current / Last Activity*
—reservada para H-3—.

**Cero migraciones. Cero cambios de esquema. El contrato `LiveSupervisor` no
cambió ni un campo.**

### Los contadores, sin tocarlos

`supervisors_total`, `supervisors_working`, `on_route` e `in_activity` se
calculan en [`live/router.py`](app/routers_api/live/router.py) contando filas de
la lista. Con una fila por persona **pasan a contar personas sin modificar una
sola línea**. Se fijaron con pruebas igualmente, porque lo que hoy es correcto
por construcción debe seguir siéndolo mañana.

---

## 4 · Validación

### 4.1 · Integración · 23/23 PASS · exit 0

`tests/integration/test_live_today.py` — 15 existentes sin modificar, 8 nuevos.

| Criterio | Prueba |
|---|---|
| AC-1 · aparece una sola vez | `test_dos_jornadas_el_mismo_dia_producen_una_sola_fila` |
| AC-2 · millas acumuladas | `test_las_millas_del_dia_suman_todas_sus_jornadas` (10 + 10 = 20) |
| AC-3 · actividades sin duplicar | `test_las_actividades_del_dia_suman_sin_duplicar` |
| AC-4 · panel correcto | `test_el_estado_sale_de_la_jornada_activa_y_no_de_la_cerrada` |
| AC-5 · personas únicas | `test_el_resumen_cuenta_personas_y_no_jornadas` |
| AC-6 · refresco | E2E, §4.3 |
| AC-7 · sin pérdida de información | `test_quien_no_ha_empezado_no_se_convierte_en_jornada_de_cero` |
| AC-8 · tenant y permisos | los 3 tests de autorización existentes, sin cambios |

Tres pruebas van más allá del mínimo, por riesgos concretos:

- `test_la_consolidacion_no_mezcla_a_dos_supervisores` — el control del
  conjunto. Sin él, una agrupación mal escrita pasaría todas las demás y sumaría
  las millas de una persona a otra, **que es peor que el defecto original**.
- `test_sin_jornada_activa_el_estado_sale_de_la_ultima` — la otra mitad de la
  regla de elección.
- `test_quien_no_ha_empezado_no_se_convierte_en_jornada_de_cero` — la fila con
  `sesion_id` nulo que deja el `LEFT JOIN` no es una jornada de cero; tratarla
  como tal daría `0.0 mi` con aire de dato medido.

### 4.2 · Las pruebas reproducen el defecto · `CONFIRMED`

Ejecutadas contra el código anterior, revirtiendo sólo `app/`:

```
...............FFFF.F..                            [100%]
FAILED test_dos_jornadas_el_mismo_dia_producen_una_sola_fila
FAILED test_las_millas_del_dia_suman_todas_sus_jornadas
FAILED test_las_actividades_del_dia_suman_sin_duplicar
FAILED test_el_estado_sale_de_la_jornada_activa_y_no_de_la_cerrada
FAILED test_el_resumen_cuenta_personas_y_no_jornadas
```

**5 de las 8 fallan con el código anterior.** Las otras tres son controles de
regresión, no reproducciones, y se dice explícitamente para no inflar la cifra.

Una de ellas merece una nota honesta:
`test_sin_jornada_activa_el_estado_sale_de_la_ultima` **pasaba** con el código
anterior, pero por casualidad: sin consolidación el orden entre dos jornadas de
la misma persona no estaba definido y PostgreSQL podía devolver cualquiera.
Ahora es determinista. No se presenta como reproducción del defecto.

### 4.3 · Navegador · 2/2 PASS · exit 0

`tests/e2e/test_h2_today_consolidation_browser.py`, contra el bundle
reconstruido con `npm run build:prod`.

| Prueba | Qué fija |
|---|---|
| `test_escritorio_una_fila_y_el_panel_correcto` | una fila, panel de la jornada abierta, `user_id` sin repetir, contadores por persona, y **la selección intacta tras una relectura** |
| `test_movil_una_fila_y_su_detalle` | lo mismo en la arquitectura móvil, que es otra: lista y detalle a pantalla completa |

El caso móvil no se copió del de escritorio porque la pantalla no es la misma:
el detalle es una vista entera con vuelta, no un panel lateral, así que hay que
entrar a él para comprobar lo que describe.

### 4.4 · Evidencia visual

Cuatro capturas en `var/screenshots/h2/`, fuera del árbol versionado, con el
mismo arnés que el resto de la evidencia visual de Today:

```
escritorio-una-fila-panel-correcto.png
escritorio-tras-el-refresco.png
movil-lista-una-tarjeta.png
movil-detalle-jornada-abierta.png
```

Se regeneran con:

```bash
uv run pytest tests/e2e/test_h2_today_consolidation_browser.py
```

**Lo que muestran, y es la demostración más clara de la regla:** una sola fila
de `Supervisor Tester`, estado `Working` —el de la jornada **abierta**— y
`1 activities today`, que es la actividad de la jornada **cerrada**. La
consolidación suma lo que pertenece al día y elige lo que describe el instante,
y las dos cosas se ven a la vez en la misma captura.

El encabezado muestra `SUPERVISORS WORKING 1 · of 1 active today`: una persona
con dos jornadas sigue siendo una persona.

### 4.5 · Typecheck, lint y build

```
npm run typecheck   0 errores
npm run lint:ts     0 errores
npm run build:prod  compilado (2 warnings de tamaño, preexistentes)
```

### 4.6 · Regresión completa · 1080 ejecutados · 1 fallo preexistente

```
1080 ejecutados
1064 PASS
   1 FAILED   test_provisioning_alignment (preexistente, ajeno a H-2)
   0 errores
  15 skipped
```

El único fallo es el que el diagnóstico ya elevó: el rol Administrador tiene 14
capacidades y se certificaron 12, por `route.live.read` (RTE07) y
`route.activity.read` (RTE08). **Falla igual con el código de `dev`** y no se
toca a propósito: ese test existe para que una ampliación de privilegio no pase
sin aprobación de CER, y cambiar el número sería hacer verde justo lo que el
control frena. Es la decisión G-2 del diagnóstico.

Ningún test de Today, Live, viajes, jornadas, kilometraje, odómetro ni ubicación
se rompió.

### 4.7 · Resumen de lotes

| Lote | Tests | PASS | Fallos | Exit |
|---|---|---|---|---|
| Today / Live (dirigido) | 23 | 23 | 0 | 0 |
| Regresión sin navegador | 1080 | 1064 | 1 preexistente | 1 |
| E2E H-2 escritorio y móvil | 2 | 2 | 0 | 0 |
| typecheck · lint · build | — | — | 0 | 0 |

---

## 5 · Hallazgos

### H-2-F1 · `CONFIRMED` — La selección caía al primero durante el refresco

Encontrado al revisar el criterio AC-6, no reportado antes. El frontend hacía:

```ts
const elegido = supervisores.find(...) ?? supervisores[0] ?? null;
```

Si el supervisor seleccionado desaparecía de la lista —se desactiva su perfil,
cambia el conjunto— el panel **saltaba al primero sin avisar**, y con un refresco
cada 30 segundos eso podía ocurrir bajo el cursor.

Corregido: el reserva al primero se aplica **sólo al primer render**, cuando aún
no se ha elegido a nadie. Con una elección hecha, si esa persona no está, no se
muestra a otra. Es preferible no mostrar a nadie que mostrar a alguien distinto
sin decirlo.

### H-2-F2 · `DECISION REQUIRED` — El día de negocio sigue dependiendo de un desfase ajeno

No se corrigió por instrucción expresa (§2). `business_day()` toma el desfase de
la última jornada iniciada **en toda la compañía** y lo aplica al reloj para
decidir qué día es hoy, de modo que el día de un supervisor puede derivarse del
dispositivo de otro.

Está documentado en el verificador del contrato temporal (I-1, I-2) y su
corrección depende de la decisión T-1.

---

## 6 · Estimación del trabajo realizado

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Validación previa de zona horaria | — | análisis | 0,4 |
| Consolidación en el DAO | ~95 LoC | dominio | 0,7 |
| Selección estable en el frontend | ~20 LoC | UI | 0,4 |
| Pruebas de integración (8) | ~310 LoC | integración | 3,4 |
| E2E en escritorio y móvil, con capturas | ~230 LoC | navegador | 3,6 |
| Verificación contra el código anterior | — | — | 0,5 |
| Regresión, MR y reporte | — | — | 1,4 |
| **Total** | **441 añadidas / 16 borradas** | | **≈ 10,4 h** |

Márgenes: **+10 %** en dominio y UI, **+50 %** en navegador.

Estimado en el diagnóstico: 4,1 h para el bloque equivalente. La diferencia está
en las pruebas: el diagnóstico estimó el cambio, no el E2E en dos tamaños con
evidencia visual ni la verificación contra el código anterior, que juntos son
4,1 h de las 10,4.

---

## 7 · Git

| | |
|---|---|
| Rama | `fix/h2-today-live-data-integrity` |
| Base | `dev` en `7b597ec` |
| Commit | se añade al cerrar |
| MR | se añade al cerrar |
| Fusionado | **No.** CER certifica |

---

## 8 · Trabajo restante y acción operativa

1. **Validación de campo (CER).** Un supervisor real con dos jornadas en un día
   y un administrador mirando Today. `IMPLEMENTED` no es `VALIDATED`.
2. **Decisión T-1** sobre qué define el día de negocio (§5, H-2-F2).
3. **H-3 no se ha iniciado.** La semántica de *Current / Last Activity* sigue
   exactamente como estaba: el propósito del viaje vigente, vacío cuando no hay
   ninguno. Se ve en las capturas como `—`, y es el comportamiento anterior sin
   modificar.
4. **Nada que ejecutar en el despliegue.** Sin migraciones, sin semillas, sin
   convergencia: basta con desplegar.

## 9 · Siguiente paso

La certificación de CER sobre el MR. No se inicia H-3 ni ningún cambio temporal
adicional sin aprobación del checkpoint siguiente, como indica la instrucción.
