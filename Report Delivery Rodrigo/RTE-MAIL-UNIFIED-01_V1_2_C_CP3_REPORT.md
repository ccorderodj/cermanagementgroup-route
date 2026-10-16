# RTE-MAIL-UNIFIED-01 V1.2 · C (CP3): los cinco envíos de prueba

**Reporte C** · 16 de octubre de 2026
**Status C: COMPLETED WITH PENDING VALIDATION.**
- Los cinco caminos de prueba (T0-T4) pasan en código y en navegador.
- **La recepción real en un buzón es otra puerta:** BLOCKED EXTERNAL CONFIGURATION hasta que CER haga la prueba con su proveedor.

## 1. Los cinco casos

| Caso | Camino | Contenido | Destino |
|---|---|---|---|
| T0 | Platform › Outbound email › *Send Test Email* | Genérico `[TEST] CER Route — Email integration` | Escrito por el administrador de plataforma (A) |
| T1 | Midday Motivation › *Send test* | Plantilla guardada + datos ficticios | Propio o `MAIL_TEST_RECIPIENTS` |
| T2 | End of Day Recognition › *Send test* | Ídem, día y semana | Ídem |
| T3 | Strategic Midday Report › *Send test* | Plantilla guardada + dos personas ficticias, **sin** resumen semanal | Ídem |
| T4 | Strategic End-of-Day Report › *Send test* | Plantilla guardada + personas, semana individual y **un** *Team Weekly Summary* al final | Ídem |

**T3 y T4 usan el mismo endpoint, la misma política y el mismo generador** que la vista previa: `POST /api/activity-emails/templates/{tipo}/test-send` con `content.sample_values(tipo)`. No hay endpoint nuevo ni otra configuración de proveedor.

## 2. Garantías comprobadas
- **Marcado:** los cinco llevan «[TEST]» exactamente una vez, el banner «CORREO DE PRUEBA — datos ficticios», la cabecera `X-CER-Route-Test` y ningún marcador sin resolver.
- **Un solo presupuesto:** los cinco consumen **el mismo** (5 cada 15 minutos). El sexto, por cualquier camino, da 429.
- **No tocan nada:** jornadas, actividades y preferencias quedan igual antes y después.
- **Registro:** `mail_test_send` registra un envío de proveedor y cuatro de plantilla, con su resultado.
- **Destino libre solo en T0** y solo para administradores de plataforma. El tenant no puede mandar T3/T4 a otra dirección (403) ni usar T0 (403).
- **Resultados honestos:** «accepted by provider» nunca se muestra como entregado; «Captured…» o «Not sent outside the server» cuando no hay proveedor real.

## 3. Pruebas

| Lote | Comando | Resultado |
|---|---|---|
| Matriz de cinco casos | `uv run pytest tests/integration/test_mail_five_cases.py` | **2/2 PASS** |
| E2E de correo: T0 escritorio y móvil; Activity Emails (plantillas, vista previa, validación, restaurar, destinatarios, prueba controlada); estratégicos (grupo, vista previa T4, *Send test* T4, interruptor de mando, móvil) | `uv run pytest tests/e2e/test_activity_emails_browser.py tests/e2e/test_mail_provider_test_browser.py -n 0` | **8/8 PASS** |
| Regresión completa | `uv run pytest tests --ignore=tests/e2e` | **1.456 recogidos, 1 FAIL preexistente**, exit 1, 1.276 s |

Capturas en `var/screenshots/activity-emails/` (`escritorio-estrategicos.png`, `escritorio-preview-t4.png`, `escritorio-mandos.png`, `movil-mandos.png`) y en `var/screenshots/mail-provider-test/`.

## 4. Regresión completa
`uv run pytest tests --ignore=tests/e2e` (con A, B y C): **1.456 recogidos, 1 FAIL**, exit 1, 1.276 s. Los otros 1.455 pasaron u omitieron; el desglose no quedó capturado.
- **Único fallo:** `test_provisioning_alignment::…twelve_and_two_capabilities`, **preexistente desde RTE09** (`CONFIRMED`: espera 12 capacidades para `route_admin` y hay 16). Sin relación con este cambio.
- **Migraciones:** `0023_strategic_reports (head)`, un solo head.
- **Git:** rama `feature/mail-u01-cp2-cp3`, commits `328dd6c` (A) y `c2dbad5` (B+C).

## 5. Verificación real (la hace CER; V1.2 §4)
1. **Desplegar** el MR (migraciones 0023 y, si faltara, 0022).
2. **Platform › Outbound email:** **Verify** debe dar `healthy`.
3. **T0:** escribir el buzón de prueba y pulsar *Send Test Email*. Debe decir «Accepted by m365_oauth…».
4. **T1 a T4:** *Send test* en cada plantilla, al propio correo o a `MAIL_TEST_RECIPIENTS`. Son 4 envíos: con T0 hacen 5, el máximo de 15 minutos.
5. **Mirar la bandeja (y spam)** y guardar una captura de cada uno: deben verse cinco correos distintos con «[TEST]».
6. Hasta entonces, **PENDING DELIVERY VALIDATION**. Verify en verde no cierra esta puerta.

## 6. Lo que no se ha hecho (por instrucción)
- **Ningún envío automático** (CP4 NO AUTORIZADO).
- Ninguna suscripción activada por defecto.
- Ninguna nota real por correo.
- Ningún cambio en jornada, End Work, cálculos ni navegación.

## 7. Esfuerzo
Medido con `git diff --stat origin/dev..HEAD`: 28 archivos, +1.753 / −149 líneas.

| Tarea | Estado | Volumen | Horas-agente |
|---|---|---|---|
| A: conciliación y T0 editable | Hecho | ~150 LoC | 1,5 |
| B: plantillas estratégicas, generador, destinatarios, migración (backend) | Hecho | ~700 LoC, 150 LoC/h | 4,7 |
| B: pantalla (grupos, lista genérica de destinatarios, vista previa) | Hecho | ~330 LoC, 60 LoC/h | 5,5 |
| B+C: tests (unitarios, integración, matriz, E2E) | Hecho | ~620 LoC, 120 LoC/h | 5,2 |
| **Total V1.2 (A+B+C)** | | | **≈17** |
| CP4: envío programado de los cuatro correos (no autorizado) | | ~1.500-2.000 LoC | 15-20, **+30 % = 20-26** |
