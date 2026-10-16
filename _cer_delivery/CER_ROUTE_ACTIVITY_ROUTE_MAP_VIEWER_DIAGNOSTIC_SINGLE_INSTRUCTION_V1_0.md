# CER Route — Diagnóstico de factibilidad del visualizador de ruta estimada en Activity

**INSTRUCCIÓN ÚNICA DE DIAGNÓSTICO — V1.0**  
**Fecha:** 14 de octubre de 2026  
**Dirigido a:** desarrollador CER Route y su agente de IA  
**Autoridad:** Product Owner CER / CER Development Copilot  
**Fase:** investigación AS-BUILT **exclusivamente de lectura** — NO autoriza programación, diseños de UI ni despliegue  
**Entrega solicitada:** **un solo reporte Markdown** con evidencias, decisiones pendientes y recomendación de viabilidad.

## 1. Contexto y decisiones confirmadas

CER Route registra eventos operativos con ubicaciones puntuales (inicio de jornada, salidas, llegadas y demás eventos que el modelo vigente registre). Usa información de Routing para estimar distancia/millas por viaje y genera un enlace de Google Maps. El Product Owner quiere **visualizar gráficamente la ruta estimada a partir de los datos ya obtenidos**, no implantar seguimiento GPS continuo.

Existen dos experiencias de Activity, con fines y permisos distintos:

- **Personal:** `/route/activity`, vinculada a My Route; muestra exclusivamente jornadas y viajes del usuario autenticado. El contrato de implementación RTE08 debe considerarse referencia, verificando cuál versión está actualmente integrada/desplegada.
- **Administrativa:** `/admin/route/activity`, con consultas de personas incluidas en el **alcance jerárquico autorizado**; no debe confundirse con la Activity personal.

La iniciativa propone **una capacidad opcional y asignable a determinados usuarios para VER el mapa**. La condición es acumulativa: (a) permiso explícito del **usuario que consulta** el visualizador y (b) derecho preexistente para consultar esa Activity y ese sujeto. **El permiso de mapa no concede acceso a otros usuarios, otros tenants, otra rama ni otros datos.**

Contexto de jerarquía relevante: el frente V1.3 solicita roles identificables CEO, COO, Regional Manager, OSM, Supervisor y Sales, con Sales subordinado **directamente al CEO** y fuera del alcance de COO y RM. **Verificar estado real de despliegue, sin asumir V1.3 terminado**, y evaluar cómo se conservarán estas reglas en el futuro mapa. OSM y Supervisor conservan nivel de acceso operativo equivalente; Sales también ejecuta jornadas y viajes propios.

**Importante:** Estado de operación y Zona horaria quedan completamente **fuera de alcance**. No proponer cambios ni correcciones a sus campos, inferencia, validaciones o reglas.

## 2. Objetivo del diagnóstico

Determinar, con evidencia del repositorio y de datos de prueba/controlados, **si CER Route ya dispone de lo necesario para dibujar en Activity la misma ruta estimada que fundamentó el cálculo de millas**, qué datos o contratos faltan, cómo conceder la visualización a usuarios específicos sin elevar sus otros permisos y qué decisiones requerirá CER antes de diseñar la vista.

**NO diseñar todavía la pantalla ni implementar el visualizador.** La secuencia de trabajo es obligatoria:

**(1) Diagnóstico documentado → (2) revisión y diseño de la vista junto al PO → (3) aprobación explícita del diseño y alcance → (4) MD de desarrollo de Activity → (5) implementación/pruebas.**

## 3. Alcance de investigación (AS-BUILT)

### A. Trayecto del dato: evento → Routing → kilometraje → Google Maps

Reconstruir el flujo real, citando **archivos, funciones, modelos, columnas, endpoints y ruta de ejecución**:

