# CER Route — Handoff para planificación

**Fecha de corte:** lunes 5 de octubre de 2026
**Semana cubierta:** lunes 28 de septiembre – domingo 4 de octubre de 2026
**Destinatario:** agente planificador de proyecto
**Fuente de los datos:** `git log` de `dev`, los reportes de `Report Delivery Rodrigo/`
y el estado real del ambiente de prueba. No hay cifras estimadas en la §2 ni en la §3.

---

## 0. Contexto mínimo para planificar

**CER Route** es una aplicación de gestión de rutas y jornadas de campo:
supervisores salen a ruta, registran odómetro con foto al empezar y al terminar,
ejecutan actividades en sitio y cierran el viaje. Encima hay un motor de
kilometraje que segmenta el recorrido con geolocalización y lo reconcilia contra
el odómetro.

**Stack:** monolito modular FastAPI + PostgreSQL + React/TypeScript servido por
Jinja. Multi-tenant por subdominio. Sin router de frontend: la ruta del servidor
elige la página de React por su nombre.

**Entornos:**

| Entorno | Dónde | Estado |
| --- | --- | --- |
| Local | `docker-compose` | operativo |
| Prueba (CER) | DigitalOcean App Platform + Postgres gestionado | operativo, con brechas de configuración (§4) |
| Producción | no existe todavía | — |

**Quién decide qué:** el desarrollo entrega en una rama con MR y un reporte.
**CER certifica y fusiona.** El agente no fusiona nunca. Esto condiciona la
planificación: un MR abierto no es trabajo terminado desde el punto de vista del
cliente, y la certificación es tiempo de calendario que no controlamos.

---

## 1. Lo que se completó la semana pasada

Cinco días de trabajo, **23 merge requests fusionados a `dev`**. Agrupados por
frente, no por día.

### 1.1. RTE02 — Accesos, roles y creación de usuarios

| Entrega | Qué resolvió | Estado |
| --- | --- | --- |
| A02 alineación de accesos | Dos roles de Route separados; capacidades sobrantes retiradas; UX de lista primero | `MERGED` |
| A02 cierre final | Contexto de producto, limpieza de capacidades; la prueba de navegador obligatoria encontró el hueco real de FR-03 | `MERGED` |
| A03 creación de usuarios | UX de creación y **re-inscripción en el mismo tenant**; cuatro requisitos a los que les faltaba la evidencia | `MERGED` |

### 1.2. RTE04 — Cierre

Validado contra la línea base certificada de A02. `MERGED`.

### 1.3. RTE05 — Ejecución de actividad y cierre de viaje

Cuatro entregas sucesivas en dos días, todas `MERGED`:

1. **Ejecución de actividad, resultado y cierre de viaje** (la entrega grande: 28 archivos)
2. **Cierre final**: `Received By` en Leave, *My Route* en el menú
3. **Realineación de UX**: el workbench pasa a ser la pantalla operativa
4. **Alineación visual**: el workbench es la grilla de tarjetas V0.7 aprobada

> Señal para planificar: RTE05 necesitó **tres iteraciones de UX después de
> estar funcionalmente completo**. La alineación visual contra un diseño
> aprobado no es gratis y conviene presupuestarla como fase propia, no como
> remate.

### 1.4. RTE06 — Geolocalización y motor de kilometraje

El frente más grande de la semana.

| Entrega | Qué resolvió | Volumen | Estado |
| --- | --- | --- | --- |
| CP0 — fechado efectivo | El invariante de solapamiento pasó **a la base**, no a Python | — | `MERGED` |
| Asignación de vehículo | Se resuelve por efectividad **en el momento del hecho**, no por la asignación vigente hoy | — | `MERGED` |
| Preflight odómetro/OCR | Diagnóstico as-built antes de construir | 1.124 líneas | `MERGED` |
| Recomendación de ejecución | Con el hueco restante de CP0 medido | — | `MERGED` |
| CP1–CP4 motor de kilometraje | Evidencia de localización y motor segmentado | **8.707 líneas, 36 archivos** | `MERGED` |
| Cierre final | Hecho `Missing` estricto, evidencia durable, routing en vivo, soak; correlación offline exacta y migración segura de notas | 2.798 líneas | `MERGED` |
| Adaptador TomTom | Routing real + reproceso de kilometrajes fallidos | 1.654 líneas (2 MRs) | `MERGED` |

### 1.5. RTE06 — Correcciones de campo (jueves y viernes)

Derivadas de hallazgos reales en dispositivos Android:

