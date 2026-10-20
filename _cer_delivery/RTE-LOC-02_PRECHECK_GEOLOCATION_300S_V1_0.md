# RTE-LOC-02-PRECHECK | Validación focalizada antes de implementar GPS periódico

**Tipo:** Discovery / READ-ONLY | **Versión:** 1.0 | **Entrega:** un MD breve | **NO autoriza código, DDL, migraciones, despliegue ni cambios de configuración.**

## Contexto aprobado (NO volver a debatir)

- CER Route **ya exige geolocalización** para operar y el PO confirma que **ya existe y se acepta un aviso** de captura durante el uso. **Verificar su implementación actual; NO diseñar otro flujo de consentimiento por defecto.** El diagnóstico anterior observó un aviso no conectado: comprobar si fue corregido desde entonces.
- Los registros `location_fix` **siguen intactos**: Start Work, Start Trip, Arrived, eventos de actividad y End Work. No cambiar millaje, Route Engine, UX aprobada ni reglas de jornada.
- Nueva captura **cada 300 segundos inicialmente**, durante WorkSession activa y mientras la web esté en condiciones de obtener GPS. La captura en segundo plano no está garantizada.
- El intervalo será **configurable desde UX por usuario autorizado** y por tenant. La configuración NO debe alterar el motor actual de eventos.
- Los puntos periódicos irán a **tabla independiente**; una vista/consulta lógica unirá ambas fuentes por `company_id`, `work_session_id` y tiempo para reconstrucción histórica por viaje. Sin calcular rutas, millas ni combustible en este checkpoint.
- Archivo mensual y purga segura son RTE-LOC-03; no implementarlos ahora.

## Baseline que YA conocemos (no repetir auditoría general)

RTE-LOC-01 inspeccionó `dev@4bc266e` (20-Oct-2026): `location_fix`, `missing_location_event`, `work_session`, `trip`, API `/api/location/*`, `shared/lib/location/location.ts`, cola `offlineQueue.ts`/IndexedDB, `privacyNotice.ts`, `permission.ts`. Confirmó: capturas solo por evento; 925 puntos en copia local; cola offline sin aislamiento pleno entre usuarios; cinco E2E de ubicación offline fallando; aviso existente en código pero sin pantalla observada **en aquella revisión**. Ver informe `RTE-LOC-01_AS_IS_GPS_DATA_AND_ARCHIVE_DIAGNOSTIC_REPORT.md`.

**Regla de economía:** empezar por `git diff` desde ese baseline y solo archivos implicados. No volver a medir 925 puntos, inventariar todo el repositorio ni ejecutar regresión global. No copiar el diagnóstico previo.

## Objetivo: responder SOLO 6 verificaciones que desbloquean implementación

1. **Aviso y bloqueo GPS actuales.** Identificar archivo/componente y flujo real donde el usuario **ve y acepta** el aviso, cómo persiste la aceptación (si aplica) y dónde se bloquea al negar/revocar ubicación. Probar o rastrear: Start Work, jornada abierta, revocación, End Work seguro y sesión nueva. Distinguir política declarada de comportamiento AS-BUILT. Si el aviso ya cumple la nueva captura periódica, marcar CLOSED con evidencia; si no, especificar **solo** diferencia de texto/flujo, sin crear consentimiento nuevo por su cuenta.
2. **Punto de integración del temporizador.** Precisar 1 lugar concreto para iniciar/reanudar/parar captura a **300 s** durante jornada activa, sin tocar `getCurrentPosition` usado por eventos. Determinar limpieza al cerrar sesión, cambiar tenant/usuario, revocar permiso, cerrar jornada, navegar entre pantallas y varias pestañas. Explicar si usar `watchPosition` o invocación periódica y por qué; no prometer funcionamiento con pantalla bloqueada.
3. **Configuración UX / API / RBAC.** Identificar settings, componente UX, contratos y permisos existentes reutilizables. Proponer ubicación mínima en Configuration, campo `capture_interval_seconds` (default 300), habilitación solo para captura nueva y permiso dedicado (nombre sugerido: `route.location.capture.configure`; verificar convenciones). Precisar si el cambio se aplica sin refresh, cómo se propaga por tenant, validación server-side y auditoría. Proponer rango seguro, sin asumir que ya está aprobado.
4. **Ingesta y cola offline.** Proponer tabla y API mínimas para muestras periódicas (IDs/tenant/jornada del servidor, UUID idempotente, coords, accuracy, `device_captured_at`, `server_received_at`); confirmar control de lotes, autenticación, deduplicación, datos tardíos y límites de volumen. **P0:** localizar la causa del posible cruce de cola entre usuarios/sesiones e indicar fix mínimo. Clasificar los **5 E2E offline** con fallo actual (causa comprobada vs no reproducido); ejecutar solamente tests dirigidos necesarios.
5. **Vista unificada y asignación a viajes.** Verificar qué campos existentes permiten intervalos `Start Trip -> Arrived` (incluidos cambios de plan, viajes no cerrados, jornadas a medianoche, viajes seguidos, reloj/dispositivo). Proponer `VIEW` o consulta equivalente que una eventos y muestras **sin escribir en `location_fix`**, sin duplicar puntos y sin cruzar usuarios/tenants; marcar qué asociaciones son seguras y qué queda como aproximación.
6. **Preparación para archivado posterior.** Identificar solo las decisiones de esquema/partición que RTE-LOC-02 debe respetar para RTE-LOC-03: export por tenant/mes, retención de nuevas muestras, origen de timestamps, referencia a eventos que NO se purgan. No configurar Spaces ni cron ahora.

## Formato obligatorio de respuesta (MAX 750 palabras + tabla)

Guardar `RTE-LOC-02_PRECHECK_RESULT.md` con:

1. **Baseline:** commit actual y delta vs RTE-LOC-01 (máximo 5 líneas).
2. **Matriz 6 filas** con columnas `# | Confirmed (archivo:símbolo/línea o prueba) | GAP real | Decisión técnica mínima | Estado`.
3. **Contract sketch** compacto: tabla + API + permisos + fuente de config + vista/consulta; SIN DDL ni código.
4. **P0/Blockers:** solo brechas demostradas que impedirían codificar con seguridad; incluir estado del aviso GPS y de los 5 E2E.
5. **Propuesta de siguiente checkpoint:** hasta 3 unidades verificables, estimación y tests focalizados. `GO / GO WITH GAPS / BLOCKED` motivado.
6. **Preguntas al PO:** máximo 3, solo las que realmente bloquean el desarrollo; no reabrir las decisiones aprobadas.

## Guardrails

READ-ONLY: no editar código, no crear migraciones, no insertar ubicaciones reales, no cambiar permisos ni desplegar. No adjuntar coordenadas/personas a evidencias. Respetar multitenancy, autorización en backend, privacidad y separación de datos por sesión. No imponer arquitectura nueva ni sumar un microservicio. Preferir contratos y servicios existentes. Entregar evidencia, no narraciones largas ni especulaciones.
