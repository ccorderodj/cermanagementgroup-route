"""
Primitivas de integración entre aplicaciones modulares de CER.

Cada aplicación es un monolito modular con su propio dominio. Se hablan por
REST versionado y webhooks firmados en las dos direcciones; nada más. Esto no es
un bus de eventos ni una plataforma de integración: son las piezas mínimas y
neutrales que cualquier dominio reutiliza.

* `signatures` — firma y verificación HMAC-SHA256 con marca de tiempo.
* `idempotency` — una clave de idempotencia recuerda la respuesta.
* `events` — metadatos append-only de cada mensaje que entra o sale.
* `webhooks` — endpoints entrantes/salientes, cola de entregas y reintentos.
* `router` / `admin_router` — la superficie HTTP.

Guía: `docs/INTEGRATION_GUIDE.md`.
"""
