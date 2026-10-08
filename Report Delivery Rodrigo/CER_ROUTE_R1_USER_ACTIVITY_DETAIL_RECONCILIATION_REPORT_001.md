# CER Route · R-1 · El detalle de User Activity explica su consolidado

**Reporte 001** · 8 de octubre de 2026
**Alcance:** la asimetría entre el total y la lista. Nada más.
**Rama:** `fix/r1-user-activity-detail-reconciliation`

---

## Status

`COMPLETED WITH PENDING VALIDATION`

Los nueve criterios de aceptación están implementados y validados con evidencia
nombrada. Queda la validación de campo de CER.

---

## 1 · Causa raíz y corrección

El total salía de `agregados_por_dia` —que parte de `WorkSession`, hace `INNER
JOIN` a `Trip` y por tanto **incluye todos los viajes**— mientras la lista salía
de `paradas_del_dia`, que partía de `ActivityExecution` y **sólo veía los viajes
con parada**.

Un viaje que no abre parada —el regreso a casa, uno interrumpido por
`End Work Anyway`, uno que llegó sin iniciarla— aportaba sus millas al
consolidado y no existía para el detalle. En el caso que lo destapó, ese viaje
invisible era **la mitad del kilometraje del día**.

**La corrección invierte el origen de la consulta del detalle:** parte de `Trip`
y hace `outerjoin` a `ActivityExecution`. La relación opcional convierte «no hay
parada» en un hecho representable en lugar de en una fila ausente.

---

## 2 · Archivos y contratos

| Archivo | Cambio |
|---|---|
| [`activityexplorer/dao.py`](app/routers_api/activityexplorer/dao.py) | `paradas_del_dia` parte de `Trip`; `trip_id` y `user_id` se leen del viaje y de la jornada; orden por `Trip.started_at, Trip.id`; nuevo `has_activity` |
| [`activityexplorer/schemas.py`](app/routers_api/activityexplorer/schemas.py) | `activity_execution_id` y `started_at` pasan a opcionales; se añade `has_activity` |
| [`activityexplorer/router.py`](app/routers_api/activityexplorer/router.py) | el contador deja de ser `len(paradas)` |
| [`ExplorerActivityCards.tsx`](app/components/react/features/RouteActivityExplorer/ui/ExplorerActivityCards.tsx) | clave de render `trip_id`; `Outcome` y el rango horario no fingen `In progress` |
| [`RouteActivityExplorer/model/types/index.ts`](app/components/react/entities/RouteActivityExplorer/model/types/index.ts) | el esquema Zod acepta los campos opcionales |

### Cambios de contrato

```diff
- activity_execution_id: int
+ activity_execution_id: Optional[int] = None
- started_at: datetime
+ started_at: Optional[datetime] = None
+ has_activity: bool = True
```

**Los tres son compatibles hacia atrás.** Relajar un campo obligatorio no rompe
a ningún consumidor que ya lo recibía, y `has_activity` trae un defecto que
describe el comportamiento anterior. **Ninguna migración. Ningún cambio de
esquema de base de datos.**

### El contador, que era el riesgo señalado

```diff
- activities=len(paradas),
+ activities=sum(1 for p in paradas if p["has_activity"]),
```

Mientras la lista contenía sólo actividades, contar filas y contar paradas eran
lo mismo. Desde que incluye trayectos, no: habría dicho «2 activities» donde
hubo una. **El contador sigue respondiendo a la misma pregunta que antes**, y hay
una prueba dedicada a que siga haciéndolo.

---

## 3 · Expected vs Implemented

| | Esperado | Implementado |
|---|---|---|
| Viaje sin parada en el detalle | sí | **sí** |
| Total reconciliable con la lista | sí | **sí**, comprobado sumando |
| Contador = paradas reales | sí | **sí** |
| Viaje sin parada como `In progress` | **no** | **no**, en los dos sitios donde ocurría |
| Millas almacenadas | sin cambios | **sin cambios** |
| Pendiente distinguido de calculado | sí | **sí** |
| Duplicados | ninguno | **ninguno** |
| Filtros y autorización | sin cambios | **sin cambios** |
| Disposición escritorio/móvil | aprobada | **sin rediseño** |

