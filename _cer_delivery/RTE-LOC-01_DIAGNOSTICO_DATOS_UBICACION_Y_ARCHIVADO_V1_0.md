# RTE-LOC-01 — Diagnóstico de fuentes de ubicación, captura y archivado mensual

**Proyecto:** CER Route  
**Tipo:** Instrucción de diagnóstico / discovery (NO implementación)  
**Versión:** 1.0  
**Estado:** Lista para ejecución por programador y agente técnico  
**Dependencias futuras:** RTE-LOC-02 (captura y almacenamiento), RTE-LOC-03 (archivo mensual)  
**Autoridad:** Product Owner (PO) conserva las decisiones de producto; el agente informa hechos y recomienda, sin activar seguimiento ni ejecutar migraciones.

## 1. Context

CER Route necesita una base de datos de puntos de ubicación que permita, en futuras fases, reconstruir trayectos, visualizar un historial por alcance autorizado y mejorar la precisión de las estimaciones de distancia para apoyar la asignación de combustible por usuario.

La fase aprobada **por ahora** comprende capturar ubicaciones, almacenarlas temporalmente durante aproximadamente un mes y archivarlas de forma recuperable mediante un job; **no** desarrollar todavía mapas históricos, reconstrucción de rutas ni cálculos de millas, consumo o asignación de combustible.

El PO solicita iniciar con **un diagnóstico de los datos y mecanismos que YA existen en el repositorio y bases de CER Route**. Hay informes anteriores que mencionan jornadas, viajes, actividades, coordenadas, Route Map Viewer, registros temporales y un scheduler de plataforma. Úsalos como pistas para investigar, **no como prueba de existencia o calidad actual**. No asumas nombres de tablas, endpoints ni capacidades del cliente móvil sin inspección.

Arquitectura de referencia: CER Route es una aplicación independiente; mantener separación modular, API-First, aislamiento por tenant y compatibilidad con la navegación/UX aprobada. No contaminar el Core con reglas del dominio de ubicaciones.

## 2. Objective

Entregar evidencia técnica suficiente para responder, sin suposiciones:

1. **Qué datos geográficos se almacenan hoy**, en qué estructuras, cuándo y con qué calidad, relación y volumen.
2. **Qué datos acompañan cada punto** (usuario, tenant, jornada, actividad, viaje, dispositivo, origen, fechas/zonas, precisión) y qué campos faltan.
3. **Cómo llegan actualmente las ubicaciones** desde Web/Mobile hasta la base de datos, incluyendo permisos, captura con app activa, posibles límites en segundo plano y desconexión.
4. **Qué se puede reutilizar** para un repositorio operativo de puntos y para un respaldo mensual íntegro, recuperable y privado.
5. Qué condiciones, riesgos y decisiones debe aprobar el PO antes de autorizar RTE-LOC-02 y RTE-LOC-03.

**Entregable principal:** diagnóstico AS-IS y propuesta TO-BE acotada, sin programar.

## 3. Confirmed / Assumptions / Pending decisions

| Clasificación | Enunciado |
|---|---|
| **CONFIRMED (PO)** | El desarrollo comienza por diagnóstico; la captura y el respaldo mensual serán pasos posteriores. |
| **CONFIRMED (PO)** | El objetivo de largo plazo incluye estimar mejor los desplazamientos para apoyar la asignación de combustible. |
| **CONFIRMED (PO)** | Interesa almacenar información de ubicación disponible con suficiente contexto para uso futuro y un histórico consultable. |
| **CONFIRMED (PO)** | Se desea conservar un período operativo de aproximadamente un mes, exportarlo a un destino configurable y depurar luego el almacenamiento operativo. |
| **CONFIRMED (PO)** | No se implementarán en esta fase rutas reconstruidas, gráficos, millaje calculado ni asignaciones de combustible. |
| **ASSUMPTION TO VERIFY** | CER Route dispone de fuentes GPS asociadas con WorkSession, Trip, Activity/ActivityExecution u otras entidades. |
| **ASSUMPTION TO VERIFY** | Existe infraestructura de scheduler y despliegue en DigitalOcean que podría reutilizarse para el futuro archivado. |
| **DECISION REQUIRED** | Captura durante toda la jornada Start Work–End Work, incluidas pausas sin actividad y segundo plano cuando sea técnicamente posible, o alcance más limitado. No darlo por aprobado por inferencia. |
| **DECISION REQUIRED** | Intervalo de muestreo, estrategia por movimiento, tolerancia a batería/datos y operación offline. |
| **DECISION REQUIRED** | Mes calendario frente a ventana móvil de 30/31 días; margen para datos tardíos; conservación del histórico archivado y política de eliminación. |
| **DECISION REQUIRED** | Destino persistente del archivo y autoridad administrativa para acceder/restaurar; alcance de monitoreo visible, avisos y requisitos legales por jurisdicción. |