1. **Captura y persistencia de cada evento:** qué eventos producen latitud/longitud, fecha/hora, precisión/calidad u otros datos de ubicación; dónde se almacenan; qué pasa con permisos GPS denegados, offline, coordenadas inexistentes e inconsistentes.
2. **Trip y WorkSession:** cardinalidad y vinculación entre jornada, viajes, eventos y actividades, incluyendo viajes sin `ActivityExecution` (p. ej. regreso a casa), viajes abiertos, pendientes, fallidos y jornadas múltiples en un mismo día.
3. **Motor/servicio Routing:** proveedor(es), API/SDK/biblioteca, entrada efectiva, modos de viaje, parámetros, salida, manejo de errores y cálculo de millas oficiales. Localizar la frontera entre *distancia estimada* y cualquier *geometría*. **No modificar algoritmos ni recalcular datos.**
4. **Persistencia de Routing:** comprobar explícitamente si se guarda **polyline/encoded polyline, GeoJSON, geometry, coordenadas de vértices, lista de puntos, cache de respuesta, route_id o equivalente**, y a qué `trip_id`/`work_session_id` corresponde. Si solo se guardan origen/destino y metros, declararlo inequívocamente.
5. **Enlace existente de Google Maps:** identificar quién lo genera, desde qué datos, si se almacena o se forma en cada solicitud, su patrón/contrato (sin secretos ni ubicaciones reales identificables), si contiene waypoints y si la ruta abierta puede diferir del cálculo oficial. Aclarar si es simple enlace externo o si permite reproducir la geometría exacta usada en Routing.
6. **Geometría disponible por segmento:** verificar si existe trazado reutilizable **sin pedir nuevamente rutas** a un tercero. Si la distancia fue calculada usando un proveedor diferente de Google Maps, documentar la diferencia y el riesgo de mostrar otra ruta como si fuese la original.
7. **Rutas históricas:** identificar si los viajes ya guardados disponen de la geometría o solo los nuevos; política de preservación y consecuencias si se requieren futuras llamadas para recuperar un trazado. No hacer backfill ni llamadas masivas.

No confundir: **puntos de eventos**, **polilínea estimada del motor** y **recorrido GPS real** son datos diferentes. El PO quiere **ruta estimada**, nunca una reconstrucción presentada como rastreo de calles efectivamente transitadas.

### B. Viabilidad de la representación en Activity

Inspeccionar componentes, contratos/API y navegación existentes de `/route/activity` y `/admin/route/activity`:

- Identificar las estructuras comunes reutilizables, tarjetas/detalles de viaje y forma estable de identificar la jornada/`trip_id`.
- Estudiar **dos alcances de visualización**, sin diseñar UI: **(i) un viaje** y **(ii) secuencia de viajes de una jornada**. Determinar qué se puede mostrar en cada caso con datos reales; no sumar o unir segmentos inexistentes.
- Confirmar si el proveedor cartográfico/renderizador ya está instalado o se dispone de él mediante contratos existentes; alternativas viables de representación **sin seleccionar todavía un proveedor**.
- Identificar limitaciones Mobile/Web: tamaño de payload, renderizado de polilíneas, experiencia offline, carga progresiva, enlace externo disponible, accesibilidad y errores.
- Identificar efectos sobre millas oficiales: el mapa será visual y **no cambiará ni reemplazará** las cifras existentes. Mostrar, en el futuro, diferencias entre geometría y millas solo como datos de diagnóstico, sin alterar resultados.
- Precisar si el enlace actual de Google Maps puede usarse como **fallback** de visualización sin afirmar que representa el mismo cálculo; identificar dependencias y limitaciones.

### C. Permiso configurable por usuario que CONSULTA el mapa

Examinar el RBAC/roles real en la rama vigente, y los cambios pertinentes del frente V1.3, para determinar:

1. Si existe una **capacidad efectiva o permiso individual** por usuario (`allow/deny/override` o equivalente). Distinguir entre feature flag global/por tenant y autorización individual; **no asumir que ya existe override**.
2. Cómo se configura hoy una excepción individual desde la administración, qué guardas del servidor aplica y qué auditoría deja; **solo describir**, no editar roles ni catálogos.
3. Viabilidad de la **capacidad propuesta** `route.map.read` (nombre **provisional**, NO autorizado para crear en esta fase). Por defecto no debe otorgarse a roles completos. Si la plataforma solo admite roles, describir alternativas y sus riesgos, sin introducir nuevos roles o mecanismos.
4. Matriz de autorización esperada para: `route_admin`, CEO, COO, RM, OSM, Supervisor, Sales, usuario sin rol o sin habilitación, actor suspendido, y peticiones directas a API con IDs manipulados. La regla de mapa es **permiso individual del visor + acceso vigente a la Activity objetivo**.
5. Revisar **ambas rutas** personal y administrativa y todas las API involucradas. `/route/activity` seguirá siendo self-only aunque quien la abra sea CEO o admin; en la vista administrativa se limita al árbol y a la historia por períodos ya aprobados.
6. Verificar la **separación Sales/COO**: un COO que tenga `route.map.read` jamás podrá acceder a rutas de Sales directamente subordinado al CEO; tampoco por `trip_id`, `user_id`, `work_session_id`, URL externa o export indirecto.
7. Aclarar dónde se administra la habilitación y quién puede otorgarla/revocarla, con alcance de tenant, mínimo privilegio, revocación efectiva y audit trail. **No decidir aún una nueva UI de permisos.**