---

## 4 · Validación

### 4.1 · Integración · 26/26 PASS · exit 0

`tests/integration/test_activity_explorer.py` — 17 existentes **sin modificar**,
9 nuevos.

| AC | Prueba |
|---|---|
| AC1 · el regreso a casa aparece | `test_el_regreso_a_casa_aparece_en_el_detalle` |
| AC2 · no sube el contador | `test_un_viaje_sin_parada_no_cuenta_como_actividad` |
| AC3 · no es `In progress` | `test_un_viaje_sin_parada_no_se_presenta_como_en_curso` |
| AC4 · total sin cambios | `test_el_detalle_reconcilia_el_total_consolidado` |
| AC5 · las paradas conservan su información | los 17 existentes, verdes sin tocar |
| AC6 · pendiente distinguido | `test_el_millaje_pendiente_sigue_distinguiendose` |
| AC7 · sin duplicados | `test_no_hay_viajes_duplicados_en_el_detalle` |
| AC8 · filtros y tenant | los 4 de autorización existentes |
| AC9 · disposición | E2E, §4.3 |

Más los casos que el checkpoint pedía por separado: viaje interrumpido, varias
jornadas el mismo día, y orden determinista.

### 4.2 · Las pruebas reproducen el defecto · `CONFIRMED`

Contra el código anterior, revirtiendo sólo `app/`:

```
.................FFFFFF.FF                         [100%]
8 de 9 fallan
```

La novena —`test_no_hay_viajes_duplicados_en_el_detalle`— es un control de
regresión, no una reproducción, y se dice para no inflar la cifra.

### 4.3 · Navegador · 2/2 PASS · exit 0

`tests/e2e/test_r1_detail_reconciliation_browser.py`, contra el bundle
reconstruido.

- **Escritorio:** la tarjeta del trayecto existe, no dice `In progress`, el
  total se reconcilia sumando lo visible, y el contador cuenta paradas.
- **Móvil:** lo mismo, y **sin desbordamiento horizontal** — la disposición
  aprobada se mantiene.

### 4.4 · Un hallazgo del propio test · `CONFIRMED`

La primera ejecución del E2E **falló**, y por una razón que ninguna prueba de
integración habría visto: `formatClock(null)` devuelve `'In progress'`, así que
el subtítulo de la tarjeta decía `2:41 PM–In progress` sobre un viaje que nunca
abrió una parada.

Había **dos** sitios donde un trayecto se presentaba como actividad en curso, no
uno. El `Outcome` ya estaba corregido; el rango horario no.

Se corrigió condicionándolo igual, **sin tocar `formatClock`**: su
comportamiento es correcto para una parada abierta y lo usan otras pantallas.

La captura previa al arreglo está en el historial de este reporte como evidencia
de que la prueba detectó algo real.

### 4.5 · Evidencia visual

`var/screenshots/r1/`, fuera del árbol versionado:

```
escritorio-detalle-con-trayecto.png
movil-detalle-con-trayecto.png
```

Se regeneran con:

```bash
uv run pytest tests/e2e/test_r1_detail_reconciliation_browser.py
```

**Lo que muestra la de escritorio**, y es la demostración completa en una
imagen: dos tarjetas —*Client Visit* con `Outcome Completed`, y *Home* con
`10.0 mi` y `Outcome —`—, el encabezado con `10.0 mi +` y **`1 activities`**.
Dos tarjetas, una parada. El total queda explicado por lo que se ve.

La captura se toma **antes** de las aserciones, a propósito: si alguna falla, la
imagen del estado real es lo primero que hace falta, y tomarla después no la
produciría nunca.

### 4.6 · Typecheck, lint y build

```
npm run typecheck   0 errores
npm run lint:ts     0 errores
npm run build:prod  compilado (2 warnings de tamaño, preexistentes)
```