## 4. Scope — SOLO RTE-LOC-01

### A. Inventario AS-IS de captura y datos

Inspeccionar código, migraciones, modelos, schemas, APIs, servicios, pantallas y configuración, documentando rutas/identificadores/commit de evidencia. Identificar, **si existen**, estas fuentes:

- WorkSession / Start Work / End Work y sus datos de ubicación o zona horaria.
- Trip / movimientos de odómetro / trayectos / coordenadas de inicio y destino.
- Activity y ActivityExecution, visitas, resultados, notas, puntos GPS, enlaces de ruta y mecanismos del Route Map Viewer.
- Registro de ubicaciones por intervalos, eventos GPS, geofence, mapas y tracking; duplicaciones entre sistemas.
- Localización en navegador o dispositivo, permisos, colas offline, sincronización/reintentos y timestamps de captura vs recepción.
- Jobs, cron, scheduler, task queues, storage de archivos y herramientas de exportación ya disponibles.

No asumir que el usuario dispone de puntos intermedios por el hecho de existir coordenadas en inicio/cierre de una actividad. Separar **puntos de evento** de **traza periódica**.

### B. Catálogo de campos geográficos y contexto

Construir una matriz por **fuente real** con las columnas:

`source_module | table_or_endpoint | exact_field | data_type | nullable | semantic_meaning | acquisition_event | timestamp_source | tenant_scope | user_relation | session_relation | trip_activity_relation | data_quality | sensitivity | existing_usage | evidence`.

Investigar si se dispone de: identificadores de tenant, usuario, jornada, actividad, viaje y punto; latitud, longitud; precisión horizontal (`accuracy_m`); timestamps de origen y recepción; offset/time zone; fecha operativa; velocidad, rumbo y altitud **solo si ya existen y justifican utilidad**; origen GPS/dispositivo/manual/derivado; estado de permiso; calidad de punto; identificador de evento para deduplicación; relación con odómetro existente.

**Importante:** “capturar la mayor cantidad de registros” significa preservar la mejor información *necesaria y útil*, no recopilar indiscriminadamente telemetría, contactos, redes Wi-Fi, IP permanente, identificadores persistentes de hardware o PII adicional. Distinguir dato obligatorio, opcional y no recomendado.

### C. Diagnóstico cuantitativo y calidad (solo lecturas)

Sobre una base de prueba representativa o consultas de agregados autorizadas, medir por fuente:

- Registros disponibles por día/mes, por tipo de evento y por tenant **agregados** (no listar empleados ni coordenadas personales).
- Cobertura: porcentaje de jornadas, viajes y actividades con al menos una coordenada válida; proporción con timestamps/precision/usuario/tenant presentes.
- Distribución de puntos por jornada y brechas temporales, **si existe traza periódica**; caso contrario establecer GAP sin inventar porcentajes.
- Validez de latitud/longitud, coordenadas nulas o `0,0`, precisión ausente o deficiente, velocidad inverosímil, duplicados, cronología fuera de orden y muestras recibidas tarde.
- Inconsistencias entre `captured_at` y `received_at`, offsets perdidos, `session_date` y jornadas que cruzan medianoche; compatibilidad con columnas `timestamp with time zone` donde aplique.
- Densidad estimada según frecuencia de captura propuesta y duración promedio de jornada, **con fórmulas parametrizadas** (usuarios concurrentes, horas, intervalo, bytes/punto); declarar supuestos, no simular hechos.