**Aclaración fundamental:** habilitar el mapa a un usuario le da la posibilidad de consultar mapas que **ya tiene derecho a consultar por Activity**; no habilita a todo el personal a ver mapas ni cambia la visibilidad de la persona cuyo viaje fue registrado.

### D. Seguridad, privacidad, proveedor y costos

- Identificar posibles exposiciones de coordenadas, enlaces persistentes, geometrías y claves/API tokens a usuarios sin `route.map.read` o fuera de scope. Verificar si el enlace externo constituye un canal de acceso que evade la API. Reportar riesgos sin alterar el enlace existente.
- Evaluar qué datos de localización quedarían accesibles en frontend/red, qué control debe ejercerse server-side y la relación con protección/retención de ubicaciones de empleados.
- Revisar proveedor, tipo de API/servicio y configuraciones existentes (secretos **nunca impresos**): si generar/dibujar una geometría requiere nuevas consultas, API habilitada, clave, cuotas, facturación, límites o restricciones de licencia/retención/caché, describirlo y señalar lo que requiera verificación externa; **no consumir servicios de pago en este diagnóstico**.
- Considerar que abrir Google Maps fuera de la aplicación puede escapar al control de `route.map.read` si una URL compartible queda visible. Registrar la limitación y alternativas de mitigación para decisión futura.
- No asumir consentimiento o autorización regulatoria para nuevos usos de geolocalización; identificar controles/políticas que habría que revisar antes de lanzar el feature.

## 4. Método y límites operativos

- Acceso **read-only** al repositorio, documentación y, si existe autorización y un entorno seguro, **SELECTs limitados** en base de datos no productiva. No modificar archivos de código, esquema, registros, permisos, configuraciones, tests ni UI.
- No ejecutar migraciones, backfills, fixtures que escriban datos, invocaciones al Routing que generen cargos, cambios en cloud, merges, despliegues ni llamadas a APIs externas sin permiso.
- Usar ejemplos **anonimizados o sintéticos**: nunca entregar nombres de empleados, coordenadas reales identificables, tokens, API keys o URLs con información sensible. Para demostrar persistencia, citar columnas y tipos y mostrar valores truncados/codificados no sensibles o agregados.
- Si una comprobación necesita credenciales, ambiente no disponible o acceso adicional, clasificarla **BLOCKED / PENDING VALIDATION**; describir la evidencia necesaria, sin fingir que se verificó.
- No redefinir permisos aprobados, estructura jerárquica, State, Timezone, WorkSession, GPS capture, consumo energético, millas, fórmulas ni flujos operativos. El frente V1.3 de jerarquía continúa independiente; registrar solo dependencias del futuro mapa.
- Reutilizar las capacidades/modularidad existentes de CER Route: política de autorización de dominio, API-first, sin contaminar Core con lógica de mapas o crear microservicios innecesarios.

## 5. Evidencias mínimas y tabla de hallazgos

El reporte deberá incluir como mínimo una matriz **Expected → As-Built → Evidence → Gap → Impact → Recommendation**, con referencias comprobables:

| Investigación | Evidencia mínima esperada |
|---|---|
| Puntos GPS de eventos | nombres de modelos/campos/servicios y los eventos que realmente guardan ubicaciones |
| Kilometraje y proveedor | servicio ejecutado, campos de `TripMileage` u homólogo, estado de cálculo y fuente del dato |
| Geometría de ruta | **sí/no/parcial/no comprobado**; tabla/campo/tipo y relación con viaje |
| Google Maps link | generador, contrato, relación con el cálculo y alcance de la URL |
| Activity personal vs admin | endpoints, parámetros, controles de seguridad y componentes relevantes |
| Configuración por usuario | modelo de permisos efectivo y opciones, sin inventar capacidad existente |
| Scope por jerarquía | evaluaciones de CEO/COO/RM y Sales directo al CEO, con caso negativo de acceso |
| Seguridad y privacidad | exposición posible, límites de proveedor y controles requeridos |
| Viabilidad Web/Mobile | restricciones y componentes existentes que podrían reutilizarse |

