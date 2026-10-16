# CER Route — Activity Admin: Route Map Viewer

**Reporte 001 — respuesta a** `CER_ROUTE_ACTIVITY_ADMIN_ROUTE_MAP_VIEWER_SINGLE_DEVELOPMENT_INSTRUCTION_V1_0.md`
**Fecha:** 15 de octubre de 2026
**Status: COMPLETED WITH PENDING VALIDATION** (local, base de tests).
- **Checkpoint A** (15-10, MR !96): bloqueado en el gate, porque la geometría por carretera no existe.
- **Decisión de CER el mismo día:** enseñar los **puntos del cálculo de TomTom sobre un mapa base de OpenStreetMap** (la «Opción 3», marcadores sin línea).
- **Checkpoints B y C:** ejecutados con esa decisión.
- **Pendiente:** certificación de CER, concesión del permiso por rol en cada tenant y despliegue.

---

## Checkpoint A — Discovery & decision

### A.1 Base inspeccionada
| Elemento | Valor |
|---|---|
| Rama / commit | `dev` @ `aa4d2b0` (incluye la jerarquía V1.6) |
| Datos | Copia local del entorno compartido, solo `SELECT` con agregados; ninguna coordenada leída ni reportada |
| Entorno desplegado | NOT RUN (sin acceso) |

### A.2 Trazado AS-BUILT: tarjeta → viaje → millaje → TomTom

| Pieza | Hallazgo | Evidencia | Estado |
|---|---|---|---|
| Tarjeta de Activity Admin | **Una tarjeta = un viaje** (`key={trip_id}`). Las millas de la tarjeta son las oficiales de `TripMileage` (solo `calculated`) | `features/RouteActivityExplorer/ui/ExplorerActivityCards.tsx:53-68`; `activityexplorer/dao.py` (`paradas_del_dia`); 0 tarjetas con más de un viaje en los datos | CONFIRMED |
| Contrato de la API de Activity | `ExplorerActivity` **no** incluye coordenadas, geometría ni enlaces (`extra="forbid"`) | `activityexplorer/schemas.py:74-143` | CONFIRMED: hoy no hay exposición |
| Petición a TomTom | `GET /routing/1/calculateRoute/{lat},{lon}:{lat},{lon}/json` con **`routeRepresentation=summaryOnly`**: TomTom **no devuelve** la geometría, solo `lengthInMeters` | `mileage/routing.py:406-421` | CONFIRMED |
| Persistencia | `trip_mileage_segment`: puntos de paso ordenados (origen, cada cambio de plan, destino), metros, proveedor y método. **Ninguna polilínea, GeoJSON ni vértices** en modelos ni migraciones (0001–0020) | `mileage/models.py:188-272`; búsqueda en `app/` | CONFIRMED |
| Enlace de Google Maps | **No existe en el código** (ni backend ni frontend). La URL de ejemplo de la instrucción no la genera la aplicación | Búsqueda de `google.com/maps` y `maps/dir` en `app/`, en las ramas y en el historial (diagnóstico del 14-10 y repetida hoy) | CONFIRMED |
| Librerías de mapa | Ninguna instalada | `app/package.json` | CONFIRMED |
| CSP | `script-src 'self'`, `img-src 'self' data: blob:`, `connect-src 'self'`: **bloquea** teselas y scripts externos | `core/middleware/security_headers_middleware.py:46-69` | CONFIRMED |
| Permisos | Solo por rol. Catálogo en `app/core/rbac/catalog.py`; concesión por Roles & Permissions con aprobación de dos personas. `route.activity.map.read` **no existe** | Diagnóstico RBAC del 14-10 | CONFIRMED |
| Alcance | `alcance_administrativo`: el CEO ve todo (V1.6); COO y RM por periodo (`WorkSession.started_at`); Sales solo para el CEO | `organization/scope.py` | CONFIRMED |

**Datos disponibles (copia local):**