Si la base local es una copia no actualizada o faltan permisos, marcar `PENDING VALIDATION/BLOCKED`, indicando qué consulta necesita quien tenga acceso. **No exportar puntos reales ni PII a los MD, logs, capturas o anexos.** Usar ejemplos sintéticos para demostrar formato.

### D. Diagnóstico Web/Mobile

Determinar el tipo real de cliente (Web responsive, PWA, híbrido, nativo) y documentar, con referencia al código:

1. En qué eventos se solicita la ubicación y qué ocurre cuando el usuario niega/revoca el permiso.
2. Qué precisión, actualización y frecuencia efectiva entrega el cliente; si se usa `getCurrentPosition`, `watchPosition` u otro mecanismo.
3. Qué sucede con pantalla bloqueada, app minimizada/cerrada, suspensión del sistema, modo ahorro y pérdida de señal.
4. Si hay sincronización offline y prevención de pérdida/duplicación de puntos.
5. Qué cambios serían imprescindibles para una captura Start Work–End Work y cuáles **no** son garantizables por el navegador/SO.
6. Cómo detener captura tras End Work, logout, revocación de autorización o cambio de usuario/tenant.

Documentar restricciones por plataforma con hechos verificables; no prometer seguimiento continuo en segundo plano si no es viable.

### E. Seguridad, privacidad y gobierno

Determinar controles existentes y brechas para:

- Aislamiento por tenant en ingestión, almacenamiento, exportación y recuperación.
- Asociación confiable de punto al usuario autenticado y jornada autorizada; **no confiar** en `tenant_id` o `user_id` enviados por el cliente sin contrastar.
- Alcance jerárquico actual (CEO, COO, Regional Manager, Supervisor/On-Site; Sales bajo CEO), sin conceder lectura automática de trazas por tener acceso a otros reportes.
- Datos de ubicación como PII sensible: finalidad informada al trabajador, acceso mínimo, cifrado, auditoría de consultas/exportaciones y retención/eliminación conforme a política y jurisdicción.
- Riesgos de falsificación de coordenadas, replay, datos antiguos, manipulación del reloj, multi-dispositivo, abuso de endpoints y fugas por logs.
- Separación entre GPS histórico y odómetro/millaje oficial existente: **no cambiar los cálculos actuales**.

Anotar qué requisitos legales o avisos requieren revisión humana; no concluir que un aviso o consentimiento específico sea siempre suficiente en todos los estados.

### F. Archivado mensual y recuperación: diseño, NO implementación

Inventariar mecanismo real de DigitalOcean (App Platform, scheduler interno, Scheduled Jobs, settings, secretos, object storage, buckets, API de archivos). Si existe una App Spec en el repo, **compararla con la configuración real solo si se dispone de acceso**; una spec antigua no demuestra despliegue.

Evaluar al menos estas cuestiones:

- Destino configurable **persistente** (p. ej. almacenamiento de objetos privado, si ya está habilitado), evitando el disco efímero del contenedor; NO seleccionar proveedor ni crear bucket sin aprobación.
- Esquema de partición temporal y por tenant, nombre de archivo, formato exportable/recuperable (CSV comprimido, Parquet u otro justificable), versión de esquema, manifiesto, recuento y checksum.
- Ventana de corte, captura tardía y sesiones nocturnas; consistencia transaccional o snapshot durante exportación.
- Validación de exportación, lectura de verificación/restauración y trazabilidad por archivo/tenant/período.
- Idempotencia del job, concurrencia entre réplicas, reintentos, alarmas, costos estimados y manejo de cortes parciales.
- Política de purga: **no ejecutar `TRUNCATE` indiscriminado**. Proponer eliminación selectiva/particiones solo después de confirmar copia íntegra y recuperable; jamás borrar meses, tenants o puntos no exportados.
- Lectura futura del histórico archivado sin prometer consultas interactivas directas a archivos si no existe un índice/catálogo de recuperación.