| Entrega | Qué resolvió | Estado |
| --- | --- | --- |
| Diagnóstico de hallazgos de campo | Sólo análisis, 1.002 líneas | `MERGED` |
| Correcciones de campo | F-1, odómetro, y un 409 que **perdía evidencia** | `MERGED` |
| Cierre de correcciones | «La puerta estaba en el cliente» — control que vivía en el frontend | `MERGED` |
| Cierre final de desarrollo | Cola offline acotada; lo que deja de reintentar **se cuenta** | `MERGED` |
| Corrección final de campo | «No poder leer no es saber que no hay nada»: el END expulsaba al supervisor tras la foto | `MERGED` |

Las dos últimas se verificaron **por mutación**: se rompió el arreglo, se
comprobó que el test fallaba, se restauró.

### 1.6. Excepción temporal de odómetro

Medida de estabilización autorizada por CER (Opción B). Capacidad acotada
`route.odometer.selfapprove`: el supervisor no espera a un administrador para su
excepción. **Apagada por defecto**; reversible retirando la concesión, sin
desplegar. 6 tests, incluido el de reversión.

Estado del código: `MERGED`. Estado de la activación: ver §3.1.

### 1.7. Infraestructura y herramienta

| Entrega | Qué resolvió | Estado |
| --- | --- | --- |
| Optimización de la suite de pruebas | El coste estaba en **abrir conexiones**, no en las consultas | `MERGED` |
| Catálogo de consultas SQL de verificación | 3.717 líneas; verificación manual de todos los flujos | `MERGED` |
| Preflight de jerarquía, roles y data scope | 1.151 líneas de análisis | `MERGED` |
| Conexión a la base: TLS opcional | `DB_SSL` + separador condicional en `alembic/env.py` | `MERGED` (MR !40) |
| `road_routing` | La comprobación que faltaba; fuera la caché del router | `MERGED` |

### 1.8. Trabajo del fin de semana y del ambiente de prueba

Sin commits asociados (es configuración, no código):

- Puesta en marcha del **job `PRE_DEPLOY` de migraciones** en DigitalOcean.
  Costó cuatro despliegues fallidos: `SECRET_KEY` corta, `PLATFORM_MASTER_KEY`
  con formato inválido, TLS obligatorio desde IP pública, y contraseña
  desincronizada entre la app y la base. **Resuelto y verificado.**
- Rotación de secretos de plataforma (`SECRET_KEY`, `PLATFORM_MASTER_KEY`).
- Reinicio de la contraseña de la base.
- Borrado de 18 ramas ya fusionadas.

### 1.9. Hoy, lunes 5

Runbook de migraciones documentado: `docs/MIGRACIONES_EN_APP_PLATFORM.md`.
MR !41, **fusionado por CER el mismo día a las 15:31** (`65d3892`).

---

## 2. Volumen medido (para calibrar estimaciones)

Diferencia en `dev` entre el 28 de septiembre 00:00 y el 5 de octubre 00:00:

```
186 archivos | 52.108 inserciones | 701 eliminaciones | 23 MRs
```

| Área | Líneas |
| --- | --- |
| Tests | 15.125 |
| Backend Python | 6.971 |
| Frontend React | 3.704 |
| Migraciones | 1.174 |
| **Subtotal código** | **26.974** |
| Instrucciones y reportes de entrega | ~25.100 |

**Dos datos que el planificador debería usar:**

1. **La proporción test/código es ~1,2:1.** Toda estimación de una tarea de
   backend debe incluir su test; no es un extra opcional en este proyecto.
2. **La documentación de entrega pesa casi tanto como el código.** Cada entrega
   lleva su reporte en `Report Delivery Rodrigo/`. Planificar una entrega sin su
   reporte subestima el esfuerzo a la mitad.

**Coeficientes de conversión a horas-agente** (de
`_cer_delivery/estimacion_de_tiempo_y_esfuerzo.md`):

| Tipo de trabajo | LoC/hora |
| --- | --- |
| Backend, dominio, migraciones | 150–200 |
| Integración, OCR, flujos complejos | 80–100 |
| UI, navegador, E2E | 50–70 |

**Margen de riesgo obligatorio:** determinista +10%, integraciones de terceros
+30%, automatización de navegador +50%.

---

## 3. Estado actual por frente

