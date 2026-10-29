# RTE · Motivacional de mediodía: sale con actividades iniciadas

**Fecha:** 2026-10-29 · **Rama:** `fix/midday-motivation-started` · **MR:** !119
**Estado:** COMPLETED WITH PENDING ITEMS (validado en local; sin desplegar)

## Condición, antes y después

`app/routers_api/activityemails/real_reports.py`, rama motivacional de `generar`:

```python
# Antes (los dos motivacionales)
if not hoy:                                   # hoy = completadas al corte
    return sin_correo(..., "no_activity")

# Después
if tipo == ActivityEmailType.MIDDAY_MOTIVATION.value:
    sin_actividad = not hoy and not al_corte  # al_corte = iniciadas antes del corte y abiertas
else:
    sin_actividad = not hoy                   # fin de jornada: sin cambios
if sin_actividad:
    return sin_correo(..., "no_activity")
```

Se reutilizan los mismos selectores (`_completadas` y `_abiertas`), el mismo
render y las mismas etiquetas que en MR !118. `activity_count` sigue contando
**solo completadas**: con una actividad únicamente en curso el correo sale con
`activity_count = 0`.

## Archivos

| Archivo | Por qué |
|---|---|
| `app/routers_api/activityemails/real_reports.py` | La condición de arriba |
| `app/routers_api/activityemails/content.py` | `send_condition` de mediodía (se ve en pantalla) y docstring de la regla |
| `app/routers_api/activityemails/delivery.py` | Mensaje de `no_activity`: «No eligible activities…» (antes decía «completed», ya no es cierto en mediodía) |
| `app/components/react/.../RecipientsTab.tsx` | Solo el texto que explicaba la regla antigua |
| `docs/ARCHITECTURE.md` | La regla, actualizada |
| `tests/integration/test_midday_motivation_started.py` | Nuevo: los 7 criterios de aceptación |
| `tests/integration/test_activity_emails_in_progress.py` | Se quita el test que fijaba la regla antigua |
| `tests/integration/test_mail_close_cp1.py`, `test_activity_email_delivery.py` | Dos tests que esperaban `no_activity` para una actividad en curso a las 12:00; ahora esperan correo con `0` completadas y «1 actividad en curso» |

Sin modelos, migraciones, endpoints, roles ni pantallas nuevas. El estratégico
y el fin de jornada individual no cambian.

## Criterios de aceptación

| # | Caso | Resultado |
|---|---|---|
| 1 | 11:40, abierta a las 12:00, ninguna completada | Sale; «1 actividad en curso», 0 completadas · PASS |
| 2 | Completada antes de las 12:00 | Sale igual que antes · PASS |
| 3 | Una completada y una abierta | Un solo correo (el segundo despacho no envía), las dos líneas · PASS |
| 4 | Solo una iniciada a las 12:15, generada a las 18:00 | No sale (`no_activity`) · PASS |
| 5 | Nada iniciado antes de mediodía | No sale, igual que antes · PASS |
| 6 | Jornada cerrada antes de mediodía con la actividad sin cerrar | Sale; «iniciada sin finalizar», no «en curso» · PASS |
| 7 | Estratégicos, fin de jornada, horarios, deduplicación | Lote de correo 174/174 PASS; fin de jornada sin completadas sigue sin salir · PASS |

## Validación

| Comprobación | Resultado |
|---|---|
| `import app.main` | OK |
| Tests nuevos | 7/7 PASS |
| Lote de correo, permisos, superficie pública y cableado de páginas (14 archivos) | 174/174 PASS, exit 0, 244 s |
| `npm run check` | exit 0 |
| flake8 en los archivos tocados | 0 avisos nuevos |
| Regresión completa | NOT RUN: cambio de una condición; la cubre el lote de correo. La última completa (MR !118, hoy) dio 1755 passed, con solo el fallo conocido de provisioning |
| Entorno compartido (DO) | NOT RUN |

## Riesgos

1. **Cambio de comportamiento a la vista:** quien hoy no recibía el correo de
   mediodía por tener solo actividades abiertas empieza a recibirlo cuando se
   despliegue. Es lo pedido.
2. **Instante exacto del corte:** una actividad iniciada exactamente a las
   12:00:00 no cuenta (`< corte`). Es el mismo criterio que MR !118 y el
   estratégico; la diferencia con «at or before» es de un instante.
3. **La insignia de la vista previa** («N activities» en Generate report) cuenta
   solo completadas, así que puede decir «0 activities» con el correo en curso.
   Es honesto, pero quizá confuso. No se toca porque la instrucción excluye la UI.

Sin bloqueos.