| Métrica | Valor |
|---|---|
| Viajes | 244 |
| Millaje `calculated` (con puntos de paso guardados) | **117 (48 %)** |
| `calculation_failed` / `not_calculable` / `pending` | 69 / 51 / 2: **sin** puntos de paso |
| Viajes de 1 tramo / 2 tramos | 114 / 3 |
| Tramos con origen = destino | 6 |
| Proveedor | `tomtom` 0.0.12 en el 100 % |

**Conclusión:** solo existen los **puntos de paso**. Unirlos sería una **línea recta**, y FR-04 lo prohíbe expresamente. **La ruta por carretera no existe para ningún viaje.**

### A.3 Comparación de renderizadores (no de motores de ruta)

Medidas de npm (`npm view`, 15-10-2026). El tamaño desempaquetado incluye fuentes, *source maps* y distribuciones duplicadas; **no** es el coste en el navegador. El coste real en *bundle* **no se midió** en esta base (pendiente de la prueba de concepto de B, si se aprueba). Los valores de transferencia son **estimaciones**.

| Criterio | **Leaflet 1.9.4** | **MapLibre GL JS 6.14.0** | **OpenLayers (`ol`) 10.11.0** |
|---|---|---|---|
| Licencia | BSD-2-Clause | BSD-3-Clause | BSD-2-Clause |
| Paquete npm desempaquetado | 3,7 MB | 28,0 MB | 12,8 MB |
| Peso en el navegador (estimado, gzip) | ~40 KB JS + ~4 KB CSS | ~200+ KB JS + CSS; WebGL | ~100–150 KB con *tree-shaking* |
| Encaje con el stack | Alto: un componente React cargado bajo demanda con `import()`; sin estilos ni fuentes externas | Medio: necesita **estilo vectorial** y fuentes de glifos de un proveedor (otra dependencia de teselas) | Medio-bajo: API SIG completa, sobredimensionada para un mapa dentro de una tarjeta |
| Polilínea o GeoJSON | Nativo | Nativo (capa GeoJSON) | Nativo |
| Móvil, 390 px, desplazamiento táctil | Bueno; `scrollWheelZoom` y `dragging` controlables para no atrapar el scroll | Bueno, pero GPU y memoria más altas; liberar contexto WebGL al cerrar | Bueno; más configuración |
| Limpieza al cerrar | `map.remove()` | `map.remove()`, que libera el contexto WebGL | `setTarget(undefined)` |
| Aspecto visual | Correcto con teselas raster | El mejor (vectorial) | Correcto |
| Riesgo de mantenimiento | Bajo | Medio | Medio |

**Recomendación técnica para cuando se desbloquee: Leaflet.** Es el menor peso, el menor código y no necesita infraestructura de estilos. Se cargaría **solo** al pulsar `View Route`, en un trozo separado del *bundle*.

### A.4 Fuente de teselas (un renderizador libre **no** implica teselas gratuitas)

| Fuente | Condiciones (verificadas) | Coste | Viabilidad |
|---|---|---|---|
| **OSM público** (`tile.openstreetmap.org`) | Servicio *best-effort*, **sin SLA**; «access may be withdrawn at any point» para servicios comerciales; bloqueo sin aviso por uso intenso; atribución visible; User-Agent y Referer válidos | 0 | **No recomendado para producción** |
| **TomTom Map Display API (raster)**: mismo proveedor que el routing | Freemium: **50.000 peticiones de teselas al día gratis**, apto para uso comercial; exceso a ~0,08 USD por 1.000 teselas | 0 en el volumen actual (decenas de mapas al día) | **Recomendado.** Requiere una **clave restringida por dominio** para el navegador, o un proxy en el servidor, sin exponer la clave del routing. Hay que confirmar si el plan contratado por CER es Freemium o *Pay as you grow* |
| Teselas propias (*self-hosted*) | Infraestructura nueva | Servidor + almacenamiento | **Fuera de alcance** (§3) |

**Requisito transversal:** cualquier fuente externa exige abrir la CSP (`img-src` al dominio de las teselas). Es un cambio de seguridad pequeño, pero explícito.

