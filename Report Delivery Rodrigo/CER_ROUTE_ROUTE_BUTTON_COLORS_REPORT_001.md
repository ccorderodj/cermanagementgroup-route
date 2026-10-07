# CER Route — Color de los botones `End Work` y `Back`
## Reporte 001

**Origen:** petición directa sobre la pantalla `My Route`
**Rama:** `fix/route-button-colors` (desde `dev`)
**Fecha:** 2026-10-07

---

## 1. Resultado

Los dos botones usaban `variant="ghost"`, que no dibuja fondo ni borde: se leían
como texto plano y no como botones.

| Botón | Antes | Ahora |
|---|---|---|
| `End Work` (workbench) | `ghost` | **`destructive`** |
| `Back` (contexto del viaje) | `ghost` | **`secondary`** |

Las dos variantes salen del sistema de diseño y usan **tokens de color**, no
`slate-*` ni hexadecimales — invariante 12 de `AGENTS.md`.

---

## 2. La decisión, y la objeción que planteé

CER eligió `destructive` para `End Work`. **Señalé la objeción antes de
aplicarlo**: en este sistema el rojo está reservado para lo peligroso o
irreversible, y terminar la jornada es una acción normal, no un riesgo.

La decisión es de CER y se aplica. Queda registrada aquí para que, si alguien
se la encuentra dentro de seis meses y le extraña, sepa que fue deliberada y
no un descuido.

A favor de la elección, y es un argumento real: cerrar la jornada **sí** es la
acción con más consecuencias de esa pantalla. Con un viaje sin llegar, queda
registrado como interrumpido y no se le inventa una llegada — y eso no se
deshace.

Para `Back` se eligió `secondary`, que era mi recomendación salvo por el matiz
de `outline`: se ve como botón sin disputarle el sitio a `Start Trip`, que es
la acción principal de esa pantalla.

---

## 3. Qué **no** cambió

* Ningún texto, ninguna posición, ningún tamaño: los dos botones conservan su
  `h-12 w-full`.
* Ninguna lógica. `End Work` sigue pasando por la cola durable y sigue
  recibiendo 409 con una parada sin resolver.
* `End Work` sigue **sin** ofrecerse desde la pantalla de contexto (FR-11) ni
  mientras se conduce (PD-03). El color no cambia dónde aparece.

---

## 4. Validación

| Lote | Tests | Fallos | Err | Exit |
|---|---:|---:|---:|---:|
| `test_rte05_workbench_browser.py` | 24 | 0 | 0 | 0 |
| `test_trip_and_odometer_browser.py` | 6 | 0 | 0 | 0 |
| `test_activity_execution_browser.py` | 15 | 0 | 0 | 0 |
| `test_rte04_closure_browser.py` | 5 | **1** | 0 | 1 |

* **Frontend** `npm run check` → typecheck **0 errores**, lint **0 errores**
* **Frontend** `npm run build:prod` → compilado; los tests corren contra ese bundle

### El fallo, y por qué no es mío

`test_a_rejected_end_work_does_not_come_back_from_the_queue` falla: tras un
`End Work` rechazado, la pantalla no vuelve al workbench.

**No lo causó este cambio, y está demostrado, no supuesto.** Guardé mis
modificaciones, reconstruí el bundle desde `dev` limpio y ejecuté ese mismo
test:

```text
=== SIN mis cambios (dev puro) ===
FAILED test_a_rejected_end_work_does_not_come_back_from_the_queue
1 failed in 43.72s
```

Falla igual. Es **deuda preexistente en `dev`**, y la reporto aquí porque
apareció mientras validaba, no porque forme parte de este delta.

No la arreglé: diagnosticarla es un trabajo aparte —toca el comportamiento de
la cola durable ante un rechazo, no el color de un botón— y mezclarla con un
cambio visual haría ilegibles las dos cosas. **Si quieres, la investigo como
entrega propia.**

---

## 5. Asuntos restantes

**Dentro de este alcance: ninguno.**

**Hallazgo incidental, con su acción:** el fallo de `test_rte04_closure_browser`
está en `dev` hoy. Conviene decidir si se investiga o se acepta como conocido;
dejarlo sin clasificar hace que la próxima regresión roja parezca normal.

---

## 6. Estado propuesto

```text
BUTTON COLORS COMPLETE / READY FOR CER REVIEW
```

---

## 7. Estimación del esfuerzo

| Tarea | Estado | Complejidad | Horas-agente |
|---|---|---|---|
| Localizar los botones y las variantes disponibles | `DONE` | análisis | 0,2 |
| Aplicar las dos variantes, con el motivo escrito | `DONE` | UI | 0,2 |
| Typecheck, lint y build | `DONE` | ejecución | 0,2 |
| Regresión de navegador (50 tests) | `DONE` | ejecución | 0,6 |
| Aislar el fallo preexistente contra `dev` limpio | `DONE` | diagnóstico | 0,4 |
| Reporte | `DONE` | documentación | 0,2 |
| **Total** | | | **≈ 1,8 h-agente** |

---

## 8. Siguiente paso

Desplegar. Es sólo frontend, así que necesita el bundle reconstruido — el job
ya hace `build:prod`.