| Frente | Estado | Bloqueante |
| --- | --- | --- |
| RTE02 (A01, A02, A03) | `MERGED` | — |
| RTE03 | `MERGED` | — |
| RTE04 | `MERGED` | — |
| RTE05 | `MERGED`, certificado visualmente | — |
| RTE06 desarrollo | `MERGED` | — |
| RTE06 correcciones de campo | `MERGED` | — |
| **RTE06 excepción de odómetro** | `COMPLETE — apagada hasta que se conceda` | smoke test en dispositivo (§3.1) |
| Migraciones automáticas | **funcionando** en prueba | red de seguridad puesta (§4.1) |
| Runbook de migraciones | `MERGED` (MR !41) | — |
| RTE07 | no empezado | sin instrucciones recibidas |

### 3.1. Lo único que falta para cerrar la excepción de odómetro

Smoke test en un dispositivo real, START y END, más verificación de auditoría:
`decided_by` en `NULL`, acción `auto_approve`, método `manual_no_photo`.

Necesita: un teléfono, una cuenta de supervisor del tenant CER, y que alguien
conceda la capacidad desde la pantalla de permisos (maker-checker: lo piden y lo
aprueban personas distintas). **No es trabajo de agente**: es validación humana
en campo.

---

## 4. Deuda abierta y riesgos

Ordenada por lo que más duele si no se atiende.

### 4.1. El `exit 0` sigue puesto en el spec de migraciones — `CONFIRMED`

El `run_command` del job conserva el bloque de diagnóstico que termina en
`exit 0`. **Mientras esté, un fallo real de migración deja pasar el despliegue**,
que es exactamente la garantía que se quería instalar.

Esfuerzo: 2 líneas + un despliegue de verificación. **0.3 h-agente.**
Riesgo de no hacerlo: alto. Es la pieza que convierte la automatización en algo
en lo que se puede confiar.

### 4.2. TomTom nunca se configuró en el ambiente de prueba — `CONFIRMED`

El adaptador de routing está fusionado y probado contra la API real, pero el
almacén de secretos del ambiente de prueba reporta `SECRETOS GUARDADOS: 0`.
**El motor de kilometraje está degradando a su camino de reserva en ese
entorno.** Cualquier validación de kilometraje que CER haga ahí no está midiendo
el routing real.

Además, la API key de TomTom se compartió en un chat en una sesión anterior:
**está quemada y hay que rotarla.**

Esfuerzo: rotar la key + configurarla desde la pantalla de integraciones +
verificar un kilometraje real. **0.8 h-agente** (+30% por terceros ≈ **1.0 h**).
Riesgo de no hacerlo: alto, y además **silencioso** — nadie se da cuenta de que
está midiendo con el camino de reserva.

### 4.3. La base de datos está abierta a todo internet — `CONFIRMED`

El Postgres gestionado no tiene *Trusted Sources* configuradas. Acepta
conexiones entrantes de cualquier origen; lo único que protege es la contraseña.

Esfuerzo: configuración de panel + verificar que el job de migraciones sigue
conectando. **0.5 h** (+30% ≈ **0.7 h**). Hay que hacerlo en una ventana
tranquila: mal configurado, corta el acceso de la propia aplicación.

### 4.4. Conexiones `asyncpg` crudas sin cifrar — `CONFIRMED`

`app/core/platform/config_service.py:171` y
`app/core/platform/scheduler.py:83` construyen el DSN con `ssl=`, que
**`asyncpg` ignora** (espera `sslmode=`). Siguen saliendo sin cifrar y
reintentando cada 30 s.

Síntoma: degradación y ruido en los logs, no caída. Esfuerzo: helper compartido
en `app/database.py` + test, **~40 LoC → 0.3 h** (+10% ≈ **0.33 h**).

### 4.5. `BOOTSTRAP_COMPANY_SUBDOMAIN` no está puesto en DigitalOcean — `CONFIRMED`

Toma el valor por defecto `cer` mientras el tenant real es `cerroute`. Correr
`bootstrap` ahí falla con `UniqueViolationError` sobre el índice único por
nombre. **No es idempotente**: `seed_company` busca por subdominio y
`seed_roles` re-añade concesiones que alguien hubiera retirado a mano.

Esfuerzo: una variable de entorno. **0.1 h.** Importa porque bloquea cualquier
siembra futura de capacidades nuevas en ese entorno.

### 4.6. Riesgo de proceso: la cola de certificación

Esta semana se fusionaron 23 MRs. Ese ritmo depende de que CER certifique al
mismo ritmo. **Ahora mismo la cola está vacía**: el último MR abierto (!41) se
fusionó el 5 de octubre a las 15:31, el mismo día que se abrió.

Se deja anotado como riesgo porque es estructural, no porque esté activo: si en
alguna semana la planificación asume que lo entregado está cerrado mientras la
certificación se retrasa, la cola se acumula y las ramas empiezan a divergir.