### A.5 Cómo obtener la ruta por carretera: las tres únicas vías, y por qué todas pasan por CER

| Opción | Qué implica | Fidelidad | Histórico | Coste | Toca algo prohibido sin aprobación |
|---|---|---|---|---|---|
| **1. Capturar la geometría a partir de ahora** (recomendada) | Cambiar `summaryOnly` → `polyline` **en la misma petición** que ya calcula las millas; guardar los puntos en una columna nueva | **Exacta**: es la misma respuesta que dio las millas | Solo los viajes **posteriores** a la activación; los anteriores dirían «Route not available for this trip» (sin línea falsa) | **0 llamadas extra**; más almacenamiento | **Sí:** cambia un **parámetro de la petición a TomTom** (§3 lo excluye) y crea **datos nuevos retenidos** (migración). Hay que verificar que `lengthInMeters` no cambia y los **términos de TomTom sobre almacenar la geometría** (el propio código lo advierte en `routing.py:332-338`) |
| **2. Recalcular al abrir el mapa** | Una llamada a TomTom por apertura | **No es la original**: la red de calles y la versión pueden cambiar; tendría que rotularse «Recalculated estimate» | Todos los viajes con puntos de paso (48 %) | 2.500 llamadas al día gratis y después ~0,75 USD por 1.000 (no teselas); **no se presupone gratis** | **Sí:** coste nuevo y procedencia de datos distinta |
| **3. Solo marcadores** (origen, cambios de plan, destino) | Ninguna llamada; sin línea | No es una ruta | 48 % | 0 | No, pero **no cumple el objetivo** (FR-04 pide la ruta por carretera) |

## Decisión adoptada por CER (15-10-2026)

> «Usar OSM para mostrar los puntos calculados utilizados por TomTom» y «ejecuta y muestra el mapa usando la combinación de OSM y TomTom».

**Qué se implementó con esa decisión:**
- **Mapa base:** OpenStreetMap.
- **Encima:** los **puntos con los que TomTom calculó las millas** de cada viaje (salida, cambios de plan, llegada), en **marcadores numerados sin línea**. FR-04 prohíbe una recta que finja la ruta.
- **Sin tocar TomTom** (ni petición, ni cálculo, ni millas), **sin migraciones** y **sin coste**.

**Lo que sigue siendo cierto:**
- **No es la ruta por carretera.** Para tenerla hay que aprobar la Opción 1 (§A.5); el visor admitiría la línea sin rehacerse.
- **No hay problema de mezclar TomTom con OSM:** los puntos son **ubicaciones capturadas por el teléfono** (`location_fix` copiadas a los tramos) y TomTom solo devolvió la distancia. No se dibuja ningún contenido de TomTom sobre OSM.
- **OSM público no tiene SLA.** La URL de teselas es **configurable** (`MAP_TILE_URL`, `MAP_TILE_ATTRIBUTION`); para producción con garantías se cambia por otro proveedor sin tocar código.

## Checkpoint B — Controlled implementation

### B.1 Ficheros

