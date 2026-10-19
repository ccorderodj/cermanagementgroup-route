# CER Route — Login: una pestaña sin cookies ya entra, y los errores dicen qué pasa

**Reporte** · 19 de octubre de 2026
**Status: COMPLETED WITH PENDING VALIDATION.** Corregido y probado en local. Pendiente: desplegar y confirmar en el teléfono de un usuario.

## 1. El incidente
- **El síntoma:** Manuel Garcia (`mgarcia@cermanagementgroup.com`, Supervisor) no podía entrar desde el móvil. La pantalla decía **«Login failed — Uh oh! Something went wrong.»** y, en lugar del nombre de la compañía, **«Company»**.
- **Lo que se hizo:** soporte entró con su cuenta desde escritorio y cerró la jornada del viernes. Después él pudo entrar.
- **Lo que muestran los datos** (copia de la base de DigitalOcean):
  - la cuenta está activa, con la pertenencia a `cerroute` activa;
  - el login de soporte fue a las 12:48 UTC y el cierre de la jornada del viernes a las 12:49;
  - él abrió la jornada de hoy a las 12:53 y trabajó con normalidad.
- **El login no mira las jornadas**, así que cerrar la del viernes no pudo ser lo que lo arregló. Muy probablemente fue coincidencia.

## 2. La causa
**LIKELY.** La línea `"POST /api/public/auth/login … 403"` en los Runtime Logs lo confirmaría.
- **El navegador no tenía las cookies.** «Company» aparece solo cuando falta la cookie `app_data`, y esa cookie la escribe el servidor cada vez que sirve una página. Lo normal es que la pestaña de login se restaurara días después sin volver a pedirse al servidor, o que el navegador borrara sus cookies.
- **Sin la cookie CSRF, el login se rechaza con 403** antes de mirar las credenciales. Es la protección contra CSRF (`csrf.py`).
- **Indicio a favor:** en la captura el formulario **sigue relleno**. Con un 401 (contraseña o correo incorrectos) el interceptor de Axios habría recargado la página y vaciado el formulario.

**Tres defectos nuestros que lo agravaban (CONFIRMED en el código):**
1. **El aviso nunca decía el motivo.** `LoginForm.tsx` pasaba el texto del error a `extractErrorMessage`, que espera un objeto con `detail`. Recibía un texto, devolvía vacío y salía siempre «Uh oh! Something went wrong.», fuera contraseña incorrecta, falta de cookies o error del servidor.
2. **No había recuperación.** Una pestaña sin cookies no podía entrar hasta recargarla a mano, y nada lo decía.
3. **Una contraseña incorrecta recargaba la página.** El interceptor de 401 trataba el 401 del propio login como «sesión caducada» y mandaba a `/login?next=…`, vaciando el formulario.

## 3. El arreglo

| Pieza | Cambio |
|---|---|
| `app/core/security/csrf.py` | El 403 lleva un código estable: `{"code": "csrf_missing" \| "csrf_mismatch", "message": …}`. La interfaz reacciona al código, no a la frase |
| `entities/users/.../login/login.ts` | Si el login responde `csrf_missing` o `csrf_mismatch`, pide de nuevo la página actual (el servidor vuelve a emitir las cookies) y **reintenta una vez**. Traduce cada fallo a un mensaje claro: credenciales, sin conexión, página desactualizada, correo incompleto, servidor no disponible |
| `features/Login/ui/LoginForm.tsx` | Muestra el mensaje real del servicio |
| `shared/api/api.ts` | `LOGIN_ENDPOINT`; el interceptor **no** redirige cuando el 401 viene del propio login |

**Sin cambios en:** la seguridad (CSRF sigue exigiéndose y el reintento lleva el testigo nuevo), las cookies, los permisos y la base de datos. La respuesta del servidor sigue sin distinguir «no existe» de «contraseña incorrecta», a propósito (AUD-BE-006).

## 4. Pruebas (local)

| Lote | Resultado |
|---|---|
| E2E `test_una_pestana_sin_cookies_entra_igual`: login real en móvil, se borran las cookies con la pestaña abierta y se pulsa Sign In | **Sin el arreglo: FAIL** (no entra, como Manuel). **Con el arreglo: PASS** (entra y recupera la cookie CSRF) |
| E2E `test_contrasena_incorrecta_lo_dice_y_no_recarga` | **PASS**: dice «Incorrect email or password», no «Something went wrong», y conserva el correo sin recargar |
| `tests/integration/test_password_reset_and_csrf.py`, más el nuevo `test_un_login_sin_testigo_csrf_lo_dice_con_su_codigo` | **13/13 PASS** |
| `npm run check` / `npm run build:prod` | exit 0 / exit 0 |
| Regresión completa | **1.469 recogidos, 1 FAIL preexistente**, exit 1, 1.124 s |

**Hallazgo del test (CONFIRMED, solo del test):** «Password» coincidía también con el botón «Show password»; se localiza el campo por su nombre exacto.

## 5. Acciones para CER
- **Que Manuel cambie su contraseña.** La captura del incidente la muestra en claro. Borrar la imagen de donde se compartió.
- **La jornada del viernes 16-10 de Manuel** se cerró el lunes a las 12:49 UTC, con un odómetro final **metido a mano y aprobado solo**. Su hora de cierre y sus millas no son las reales: conviene revisarla en Odometer Exceptions o en Activity.
- **Confirmar la causa (opcional):** en Runtime Logs, el 19-10 antes de las 12:48 UTC, buscar `auth/login`. Un `403` lo confirma.
- **Mientras no se despliegue:** si a alguien le vuelve a pasar, que **recargue la página** antes de reintentar.

## 6. Regresión completa y Git
`uv run pytest tests --ignore=tests/e2e`: **1.469 recogidos, 1 FAIL**, exit 1, 1.124 s. Los otros 1.468 pasaron u omitieron; el desglose no quedó capturado.
- **Único fallo:** `test_provisioning_alignment::…twelve_and_two_capabilities`, **preexistente desde RTE09** (espera 12 capacidades para `route_admin` y hay 16). Sin relación con este cambio.
- **Resto de E2E:** NOT RUN. Inician sesión por la API (`abrir_sesion`), no por el formulario, así que no pasan por el cambio.
- **Git:** rama `fix/login-errors-csrf`, desde `dev` `84646fa`. Sin migraciones.

## 7. Esfuerzo
≈ **2 horas-agente**: diagnóstico, arreglo, pruebas en navegador y reporte.