---

## 5. Restricciones que la planificación debe respetar

No son preferencias. Están en `AGENTS.md` y varias tienen detrás un incidente
real.

**De proceso:**

1. Entregar = rama dedicada + commit + push + MR + **reporte** en
   `Report Delivery Rodrigo/`. Un hito verde sin documento es media entrega.
2. **Nunca fusionar.** CER certifica.
3. Nunca commitear directo a `dev`.
4. `IMPLEMENTED` no es `VALIDATED`. La evidencia ausente **nunca** se convierte
   en PASS. Lo no ejecutado se marca `NOT RUN` / `PENDING` / `NOT APPLICABLE`.
5. Nunca negarse a estimar. En **horas-agente**, con la tabla y el margen de
   riesgo declarado.
6. Terminado lo pedido: se reporta, se señala el siguiente paso y **se para**.
   Reportar no autoriza ampliar el alcance.

**De arquitectura — tareas que el planificador no debe proponer:**

- Microservicios, bus de eventos, Kafka, RabbitMQ, CQRS, GraphQL, React Router,
  otro ORM, otro gestor de estado, otro framework de frontend.
- Desactivar un control para que pase un test.
- SQLite en los tests (el esquema depende de índices únicos parciales, JSONB,
  claves foráneas compuestas y `timestamptz`).
- Confiar en controles del frontend: la cookie `user_data` es editable. La
  puerta está en el backend.
- Duplicar en un módulo un dato canónico de otro.
- Editar o borrar filas de tablas append-only (`audit_event`,
  `integration_event`, …). Corregir es **añadir una fila**.
- Aceptar del cuerpo de la petición quién actúa, en qué compañía o cuándo.
- **Simular lo que no está construido.** Una pantalla sin backend dice que no
  existe; no enseña una lista vacía ni un botón que no hace nada.
- Implementar dominios de negocio en la base de plataforma.
- Reescribir el historial de git.

**De seguridad en la operación:**

- Nunca SQL directo para rodear el maker-checker.
- Nunca modificar código para evitar un control existente.
- Nunca imprimir el valor de un secreto en logs; `bool(...)` responde si está
  definido.
- Un secreto que aparece en un chat, un ticket o una captura **está quemado**.

---

## 6. Backlog listo para planificar

Todo esto está identificado, acotado y sin dependencias de decisiones de
negocio. Las horas son **horas-agente** con su margen ya aplicado.

| # | Tarea | Tipo | Horas | Depende de |
| --- | --- | --- | --- | --- |
| 1 | Quitar el `exit 0` del spec y verificar despliegue verde | infra | 0.33 | — |
| 2 | `BOOTSTRAP_COMPANY_SUBDOMAIN=cerroute` en DO | config | 0.1 | — |
| 3 | Rotar API key de TomTom y configurarla en prueba | integración | 1.0 | key nueva del proveedor |
| 4 | Helper `sslmode=` para `asyncpg` crudo + test | backend | 0.33 | — |
| 5 | Trusted Sources de la base | infra | 0.7 | ventana tranquila |
| 6 | Smoke test de la excepción de odómetro (START/END) | validación humana | — | dispositivo + supervisor + concesión |

**Subtotal agente: ≈2.5 h.** El #6 no es trabajo de agente.

### Lo que no está en esta tabla porque falta una decisión

- **RTE07**: no hay instrucciones recibidas. Es el siguiente bloque natural de
  producto y probablemente el grueso de la semana, pero no se puede planificar
  sin el documento de CER.
- **Deuda de UX de RTE05/RTE06**: no hay hallazgos abiertos, pero el patrón de
  la semana pasada —tres iteraciones visuales después de estar funcional— sugiere
  reservar capacidad si CER revisa pantallas.

---

## 7. Qué debería preguntar el planificador antes de cerrar la semana

1. **¿Llegan las instrucciones de RTE07 esta semana?** Determina si la semana es
   de producto nuevo o de consolidación. Con ~2.5 h de backlog cerrado, sin
   RTE07 la semana queda mayormente vacía de trabajo de agente.
2. ~~¿Cuándo certifica CER los MRs abiertos?~~ **Resuelta:** no hay MRs
   abiertos. Todo lo entregado está fusionado en `dev`.
3. **¿Hay dispositivo y cuenta de supervisor disponibles para el smoke test?**
   Es lo único que separa la excepción de odómetro de estar cerrada.
4. **¿Se valida kilometraje en el ambiente de prueba esta semana?** Si sí, el
   #3 (TomTom) deja de ser deuda y pasa a ser bloqueante.
