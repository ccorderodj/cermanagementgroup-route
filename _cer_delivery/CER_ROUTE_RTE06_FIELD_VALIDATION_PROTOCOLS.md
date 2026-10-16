# RTE06 — Protocolos de validación en campo (Items D, E y F)

**Para:** quien ejecute la validación con dispositivos y datos reales.
**Por qué existe:** los Items D, E y F del cierre de RTE06 no se pueden ejecutar
desde un entorno de desarrollo. Necesitan un iPhone y un Android físicos, un
recorrido real en la zona de operación de CER y una muestra de piloto. Dejar
escrito "pendiente" sin decir **cómo** se cierra lo convierte en una tarea sin
dueño, así que aquí están los tres protocolos, listos para ejecutar y con la
forma exacta en que hay que registrar el resultado.

Nada de este documento se puede rellenar desde desarrollo. Los huecos se
rellenan midiendo.

---

## Item D — Validación en dispositivo físico

### Qué hace falta

- un iPhone con Safari, un Android con Chrome;
- un tenant de pruebas de CER con un supervisor y un vehículo asignado;
- el motor de routing desplegado (si no lo está, el kilometraje se quedará
  pendiente y eso **no** es un fallo de esta validación: anótalo y sigue);
- acceso a la base para leer `location_fix` y `missing_location_event`.

### Advertencia que hay que respetar al escribir el resultado

**No se puede afirmar captura en segundo plano.** Ni Safari ni Chrome dan
geolocalización a una pestaña en segundo plano o con la pantalla bloqueada. Lo
que hay que registrar es **lo que de verdad ocurre** —que el evento queda
pendiente y se resuelve al volver al primer plano, o que acaba en Missing—, no
lo que sería deseable.

### Los escenarios, en orden

| # | Escenario | Qué hacer | Qué registrar |
|---|---|---|---|
| D-1 | Permiso concedido | Start Work con el permiso ya concedido | `evidence_level` de la fila, precisión, segundos entre pulsar y que la fila exista |
| D-2 | Primer permiso | Desinstalar datos del sitio, Start Work, ver el aviso de privacidad, conceder | Que el aviso aparezca **una vez**; que no reaparezca en la acción siguiente |
| D-3 | Permiso denegado | Denegar y hacer el día entero: Start Work, Start Trip, Change Plan, Arrived, Complete, End Work | Que **ninguna** acción se bloquee; que no aparezca ningún mensaje de GPS; un `missing_location_event` por evento |
| D-4 | Paso a segundo plano | Start Trip, mandar el navegador al fondo 60 s, volver | Si el punto llegó, con qué nivel; si no, si quedó pendiente en IndexedDB o acabó en Missing |
| D-5 | Pantalla bloqueada | Start Trip, bloquear 60 s, desbloquear | Igual que D-4. **Esperado:** sin captura mientras está bloqueado |
| D-6 | Vuelta al primer plano y acción nueva | Tras D-5, hacer Arrived | Que la acción funcione con normalidad y su punto se capture |
| D-7 | Sin red durante la acción | Modo avión, Start Trip, esperar 30 s, quitar modo avión | Que el punto aparezca en la base **después**, con su `device_captured_at` original |
| D-8 | Cierre y reapertura | Con red cortada capturar, cerrar el navegador del todo, reabrir, restaurar red | Que el punto llegue. Es la durabilidad del Item A en hardware real |
| D-9 | Frontera de End Work | End Work con GPS lento, observar que la jornada cierra ya | Que `work_session.status` sea `ended` de inmediato; si el punto de `end_work` llega después, dentro de qué ventana |
| D-10 | Permiso revocado a media jornada | Conceder, hacer Start Trip, revocar en ajustes del sistema, hacer Arrived | Que Arrived funcione; que su evento acabe en Missing con `reason_code = permission_denied` |

### Plantilla de registro

Una fila por escenario y por plataforma. Sin interpretar: lo observado.

```
plataforma        | iOS 17.x Safari  /  Android 14 Chrome 1xx
escenario         | D-n
accion bloqueada  | si / no
nivel observado   | fresh / degraded_cached / recovered / (missing)
precision (m)     | 
segundos hasta la fila |
estado en servidor| location_fix id=... / missing_location_event id=... reason=...
observaciones     | 
```

### Criterio de cierre

Item D queda `CONFIRMED` cuando los diez escenarios están registrados en **las
dos** plataformas y ninguna acción operativa quedó bloqueada. Un escenario en
el que el punto no llega **no** impide el cierre: lo que se valida es que el
trabajo del supervisor no se detiene y que el servidor se entera.

---

## Item E — Muestreo de precisión en campo

### Qué hace falta

- un recorrido representativo de la zona de operación real de CER, no una
  oficina: la mezcla de urbano denso, interior de edificio, aparcamiento y
  carretera abierta es justo lo que cambia los números;