Clasificar cada afirmación como **AS-BUILT/CONFIRMED, PARTIAL, PENDING VALIDATION, NOT IMPLEMENTED/GAP, RISK o DECISION REQUIRED**. Diferenciar expresamente código local vs branch/MR vs ambiente desplegado; no mezclar supuestos con pruebas.

## 6. Alternativas técnicas que debe comparar el reporte (NO implementar)

Analizar y recomendar una opción **condicionada a la evidencia**:

- **A — Reutilizar geometría ya persistida** de la misma ruta estimada por Routing: opción preferente **solo si se verifica que existe**, que es accesible y reutilizable conforme al proveedor.
- **B — Reconstruir visualización desde los puntos/eventos que sí se conservan:** requiere obtener geometría desde servicio/proveedor; identificar diferencias potenciales respecto al cálculo original, cuotas, permisos, costos y reglas de uso. No presentarla automáticamente como ruta histórica original.
- **C — Solo marcadores + enlace existente de Google Maps** como alternativa de bajo alcance si no hay polilínea utilizable, dejando claro que eso **no** equivale a tener la geometría histórica ni reproduce necesariamente la distancia registrada.

Comparar **fidelidad del trazado, disponibilidad histórica, contratos y APIs, costo operativo, privacidad, latencia, rendimiento, compatibilidad Mobile y esfuerzo relativo**. Estimar complejidad por rangos (baja/media/alta) o tiempo justificado, no por líneas de código. Separar hallazgos de las decisiones que debe adoptar CER.

## 7. Entregable único y criterio de cierre de diagnóstico

Entregar **un solo archivo**:

`CER_ROUTE_ACTIVITY_MAP_VIEWER_AS_BUILT_DIAGNOSTIC_REPORT_001.md`

Estructura solicitada (evitar relleno):

1. **Status / alcance revisado** y commit SHA, branch, fecha y entorno inspeccionados; diferencias con despliegue si se conocen.
2. **Resumen ejecutivo**: ¿podemos dibujar la ruta estimada hoy con lo ya guardado? Respuesta **sí / parcial / no verificado / no**, y por qué.
3. **Inventario técnico** del flujo evento → Trip → Routing → TripMileage → link Google Maps, con referencias concretas.
4. **Diagnóstico de geometría e histórico** por viaje y por jornada; casos sin origen/destino, pendientes, fallidos y viajes sin actividad asociada.
5. **Diagnóstico RBAC por usuario y data scope**, identificando forma viable de habilitación individual sin permisos administrativos adicionales.
6. **Viabilidad de mapa, API, Web/Mobile y proveedor**, sin elaborar UI o mockups todavía.
7. **Matriz Expected / As-Built / Evidence / Gap / Impact / Recommendation** y riesgos de seguridad/privacidad/costos.
8. **Alternativas A/B/C**, tradeoffs y recomendación respaldada.
9. **Decisiones pendientes del Product Owner**, solo las que de verdad bloquean el diseño o la implementación posterior.
10. **Conclusión y siguiente paso:** insumos concretos para que CER **diseñe y apruebe primero la vista de Activity**; después se redactará el MD de programación. Indicar con claridad qué información aún falta si no se pudo verificar.

Incluir referencias `ruta:línea` o `ruta:símbolo`, fragmentos relevantes mínimos, evidencia de consultas limitadas y estado de acceso; no adjuntar código nuevo, capturas de mapas inventadas ni un MD de programación.

**Definition of Done del diagnóstico:** podemos decidir con evidencia si la polilínea original existe, qué alternativa de visualización sería fiel, cómo se restringiría por usuario sin romper scope, qué riesgos/costos hay y qué preguntas debemos resolver antes de diseñar la vista. **No se considera terminada ni autorizada la funcionalidad de mapas.**
