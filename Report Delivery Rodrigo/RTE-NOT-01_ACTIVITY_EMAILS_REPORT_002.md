# RTE-NOT-01: sin actividades no hay correo, y el permiso que no aparece

**Reporte técnico 002** · 16 de octubre de 2026
**Status: COMPLETED WITH PENDING VALIDATION.** Validado en local. Pendiente: despliegue y certificación.

## 1. Regla nueva: sin actividades, no hay correo
**Decisión del PO, 16-10-2026:** si la persona no completó ninguna actividad, **no se le envía** el correo. No se manda una versión «sin recuento».
- **Mediodía:** se envía solo si completó al menos una actividad antes de las 12:00.
- **Fin de jornada:** se envía solo si completó al menos una actividad en la jornada cerrada.

**Qué cambia ahora.** El motor de envío no existe todavía; es RTE-NOT-02/03. Por eso la regla queda como contrato y a la vista:

| Pieza | Cambio |
|---|---|
| `activityemails/content.py` | `TemplateSpec.send_condition` y la regla documentada en el módulo |
| `GET /api/activity-emails/templates` | Devuelve `send_condition` por plantilla |
| Pantalla Templates | Cada plantilla muestra «Sent only if… No activities, no email.» |
| Pantalla Recipients | El aviso lo menciona |
| `docs/ARCHITECTURE.md` | El motor no debe enviar sin actividades completadas |

Esto reemplaza lo que decía la instrucción V1.0 (§6.1: «show a brief motivational alternative without numeric statistics»).

## 2. «No me aparece el permiso»
- **Causa del permiso (CONFIRMED):** «Activityemails.Manage» lo crea el script `converge`, igual que pasó con «Activity.Map.Read».
- **Por qué el despliegue no lo creó (LIKELY):**
  - en el repositorio está la propuesta `_cer_delivery/APP_SPEC_cerroute-dev.yaml` (07-10), que añade `python -m app.db.scripts.converge` al job `migrate` (PRE_DEPLOY) de DigitalOcean;
  - que dos permisos seguidos hayan tenido que crearse a mano indica que esa línea no está en la App Spec real;
  - desde aquí no puedo verlo.
- **Solución inmediata:** en la consola de DigitalOcean, `python -m app.db.scripts.converge`. Tiene que decir `+ 1 capacidades creadas (31 en el catálogo)`.
- **Solución definitiva:** añadir esa línea al job `migrate` de la App Spec, como indica el archivo del repositorio.

## 3. Pruebas (local)

| Lote | Resultado |
|---|---|
| Contenido + integración de Activity Emails | **52/52 PASS** |
| Navegador de Activity Emails + cableado de páginas + catálogo de permisos | **45/45 PASS** |
| `npm run check` / `npm run build:prod` | exit 0 / exit 0 |
| Regresión completa | **NOT RUN**: el cambio es un texto de API y de pantalla, sin lógica ni datos; se ejecutaron los lotes que lo cubren |

Sin migraciones ni datos tocados.

## 4. Esfuerzo
≈ **1 hora-agente**: regla, API, pantalla, tests y diagnóstico del permiso.
