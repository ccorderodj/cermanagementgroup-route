# RTE-LOC-02 — Periodic Location Capture · Implementation report

**Fecha:** 2026-10-20 · **Rama:** `feature/rte-loc-02-periodic-capture` → `dev` · **Entorno de la evidencia:** local
**U1: Completed · U2: Completed · U3: Completed (with PENDING VALIDATION on device).** La captura queda **apagada** en todas las compañías; encenderla es decisión del PO.

## U1 — Aislamiento sin conexión y aviso

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| Cada registro de la cola, de su usuario y tenant; se envía solo lo del usuario actual | `offlineQueue.ts`: `owner` (usuario de `user_data` + host del tenant) en acciones, evidencia y muestras; `listPending*` y `flushQueue` filtran por propietario; lo de otro usuario se conserva | E2E `test_offline_queue_isolation_browser.py`: A encola sin red → B entra: 0 jornadas y 0 puntos de B, la cola de A sigue → A vuelve: su jornada y su punto llegan. **2/2 PASS** | — |
| Registros antiguos sin propietario: sin reetiquetar ni enviar como el siguiente | **Retenidos:** ni se envían ni se borran (`listHeldOfflineItems` los cuenta) | E2E `test_lo_encolado_sin_propietario_se_retiene` PASS | **Cambio de comportamiento deliberado:** RTE10-A02 enviaba una acción heredada al volver el permiso; ahora queda retenida (test actualizado). No hay pantalla para recuperarla: **decisión del PO** |
| Aviso: sin consentimiento nuevo; texto corto con la captura encendida; corregir «no se rastrea entre eventos» | `PERIODIC_CAPTURE_NOTICE` en la puerta de ubicación y en la cabecera de My Route, solo con la captura encendida. `privacyNotice.ts` corregido; sigue sin mostrarse en ninguna pantalla (como antes) | Captura `var/screenshots/periodic-location/movil-my-route-aviso.png`; E2E «apagada: sin texto» PASS | **Revisión legal y de contenido pendiente** antes de producción |
| Diagnosticar los 5 E2E de RTE-06 | **Dos causas del arnés de pruebas, CONFIRMED:**<br>(1) el sondeo de permiso (RTE10-A02) consumía los pasos del guion de `getCurrentPosition`;<br>(2) `abrir_sesion` sobrescribía la coordenada del test con la común.<br>Se corrigió **solo el arnés**; el producto no tenía defecto | Antes: **5 FAIL**. Después: los dos archivos, **17/17 PASS** | — |

## U2 — Captura independiente

- **Configuración:**
  - tabla `location_capture_setting` por `company_id` (Route, no núcleo), apagada por defecto, 300 s, CHECK 60–3600;
  - `GET`/`PUT /api/location-capture/settings` con `route.locationcapture.manage`, **a demanda**;
  - 409 por versión, 422 fuera de rango, auditoría (actor, antes y después);
  - pantalla **CER Route › Configuration › Location Capture**;
  - quien ejecuta la recibe en `GET /api/location/policy` (`periodic_capture_*`).
- **Cliente** (`shared/lib/location/periodic.ts`):
  - **cuándo muestrea:** solo con jornada activa, permiso concedido y la captura encendida;
  - **cómo:** `getCurrentPosition` acotado (10 s, `maximumAge` 60 s) cada intervalo, no `watchPosition`;
  - **pestañas:** una sola por tenant, usuario y jornada (`navigator.locks`); la última muestra se recuerda para no duplicar al recargar;
  - **segundo plano:** al volver a primer plano se comprueba si toca; sin puntos sintéticos;
  - **parada:** en End Work, al perder el permiso y al desmontar (logout, cambio de usuario).
  - La captura por evento (`captureFor`) no se toca; solo se exporta `pedirPosicion`.
- **Cola:**
  - almacén `pending_location_samples` (IndexedDB v4), con propietario y jornada;
  - máximo 500 muestras por usuario; descarte a los 30 días;
  - lotes ≤ 50;
  - **apagada:** no captura ni envía, y lo pendiente queda retenido sin reenvío automático al encender.