Registrar explícitamente si hoy ya se cuenta con suficiente información para generar un histórico *solo de eventos* y qué haría falta para un histórico *de trayectoria continua*. Son productos de datos distintos.

## 5. Out of Scope / Do Not Change

**No autorizado en este checkpoint:**

- Crear/modificar tablas, migraciones, índices, endpoints, jobs, variables de entorno ni pantallas.
- Activar GPS periódico, seguimiento silencioso o envío de ubicaciones desde dispositivos reales.
- Ejecutar un job de respaldo, descargar ubicaciones personales, hacer `TRUNCATE`, `DELETE`, exportaciones reales o restauraciones en producción.
- Construir visor de mapas, map matching, reconstrucción, comparación de odómetro, cálculo de MPG, galones o dinero.
- Alterar Start Work, End Work, Activity, Trip, millas oficiales, Route Map Viewer, navegación actual, roles y permisos aprobados.
- Implementar recursos o cron de DigitalOcean ni sustituir la App Spec real por una versión desactualizada.

Cualquier prueba que escriba datos o requiera usar ubicación real debe proponerse aparte y contar con autorización y entorno controlado.

## 6. Casos que debe evaluar el diagnóstico

| Caso | Pregunta que debe contestarse con evidencia |
|---|---|
| LC-01 | ¿Se registra algún punto al iniciar o finalizar una jornada? ¿Con qué precisión y timestamp? |
| LC-02 | ¿Hay datos durante un viaje o solamente al comienzo y al final? |
| LC-03 | ¿Existen ubicaciones asociadas a actividades sin jornada/viaje válido? |
| LC-04 | ¿Qué ocurre sin permiso GPS, sin señal, offline o con app minimizada? |
| LC-05 | ¿Qué registros se producen si cruza medianoche, estado o zona horaria? |
| LC-06 | ¿Cómo se evitan duplicados ante reintentos y dispositivos múltiples? |
| LC-07 | ¿Qué ocurriría si el archivo mensual falla, queda incompleto o llega información tardía? |
| LC-08 | ¿Se puede consultar/restaurar un mes archivado sin mezclar tenants? |
| LC-09 | ¿Qué datos faltan para estimaciones de distancia futuras SIN calcular combustible ahora? |
| LC-10 | ¿Quién podría visualizar/exportar historial y cómo se auditaría cada acceso? |

## 7. Recommended report structure (mandatory deliverable)

Entregar un solo MD de resultados denominado:

`RTE-LOC-01_AS_IS_GPS_DATA_AND_ARCHIVE_DIAGNOSTIC_REPORT.md`

Secciones mínimas del informe:

1. **Executive summary y decisión de readiness**: `READY / READY WITH GAPS / BLOCKED`, sin declarar completado lo no demostrado.
2. **Repository & environment baseline**: rama/commit, versiones de migración, entornos realmente observados, fecha de inspección, limitaciones de acceso.
3. **Source inventory**: matriz de tablas, modelos, rutas de código, APIs y flujos Web/Mobile, con evidencia por fila.
4. **Data dictionary**: campos existentes y relaciones; distinguir `AS-BUILT`, `PARTIAL`, `NOT IMPLEMENTED`, `PENDING VALIDATION`.
5. **Data quality & volume**: agregados, cobertura, tasas de nulos/duplicados, volumen estimado y origen de cada cifra; ninguna coordenada personal en claro.
6. **Gap analysis Expected → Implemented → Evidence → Gap → Impact**, incluyendo diferencia entre evento y captura periódica.
7. **Mobile/background feasibility**: límites confirmados, riesgos de batería, permisos y offline.
8. **Security/privacy/audit**: controles actuales, nuevos riesgos y validaciones legales/operativas pendientes.
9. **Archive feasibility**: opciones justificadas de almacenamiento, job, retención, integridad y recuperación; recomendar sin desplegar.
10. **Proposed minimum data contract**: tabla de campos `required / optional / derived / prohibited` y justificación; no generar DDL en CP1.
11. **Decisions required from PO**: máximo 5–8 decisiones materiales, con opción, beneficio, riesgo e impacto y recomendación.
12. **Next checkpoints**: propuesta acotada para RTE-LOC-02 y RTE-LOC-03, dependencias, criterios y pruebas requeridas.
13. **Evidence appendix**: referencias a archivos/commits, SQL `SELECT` read-only (sin resultados sensibles), resultados de tests existentes o verificaciones no invasivas, y bloqueos.

