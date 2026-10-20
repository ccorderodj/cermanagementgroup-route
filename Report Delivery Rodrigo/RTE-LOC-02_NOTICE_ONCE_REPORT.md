# RTE-LOC-02 — El aviso de captura periódica, una sola vez por persona

**Fecha:** 2026-10-20 · **Rama:** `feature/rte-loc-02-notice-once` → `dev` · **Entorno de la evidencia:** local

## Qué pasaba
Con la captura periódica encendida, My Route enseñaba **todos los días** bajo «Working since» la frase *«CER Route records your location periodically while you use the app during your workday.»*. Se pidió un entorno minimalista y que el mensaje **no se repita**.

## Qué cambia
- **El aviso sale una sola vez por persona:** la primera vez que abre My Route con la jornada activa y la captura encendida, con un botón **«Got it»**.
- **Al pulsarlo, queda registrado en el servidor** (`location_notice_ack`: compañía, usuario, versión del texto, fecha y hora). No vuelve a salir ni otro día ni en otro teléfono.
- **«Working since» queda limpio**, sin la frase.
- **La puerta de permiso** («Location Required») solo incluye la frase mientras el aviso siga pendiente para esa persona.
- **Si algún día cambia el texto,** se sube la versión (`VERSION_DEL_AVISO`) y cada persona lo vuelve a ver **una** vez.
- **Por qué en el servidor y no en el teléfono:** guardarlo solo en el navegador lo haría reaparecer al cambiar de teléfono o borrar datos, y no dejaría constancia de a quién se informó.

**Archivos:**
- Migración `0029_location_notice_ack`.
- Backend: `locationcapture/models.py`, `service.py` y `router.py`, que añade `POST /api/location-capture/notice/ack` con `route.worksession.execute`, sin permiso nuevo.
- `location/router.py` y `schemas.py`: añaden `periodic_notice_pending` a `/api/location/policy`.
- Frontend: `RouteMyRoutePage.tsx` y `shared/lib/location/periodic.ts`.
- `docs/ARCHITECTURE.md`.

## Cómo se comprobó (local)
| Prueba | Resultado |
|---|---|
| Migración 0029: subida, bajada y subida | OK · 1 head |
| Integración: pendiente → visto → no se repite; idempotente; otra persona sigue pendiente; apagada sin aviso (+ captura periódica y política) | 67/67 PASS |
| E2E: aparece una vez, «Got it», **tras recargar no vuelve**; captura periódica, aislamiento de cola y puerta de permiso | 12/12 PASS · capturas `var/screenshots/periodic-location/movil-my-route-aviso.png` y `movil-my-route-sin-aviso.png` |
| `npm run check` / `npm run build:prod` | exit 0 / exit 0 |
| Regresión sin navegador (`pytest tests -m "not browser" -n 6`) | 1513 PASS · 1 FAIL (`test_provisioning_alignment`, el de siempre) · 15 skipped · 26 min |

## A tener en cuenta
- **Qué es el registro:** constancia de que **se mostró y se pulsó «Got it»**. No es un consentimiento legal distinto del permiso del navegador; esa valoración sigue pendiente de revisión legal.
- **Al desplegar:** la tabla nace vacía, así que cada persona verá el aviso **una vez**, la próxima vez que abra My Route con la captura encendida.

## Esfuerzo
~2 horas-agente (migración, backend, frontend y tests). Restante: 0 h.