- al menos **40 capturas** repartidas entre los siete eventos del ciclo de
  vida, en al menos dos jornadas distintas y a dos horas distintas del día.

Cuarenta no es un número mágico: es el mínimo con el que una proporción de
Missing del 10 % se distingue de una del 25 %. Con menos, la muestra no puede
sostener una decisión sobre umbrales.

### Qué medir en cada captura

```sql
SELECT event_kind, evidence_level, accuracy_m, source_age_seconds,
       device_captured_at, server_received_at,
       server_received_at - device_captured_at AS retraso
FROM location_fix
WHERE company_id = :tenant_de_pruebas
ORDER BY device_captured_at;

SELECT event_kind, reason_code, permission_state,
       rejected_candidate, attempts
FROM missing_location_event
WHERE company_id = :tenant_de_pruebas;
```

`attempts` lleva la duración de cada etapa, así que la **latencia de
adquisición** sale de ahí sin instrumentar nada más.

### Los cuatro umbrales a revisar, y qué dato decide cada uno

| Umbral | Valor actual | Qué dato lo decide |
|---|---|---|
| `fresh_timeout_seconds` | 10 | percentil 90 de la duración de la etapa `current` en los intentos que **acabaron bien**. Si el p90 es 14 s, 10 está tirando capturas que habrían llegado |
| `cached_max_age_seconds` | 300 | **el más dudoso de los cuatro.** Distribución de `source_age_seconds` de los puntos cacheados **y** cuánto se mueve el vehículo en ese tiempo. Si un punto de 5 minutos está a 4 km del evento, 300 es demasiado |
| `cached_max_accuracy_m` | 500 | distribución de `accuracy_m` de los cacheados; y si con 500 m dos paradas distintas se vuelven indistinguibles en la zona real |
| `recovery_window_seconds` | 180 | proporción de `recovered` sobre el total de recuperaciones iniciadas. Si casi ninguna tiene éxito, la ventana no sirve para lo que se puso |
| `snap_radius_m` | 1.000 | **añadido tras medir**: cuántas paradas legítimas están a más de 1 km de vía cartografiada en la zona de CER. Si alguna lo está, subirlo; si ninguna se acerca, bajarlo estrecha la defensa |

### Criterio de cierre

Item E queda `CONFIRMED` cuando los cinco umbrales tienen su dato al lado y una
decisión escrita —**mantener** o **ajustar a X**— con la razón. Mantener un
valor es una decisión válida; lo que no vale es dejarlo sin dato.

Después, los umbrales dejan de describirse como provisionales en el reporte.

---

## Item F — Distribución de niveles de evidencia

### Qué hace falta

La muestra del Item E sirve, si llega a 40 capturas. Si se quiere una
distribución de piloto, hacen falta al menos **una semana** de uso real con dos
supervisores.

### La consulta

```sql
SELECT evidence_level, count(*),
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM location_fix WHERE company_id = :tenant GROUP BY 1
UNION ALL
SELECT 'missing', count(*),
       NULL
FROM missing_location_event WHERE company_id = :tenant;
```

El `missing` va aparte a propósito: **no es un nivel de evidencia** y sumarlo en
el mismo porcentaje sería contradecir §11.

### Qué patologías buscar

| Patrón | Qué significa | Qué hacer |
|---|---|---|
| Missing por encima del ~15 % | el modelo por etapas no está funcionando en esa zona | revisar permisos y `recovery_window_seconds` |
| `degraded_cached` dominando el uso normal | la etapa 1 casi nunca acierta | subir `fresh_timeout_seconds`; revisar si el dispositivo tiene GPS activo |
| `recovered` casi en cero **con** Missing alto | la ventana de recuperación no sirve | acortarla y aceptar el Missing antes, o alargarla si los intentos mostraban progreso |
| `fresh` con latencia p90 muy alta | está acertando pero tarde | es un problema de experiencia, no de datos: la acción no espera, así que no bloquea nada |

### Criterio de cierre

Item F queda `CONFIRMED` con la distribución, el tamaño de muestra y el entorno
documentados, y una frase por patología: presente o ausente.

**No se inventan porcentajes.** Si la muestra es pequeña, se dice el tamaño y se
llama muestra pequeña.

---

## Qué pasa con el cierre de RTE06 mientras estos tres no se ejecuten

El criterio 28 del cierre pide que no quede ningún `PENDING VALIDATION` dentro
del alcance. Con D, E y F sin ejecutar, ese criterio **no se cumple**, y
decirlo es parte del trabajo: son los tres puntos que separan "implementado y
probado en laboratorio" de "validado en el campo de CER".

Los otros tres items del cierre —A, B y C— sí están cerrados con evidencia
ejecutada, y están en el reporte 002.
