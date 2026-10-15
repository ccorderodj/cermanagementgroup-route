# CER Route — Activity Admin: Route Map Viewer

**Reporte 001 — respuesta a** `CER_ROUTE_ACTIVITY_ADMIN_ROUTE_MAP_VIEWER_SINGLE_DEVELOPMENT_INSTRUCTION_V1_0.md`
**Fecha:** 15 de octubre de 2026
**Status: BLOCKED at Checkpoint A — DECISION REQUIRED.** Se activa el gate de §4 y §11: **la geometría de la ruta no existe**, y cualquier forma de dibujar la ruta por carretera exige cambiar la petición a TomTom y guardar un dato nuevo, o hacer llamadas nuevas a TomTom. **No se modificó código, esquema, datos ni dependencias.** Checkpoints B y C: **NOT STARTED**.

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

## Checkpoint B — Controlled implementation
**NOT STARTED** (gate). No hay ficheros cambiados, migraciones ni dependencias.

## Checkpoint C — Validation
**NOT STARTED.**

| AC | Estado |
|---|---|
| AC-09 (comparación de renderizadores, teselas, costes y condiciones) | **COMPLETED** (§A.3–A.5); la medición del *bundle* queda **PENDING** para la prueba de concepto de B |
| AC-01 a AC-08, AC-10, AC-11 | **BLOCKED** por la decisión de §A.5 |

## Decisión que necesita CER (una sola, concreta)

> **¿Autoriza CER la Opción 1?** Cambiar la petición de TomTom de `summaryOnly` a `polyline` y guardar la geometría de cada viaje **a partir de la activación**, siempre que se verifique que las millas no cambian y que los términos de TomTom permiten almacenarla. Con ella, el mapa mostraría la **misma** ruta que dio las millas. Los viajes anteriores mostrarían «Route not available» y nunca una línea inventada.

**Condiciones asociadas, a confirmar a la vez:**
1. **Teselas:** TomTom Map Display, con una clave **pública restringida por dominio** (o proxy en el servidor) y apertura de la CSP a ese dominio.
2. **Permiso:** `route.activity.map.read` en el catálogo, **sin concederlo por defecto a ningún rol**; se concede por Roles & Permissions.
3. **Plan de TomTom contratado:** confirmar si es Freemium o *Pay as you grow*.

**Alternativas si CER no aprueba la Opción 1:**
- **Opción 2:** recalcular, rotulado como recálculo y con un coste por uso.
- **Opción 3:** solo marcadores, que no es una ruta.

**Estimación si se aprueba la Opción 1** (horas-agente):

| Tarea | Complejidad | Horas |
|---|---|---|
| Captura de la geometría en la petición existente + columna + migración + test de que las millas no cambian | media | 3 |
| Endpoint por viaje (permiso + alcance antes de serializar) + capacidad + tests de seguridad (CEO/COO/Sales, tenant, id directo, revocación) | media | 4 |
| `View Route` / `Hide Route` + Leaflet bajo demanda + estados + accesibilidad + CSP | media-alta | 5 |
| E2E escritorio/móvil, regresión, informe | — | 4 |
| **Total** | | **16 h**; +30 % por integración de terceros (teselas y TomTom) ≈ **21 h** |

## Fuentes externas consultadas
- [OSM Foundation — Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/)
- [TomTom — Pricing](https://developer.tomtom.com/pricing) · [docs.tomtom.com/pricing](https://docs.tomtom.com/pricing) · [Map Display API](https://docs.tomtom.com/map-display-api/)
- [TomTom SDK — RouteRepresentation (summaryOnly vs polyline)](https://developer.tomtom.com/assets/downloads/tomtom-sdks/ios/api-reference/0.22.1/TomTomSDKRoutePlanner/Enums/RouteRepresentation.html)
- **No encontrado:** los términos de TomTom sobre **almacenar la geometría de las rutas**. Requiere verificación contractual por CER (**PENDING VALIDATION**).