| Fichero | Cambio |
|---|---|
| `app/core/rbac/catalog.py` | Capacidad `route.activity.map.read`. Nueva lista `CAPACIDADES_A_DEMANDA`: **ninguna plantilla** la concede, tampoco owner y admin, que reciben «todo» |
| `app/config.py` | `MAP_TILE_URL` (OSM por omisión) y `MAP_TILE_ATTRIBUTION` |
| `app/core/middleware/security_headers_middleware.py` | La CSP añade **solo** el origen de las teselas, y **solo** en `img-src` |
| `app/routers_api/activityexplorer/route_map.py` (nuevo) | Comprobación del viaje **con el alcance aplicado** antes de leer coordenadas; puntos en orden, sin repetir el de enlace entre tramos, con rango validado |
| `app/routers_api/activityexplorer/router.py` | `GET /api/activity-explorer/trips/{trip_id}/map`: exige `route.activity.read` **y** `route.activity.map.read`; fuera de alcance, 404 igual que un id inventado |
| `app/routers_api/activityexplorer/schemas.py`, `dao.py` | `TripMapRead`. En la tarjeta, **solo** el booleano `route_points_available` (millaje calculado), sin coordenadas |
| `app/components/react/entities/RouteActivityExplorer/*` | Zod `tripMapSchema` y `fetchTripMap` |
| `.../features/RouteActivityExplorer/ui/RouteMapViewer.tsx` + `.scss` (nuevos) | Visor: Leaflet, teselas con `referrerPolicy` (OSM exige Referer), marcadores numerados con los colores del tema, sin arrastre con un dedo en móvil, `map.remove()` al cerrar, estados de carga, sin puntos y error con «Retry» |
| `.../ExplorerActivityCards.tsx` | `View Route` / `Hide Route` bajo el resumen de la cabecera (`aria-expanded`, `aria-controls`); el visor, con `lazy`, **después** de los detalles; se cierra al cambiar el día, el periodo o el supervisor |
| `.../widgets/RouteActivityExplorer/ui/ActivityExplorerPanel.tsx` | `mapEnabled` solo en la vista **administrativa** y con el permiso. La Activity personal no cambia |
| `app/configwebpack/build/loaders/buildCssLoader.ts` | No resuelve las 3 imágenes de Leaflet que el visor no usa (control de capas y marcador por defecto) |
| `app/package.json` | `leaflet` 1.9.4 (BSD-2) y `@types/leaflet` 1.9.12 (dev) |
| `docs/ARCHITECTURE.md` | Origen externo de teselas, visor y capacidad a demanda |
| `tests/integration/test_activity_route_map.py`, `tests/e2e/test_activity_route_map_browser.py` (nuevos) | §C |

**Sin migraciones.** El permiso se crea en la tabla `permission` con `converge` (job PRE_DEPLOY de DigitalOcean, o `bootstrap` en local) y **no se concede a ningún rol**.

### B.2 Peso medido (build de producción)

| Recurso | Antes | Después | Se descarga |
|---|---|---|---|
| `main.js` | 811.225 B | 812.294 B (+1,1 KB, +0,13 %) | Siempre |
| `main.css` | 107.395 B | 107.497 B | Siempre |
| Leaflet (trozo aparte) | — | 148,9 KB · **42,7 KB gzip** | Solo al abrir un mapa |
| Visor + CSS de Leaflet | — | 14,3 KB · 4,3 KB gzip | Solo al abrir un mapa |

### B.3 Seguridad y auditoría
- **Orden de comprobaciones:** permisos (403) → alcance de jerarquía por periodo, con Sales solo para el CEO (404, idéntico a un id inexistente) → y solo entonces se leen las coordenadas.
- **Sin rastros de coordenadas:** no se registran en logs ni en analítica, y el listado de Activity no las incluye.
- **Proveedor de teselas:** ve qué **zona** del mapa se mira (las teselas), no las coordenadas exactas ni la identidad. La atribución es visible.
- **Auditoría:** **abrir un mapa no se audita**, porque las lecturas no se auditan en el producto. **Conceder el permiso** pasa por Roles & Permissions, con la aprobación de dos personas.

### B.4 Capturas
En `Report Delivery Rodrigo/CER_ROUTE_ACTIVITY_ADMIN_ROUTE_MAP_assets/`, con datos de prueba y coordenadas sintéticas:
- `escritorio-cerrado.png`, `escritorio-abierto.png` y `movil-abierto.png`, con **teselas reales de OSM**;
- `movil-sin-permiso-linea-base.png`, la tarjeta original.

**Observación previa (`CONFIRMED` por esa captura):** a 390 px, la tarjeta **original** ya parte «activity span · trip / miles» en dos líneas. No lo introduce este cambio.

## Checkpoint C — Validation