### 4.7 · Regresión completa · 1089 ejecutados · 1 fallo preexistente

```
1089 ejecutados
1073 PASS
   1 FAILED   test_provisioning_alignment (preexistente, ajeno a R-1)
   0 errores
  15 skipped
```

El único fallo es el de las 14 capacidades del rol Administrador frente a las 12
certificadas. **Falla igual con el código de `dev`** y no se toca: ese test
existe para que una ampliación de privilegio no pase sin aprobación de CER.

Ningún test de Activity Explorer, Today, viajes, jornadas, kilometraje, odómetro
ni ubicación se rompió.

### 4.8 · Resumen de lotes

| Lote | Tests | PASS | Fallos | Exit |
|---|---|---|---|---|
| Activity Explorer (dirigido) | 26 | 26 | 0 | 0 |
| Regresión sin navegador | 1089 | 1073 | 1 preexistente | 1 |
| E2E escritorio y móvil | 2 | 2 | 0 | 0 |
| typecheck · lint · build | — | — | 0 | 0 |

**Nota de ejecución.** La suite corre en **un único proceso**: `pytest-xdist` no
está instalado y `addopts` no lleva `-n`. Medido durante esta regresión, el
worker usa el **27 % de un núcleo** sobre una máquina de cuatro, a 66 tests por
minuto: el reloj lo marca el ida y vuelta a PostgreSQL, no el cálculo.
Paralelizarla exigiría una base por worker —la suite comparte una y siembra
compañías con nombres fijos—, así que es un checkpoint propio y no un flag. Se
anota, no se propone.

---

## 5 · Lo que no se tocó

Interfaces y navegación, Today H-2, `Start Work` / `End Work`, el ciclo de vida
del viaje, el kilometraje almacenado, My Activity, las reglas de zona horaria y
las fórmulas de duración.

Sobre las fórmulas: **no se cambió ninguna.** El cambio del rango horario (§4.4)
no altera `formatClock` ni `spanBetween`; decide cuándo aplicarlas, que es lo
que AC3 exige. R-2 —rotular qué mide cada tiempo— **no se ha implementado**.

---

## 6 · Estimación

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Consulta del detalle y ensamblaje | ~70 LoC | dominio | 0,6 |
| Contrato, contador y esquema del cliente | ~40 LoC | determinista | 0,4 |
| Tarjetas: clave, `Outcome` y rango horario | ~30 LoC | UI | 0,6 |
| Pruebas de integración (9) | ~330 LoC | integración | 3,6 |
| E2E escritorio y móvil, con capturas | ~190 LoC | navegador | 3,1 |
| Verificación contra el código anterior | — | — | 0,4 |
| Regresión, MR y reporte | — | — | 1,4 |
| **Total** | | | **≈ 10,1 h** |

Estimado en el diagnóstico: 3,4 h. La diferencia vuelve a estar en la
verificación, igual que en H-2: el E2E en dos tamaños, la evidencia visual y la
ejecución contra el código anterior suman 3,5 h que la estimación no contemplaba.
Es el mismo sesgo que señalé al cerrar H-2, y se repite.

---

## 7 · Git

| | |
|---|---|
| Rama | `fix/r1-user-activity-detail-reconciliation` |
| Base | `dev` en `7b597ec` |
| Commit | `2ad7230` |
| MR | **!76** · https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/76 |
| Árbol | limpio |
| Fusionado | **No.** CER certifica |

---

## 8 · Trabajo restante

1. **Validación de campo (CER)** sobre el caso real: el día de la supervisora
   observada debería reconciliar ahora.
2. **Confirmar el valor de `trip 460`** en el entorno de las capturas. Sigue
   siendo el único dato que cerraría la causa raíz con datos de producción, y no
   lo cambia esta entrega.
3. **R-2 y R-3 no se han implementado.** R-2 sube de prioridad según los datos
   del documento 002: 2h 42m de espera en destino viajan dentro de un número
   llamado *activity span*.
4. **Nada que ejecutar en el despliegue.** Sin migraciones ni semillas.