- **Servidor** (`POST /api/location/samples`):
  - **identidad:** jornada del usuario autenticado (si no, 404); usuario y compañía nunca del cuerpo;
  - **horas:** no más de 5 min en el futuro ni más de 30 días de antigüedad, y dentro de la jornada ±5 min;
  - **precisión:** ≤ umbral de punto fresco (100 m);
  - **resultado:** idempotente por `(company_id, client_sample_id)`, con estado por muestra; 409 si está apagada;
  - **logs:** solo recuentos, sin coordenadas.
- **Datos:**
  - tabla `location_sample`;
  - vista **`location_point_timeline`**: une `location_fix` (`event`) y `location_sample` (`periodic`) con el usuario de la jornada. El viaje de una muestra se asigna solo si es inequívoco (`interval`, provisional); si no, queda sin viaje.
  - **Sin endpoint de lectura.** Ningún módulo de routing o millaje la lee (test que lo vigila).
- **Variación documentada:** `location_sample` **no está particionada**. En PostgreSQL, una clave única en una tabla particionada debe incluir la columna de partición, y eso rompería la idempotencia por `client_sample_id`. Hay índice `(company_id, server_received_at)` para el corte mensual; la partición es decisión de RTE-LOC-03.

**Migración `0028_periodic_location_capture`:**
- dos tablas y una vista; no siembra nada;
- up → down → up OK en local; 1 head.

## U3 — Evidencia

| Comando | Resultado |
|---|---|
| `pytest tests/integration/test_location_capture.py -n 4` | **6/6 PASS**: configuración (403, 422, 409, auditoría, tenant), apagada 409 sin escribir, ingesta (aceptada, precisión, fuera de jornada, futura, antigua, duplicada, 51 → 422, campos de identidad → 422), jornada ajena u otro tenant → 404/409, línea de tiempo y que millaje/routing no leen las muestras |
| `pytest tests/e2e/test_periodic_location_browser.py tests/e2e/test_offline_queue_isolation_browser.py` | **6/6 PASS**: pantalla (escritorio y móvil sin scroll horizontal), apagada (0 muestras, el punto de Start Work sigue), encendida (1.ª muestra y aviso), dos pestañas (1 muestra) y aislamiento |
| `pytest tests/test_page_wiring.py tests/test_navigation_wiring.py tests/test_permission_catalog.py tests/test_public_surface.py` | 66/66 PASS |
| `npm run check` / `npm run build:prod` | exit 0 / exit 0 |
| **Regresión completa** `pytest tests -n 6` | **1745 PASS · 4 FAIL · 15 skipped** (49 min). Detalle de los 4 fallos, abajo |
| Los 4 fallos, repetidos tras corregir | **5/5 PASS** (incluye `g12`, que falló al cambiar `/policy` con la regresión en curso) |

**Los 4 fallos de la regresión:**
- `test_provisioning_alignment`: el de siempre.
- Tres contratos de test que este cambio altera a propósito:
  - `/policy` tiene dos campos nuevos;
  - los archivos nuevos aún no estaban en git;
  - la acción heredada ya no se envía como el usuario actual.

**PENDING VALIDATION** (no ejecutado en navegador ni en dispositivo):
- revocar el permiso a mitad de jornada;
- pantalla bloqueada o pestaña en segundo plano;
- jornada que cruza medianoche y jornadas largas, en el cliente (el servidor usa los instantes de la jornada, no la fecha);
- red lenta, desbordamiento de la cola.

## Riesgos
- **Acciones antiguas sin propietario:** retenidas sin vía de recuperación en la interfaz.
- **El aviso necesita revisión legal.**
- **Sin garantía en segundo plano:** la web no puede asegurar la captura con la pantalla bloqueada.
- **Asignación de muestras a viajes:** depende del reloj del dispositivo.

## Despliegue
1. Fusionar el MR. En `migrate` deben aparecer `0028` y `converge`, que crea `route.locationcapture.manage`.
2. Asignar el permiso solo a quien deba configurarla.
3. **Mantener la captura apagada** hasta el GO del PO para un piloto.
4. No iniciar RTE-LOC-03.