Para cada conclusión importante indicar `CONFIRMED` (con evidencia) o `ASSUMPTION / PENDING VALIDATION`. No afirmar que una función existe solo porque el código contiene un nombre parecido.

## 8. Acceptance Criteria — RTE-LOC-01

- **AC-01:** Inventario verificable de todas las fuentes actuales de ubicación investigadas, incluidas ausencias y caminos descartados.
- **AC-02:** Catálogo campo-a-campo de las fuentes existentes y de los datos contextuales disponibles; evidencia de relaciones con tenant, usuario, jornada, actividad y viaje.
- **AC-03:** Diagnóstico de cantidad, cobertura y calidad basado en datos agregados reales o clasificación clara de los bloqueos para obtenerlos.
- **AC-04:** Mapa de flujo de ubicación Web/Mobile → API → persistencia, indicando si existe o no captura periódica y viabilidad de segundo plano.
- **AC-05:** Evaluación de multitenancy, roles/scope, privacidad, retención, audit trail y controles server-side.
- **AC-06:** Propuesta comprobable de exportación mensual y recuperación, con mecanismo de eliminación segura condicionado a verificación, sin elegir un destino no aprobado.
- **AC-07:** Diagnóstico reconoce explícitamente necesidades futuras de estimación de trayectos/combustible sin implementarlas ni alterar millas oficiales.
- **AC-08:** Matriz Expected/Implemented/Evidence/Gap/Impact; clasificación y decisiones pendientes para el PO.
- **AC-09:** Informe entregado **sin modificaciones de código, migraciones, envíos GPS, exportaciones personales ni despliegues**.
- **AC-10:** RTE-LOC-02 y RTE-LOC-03 definidos solo como próximas unidades de trabajo, sin iniciar su ejecución.

## 9. Tests / Verification required

Solo pruebas no destructivas y lectura del sistema:

- Consultas de metadatos de BD, esquema, constraints, índices y claves foráneas.
- Estadísticas `SELECT` agregadas sobre datos de prueba o entorno autorizado, sin copiar datos de ubicación reales al informe.
- Inspección de rutas de código, trazabilidad de endpoints/eventos, permisos y tests GPS ya existentes.
- Revisión de configuración de runtime/cron/bucket **sin mostrar secretos** y con anotación explícita cuando no se tiene acceso.
- Verificar ausencia de cambios con `git status`, `git diff` y resultados de los comandos de inspección.

No se requiere crear nuevas pruebas automatizadas en este checkpoint. Si una capacidad no puede evaluarse sin modificar datos o utilizar GPS de una persona, reportar `PENDING VALIDATION` con un plan de prueba para aprobación posterior.

## 10. Exit criterion and handoff

Terminar el trabajo **al entregar el MD diagnóstico**. No iniciar RTE-LOC-02 ni RTE-LOC-03 hasta que el PO revise hallazgos, valide las decisiones pendientes y emita la siguiente autorización.

La instrucción pretende responder qué podemos almacenar **con lo que CER Route ya recopila hoy** y cuál es la ruta mínima para capturar más puntos en el futuro sin comprometer privacidad, integridad ni compatibilidad.
