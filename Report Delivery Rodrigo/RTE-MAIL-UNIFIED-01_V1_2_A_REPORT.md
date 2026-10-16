# RTE-MAIL-UNIFIED-01 V1.2 · A: conciliación y destino editable en la prueba del proveedor (T0)

**Reporte A** · 16 de octubre de 2026
**Instrucción:** `_cer_delivery/RTE-MAIL-UNIFIED-01_CORRECTIVE_CP2_CP3_V1_2.md`
**Status A: COMPLETED WITH PENDING VALIDATION.** Implementado y validado en local.
- Pendientes: el despliegue y la recepción real en un buzón (**BLOCKED EXTERNAL CONFIGURATION** hasta que CER haga la prueba con su proveedor).

## 1. Conciliación: lo esperado frente a lo que hay

| Esperado | Implementado | Evidencia | Brecha |
|---|---|---|---|
| CP1 en `dev` | Sí | `2cc1e8b` (merge de MR !104); migraciones hasta `0022_mail_test_send` | — |
| CP1 desplegado en DigitalOcean | Según tu captura, sí: Outbound email aparece **Verified** y con la lista de un buzón (la interfaz de CP1) | Captura del PO | **UNVERIFIED desde aquí:** no tengo acceso al build de DigitalOcean |
| Plantillas estratégicas | No existían | El reporte de CP1 lo decía: «CP2/CP3 NOT STARTED» | **Era trabajo pendiente, no un defecto.** Resuelto en B |
| Destino libre en T0 | CP1 lo había **sustituido** por una lista cerrada | `politica_de_prueba.exigir_destino` | **Contradice V1.2.** Corregido aquí |
| «Verified» = entregado | No: Verify solo autentica | `backend.check()` no envía nada | — |

## 2. Qué cambia en A
- **El administrador de plataforma escribe la dirección** en Platform › Outbound email › Verify › *Send Test Email*.
  - El campo viene precargado con su correo, y `MAIL_TEST_RECIPIENTS` aparece como sugerencias (`datalist`).
  - **Verify** sigue siendo un botón aparte y no envía.
- **Validación en el servidor** (`politica_de_prueba.exigir_formato`):
  - una sola dirección con formato válido, de 254 caracteres como máximo;
  - sin saltos de línea, comas, punto y coma ni `<>`;
  - si no, 422. Campos extra (`cc`, `bcc`), 422 (`extra="forbid"`).
- **Se mantiene todo lo de CP1:**
  - `require_platform_admin` (403 para cualquier otro);
  - el presupuesto compartido de 5 cada 15 minutos (429), reservado antes de enviar en `mail_test_send` bajo candado;
  - «[TEST]» una vez, banner y `X-CER-Route-Test`;
  - **solo el proveedor elegido**, y `not_configured` sin pasar al de respaldo;
  - resultados honestos y auditoría sin el texto del proveedor.
- **El mismo endpoint** (`POST /api/platform/integrations/{key}/test-message`): solo cambia la regla del destino. **No hay endpoint nuevo.** `GET …/test-targets` pasa a dar sugerencias.
- **Las pruebas de plantillas (T1-T4) siguen con destinos cerrados** (propio correo o `MAIL_TEST_RECIPIENTS`), como pide V1.2.

## 3. Pruebas

| Lote | Resultado |
|---|---|
| `tests/integration/test_mail_test_policy.py` + `test_platform_diagnostics.py` + `test_activity_email_test_send.py`. Incluye: dirección externa aceptada; 7 formatos inválidos → 422; `cc`/`bcc` → 422; tenant → 403; presupuesto compartido y concurrente; sin respaldo oculto; credenciales malas sin filtrar | **33/33 PASS** |
| E2E T0, escritorio y móvil: campo editable precargado, Verify aparte, sin scroll horizontal | **2/2 PASS**, capturas en `var/screenshots/mail-provider-test/` |
| `npm run check` / `npm run build:prod` | exit 0 / exit 0 |

**Hallazgos (todos de la herramienta o del test, CONFIRMED):**
- Dos ediciones con heredoc rompieron cadenas con `\n`; se corrigieron antes de ejecutar.
- Con `list=`, el campo es un «combobox» y no un «textbox», así que el test lo localiza por su etiqueta.

## 4. Git
Commit `328dd6c` en la rama `feature/mail-u01-cp2-cp3`. Va en el mismo MR que B y C.