| AC | Esperado | Implementado | Evidencia | Estado |
|---|---|---|---|---|
| AC-01 | La página no cambia salvo el botón y el visor | Cabecera, detalles, resumen y selectores intactos | Capturas antes y después; línea base sin permiso | COMPLETED |
| AC-02 | Un solo control, `View Route` ↔ `Hide Route`, mapa bajo los detalles | Sí | E2E | COMPLETED |
| AC-03 | 390 px sin desborde ni scroll atrapado | Sin arrastre con un dedo; altura acotada | E2E móvil: `scrollWidth <= innerWidth` | COMPLETED |
| AC-04 | Nada se carga hasta pulsar | `lazy` + trozo aparte; 0 teselas cerrado | E2E: lista de peticiones de teselas vacía antes de pulsar | COMPLETED |
| AC-05 | Ruta por carretera; nunca una recta falsa | **Puntos sin línea** (decisión de CER); millas sin cambios | E2E: 0 `path` en la capa vectorial | **DEVIATION aprobada**: no hay geometría (§A.5) |
| AC-06 | Sin permiso, ni botón ni API; COO/Sales, no; CEO/Sales, sí | Sí | Integración: 403 para route_admin, owner, admin y CEO sin permiso; COO→Sales 404; CEO→Sales 200 | COMPLETED |
| AC-07 | Tenant, id directo, revocación, historial por periodo | Sí | Integración: otro tenant 404; id inventado 404; revocar → 403; traslado por periodo | COMPLETED |
| AC-08 | Concesión por el flujo existente, sin concesiones globales | Capacidad a demanda | Ninguna plantilla la concede | COMPLETED (concesión por rol: **PENDING**, la decide cada tenant) |
| AC-09 | Comparación de 3 renderizadores, teselas, costes, condiciones | §A.3–A.4 + medida real §B.2 | — | COMPLETED |
| AC-10 | Nada más cambia | Diff acotado | Integración 1341 PASS; E2E 206 PASS; solo los fallos preexistentes | COMPLETED |
| AC-11 | Fallos sin romper la tarjeta | Estados de carga, sin puntos y error con Retry | Integración (millaje sin calcular → `available=false`) | COMPLETED |

**Tests:**

| Lote | Resultado |
|---|---|
| `test_activity_route_map` (integración) | **10/10 PASS** |
| `test_activity_route_map_browser` (escritorio + móvil + sin permiso) | **3/3 PASS** |
| Catálogo, superficie pública, cableado | PASS |
| `npm run check` | 0 errores |
| Regresión: integración + contratos | **1341 PASS, 15 skipped, 1 FAIL** preexistente (`test_provisioning_alignment`: 12 frente a 16 capacidades de `route_admin`, desde RTE09), 1633 s |
| Regresión: E2E completos | **206 PASS, 5 FAIL** preexistentes (ubicación sin conexión de RTE06, los mismos nombres que en V1.4–V1.6), 3950 s |

**Despliegue:**
1. Fusionar (PRE_DEPLOY ejecuta `converge`, que crea el permiso sin concederlo).
2. En **Roles & Permissions**, conceder «route.activity.map.read» a los roles que CER decida (por ejemplo Administrador, CEO y COO).
3. Que recarguen la aplicación.

**Rollback:** revertir el código. La capacidad queda inactiva en la tabla `permission` (convención de `converge`).

**Limitaciones abiertas:**
- No es la ruta por carretera (Opción 1 pendiente).
- Solo los viajes con millaje calculado tienen puntos (48 % en la copia local).
- OSM público no tiene SLA.

## Fuentes externas consultadas
- [OSM Foundation — Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/)
- [TomTom — Pricing](https://developer.tomtom.com/pricing) · [docs.tomtom.com/pricing](https://docs.tomtom.com/pricing) · [Map Display API](https://docs.tomtom.com/map-display-api/)
- [TomTom SDK — RouteRepresentation (summaryOnly vs polyline)](https://developer.tomtom.com/assets/downloads/tomtom-sdks/ios/api-reference/0.22.1/TomTomSDKRoutePlanner/Enums/RouteRepresentation.html)
- **No encontrado:** los términos de TomTom sobre **almacenar la geometría de las rutas**. Requiere verificación contractual por CER (**PENDING VALIDATION**).
