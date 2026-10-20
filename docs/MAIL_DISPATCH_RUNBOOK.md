# Runbook — envío de los correos de actividad (RTE-MAIL-CP4)

Para quien opera CER Route en DigitalOcean. Los cuatro correos son: Midday Motivation, End of Day Recognition, Strategic Midday Report y Strategic End-of-Day Report.

> **Estado por defecto: APAGADO.** Con la configuración de fábrica no sale ningún correo real. Cada paso de esta guía que lo enciende exige el GO del Product Owner.

## 1. Piezas
| Pieza | Dónde | Qué hace |
|---|---|---|
| Programador interno | La app web (`PlatformScheduler`), cada minuto, solo en la réplica líder | Manda lo que venció. Da la precisión (End Work + 20 min ± 1 min) |
| Scheduled Job `route-mail-reconcile` | App Platform, cada 15 min (`*/15 * * * *`, `Etc/UTC`) | Recoge lo que venció y no salió (app caída, reinicio) |
| Botón **Send now** | Activity Emails › plantilla › Generate report | Recupera a mano un envío que tocaba y no salió |
| Botón **Resend** | El mismo diálogo, cuando el correo ya salió o su resultado es incierto | Vuelve a mandarlo, con los datos de ahora. Cada reenvío queda numerado en `activity_email_resend` |
| Registro `activity_email_delivery` | Base de datos | Una fila por correo y día; la clave única impide duplicados entre los tres caminos |

Los tres llaman al mismo despacho, `app/routers_api/activityemails/delivery.py`.

**A quién se puede elegir en Generate report:**
- Un administrador ve a todos los de la compañía.
- Un mando (CEO, COO, Regional Manager) ve a su rama **y a sí mismo**, para pedir su propio reporte. La pestaña de destinatarios sigue sin incluirle: un mando no se activa sus propios correos.

Hacen falta `route.activityemails.manage` para entrar a la pantalla y `route.activityemails.preview` para generar. Las dos se asignan a demanda.

**Reenviar (Resend):**
- Lo autoriza **solo** la capacidad `route.activityemails.resend`, a demanda. `send` no la incluye.
- Se ofrece cuando el correo del día ya fue aceptado por el proveedor o quedó con resultado incierto. No mira el interruptor de la persona en Recipients ni la hora de vencimiento.
- Sigue respetando `MAIL_REAL_SEND_TYPES` (el kill switch por tipo), un destinatario activo con correo válido y el límite de 20 envíos a mano por hora y persona.
- Va al correo de la cuenta del destinatario, nunca a una dirección escrita. Un doble clic no manda dos: el segundo responde 409.

## 2. Interruptores (variables de la App)
| Variable | Por defecto | Efecto |
|---|---|---|
| `MAIL_AUTOMATION_ENABLED` | `false` | Interruptor general del envío automático (programador y cron). **Kill switch**: ponerla en `false` lo detiene en la pasada siguiente |
| `MAIL_AUTOMATION_DRY_RUN` | `true` | Con la automatización encendida, solo cuenta y registra en el log qué enviaría (`would_send`); no reserva ni envía |
| `MAIL_REAL_SEND_TYPES` | vacía | Tipos con envío real permitido (automático **y** Send now), separados por comas. Es el kill switch por tipo |
| `MAIL_STRATEGIC_CUTOFF` | vacía | Hora local máxima (HH:MM) del reporte estratégico de cierre (DP-CUTOFF). Vacía: sin cierre completo del equipo no hay reporte final |
| `MAIL_RECOVERY_WINDOW_HOURS` | `2` | Cuántas horas atrás recoge un envío vencido (DP-RECOVERY). Evita mandar de golpe correos viejos |

Además, **por persona**: los interruptores de Activity Emails › Recipients, todos apagados por defecto.

## 3. Instalar el Scheduled Job
La definición versionada está en `_cer_delivery/APP_SPEC_cerroute-dev.yaml` (job `route-mail-reconcile`, más las dos variables).

**Desde la consola:** Apps › cerroute-dev › **Create › Create resources from source code** › mismo repositorio y rama (`dev`) › Resource type **Job** › Job trigger **On a schedule** › cron `*/15 * * * *`, zona `Etc/UTC` › Run command:
```
python -m app.routers_api.activityemails.jobs --once
```

**O desde la App Spec:** Settings › App Spec › Edit. Se **añade** el bloque del job a la spec actual; no se sustituye la spec entera por el archivo del repositorio.

El job hereda las variables de la App: base de datos, `PLATFORM_MASTER_KEY` (necesaria para el proveedor de correo) y `MAIL_*`.

## 4. Comprobar que funciona
1. **Consola de la App:** `python -m app.routers_api.activityemails.jobs --once`. Imprime una línea como esta y termina con código 0:
   ```
   MAIL DISPATCH | source=reconcile enabled=False dry_run=True checked=0 due=0 claimed=0 accepted=0 ...
   ```
2. **Activity › Jobs › route-mail-reconcile:** deben verse invocaciones cada 15 minutos. **Runtime Logs** del job: las mismas líneas `MAIL DISPATCH`.
3. **Programador interno:** en Runtime Logs del servicio web, líneas `MAIL DISPATCH | source=schedule …`. Solo aparecen con `MAIL_AUTOMATION_ENABLED=true`; apagado, la pasada vuelve sin escribir nada.

**Significado de los contadores:**

| Contador | Significa |
|---|---|
| `checked` | Combinaciones persona-tipo-día evaluadas |
| `due` | Correos que tocaban |
| `not_enabled` | Tipo no habilitado en `MAIL_REAL_SEND_TYPES` |
| `would_send` | Ensayo: lo que habría enviado |
| `accepted` | Aceptados por el proveedor |
| `retry` | Fallos que se reintentarán |
| `failed` | Fallos definitivos |
| `unknown` | Resultado incierto |
| `skipped` | No había correo que mandar |
| `errors` | Fallos de la propia pasada |

## 5. Encender (solo con GO del PO)
1. **Proveedor de correo verificado:** Platform › Outbound email › **Verify** en `healthy`, y la prueba real (Send Test Email y las cuatro Send test) confirmada en un buzón.
2. **Ensayo:** `MAIL_AUTOMATION_ENABLED=true` con `MAIL_AUTOMATION_DRY_RUN=true`. Revisar los `would_send` en los logs durante un día.
3. **Un tipo y pocas personas:** `MAIL_REAL_SEND_TYPES=midday_motivation`, activar el interruptor solo a 1-2 personas en Recipients y `MAIL_AUTOMATION_DRY_RUN=false`.
4. **Ampliar tipo a tipo**, a medida que se cierran sus decisiones:
   - DP-TIMEZONE, para todos;
   - DP-WEEK, para los de cierre;
   - DP-CUTOFF y DP-TEAM, para el estratégico de cierre;
   - DP-NOTES, si algún día se quieren notas reales.

## 6. Si algo va mal
| Síntoma | Qué hacer |
|---|---|
| Hay que parar ya | `MAIL_AUTOMATION_ENABLED=false`, o quitar el tipo de `MAIL_REAL_SEND_TYPES`. Efecto en la pasada siguiente, sin desplegar código |
| `retry` sube | El proveedor falla (credenciales, red). Verify dirá el paso. Los reintentos son automáticos con espera creciente (5 min, 15 min, 1 h), hasta 5 intentos |
| `unknown` | El proveedor pudo recibirlo o no (tiempo agotado, o un proceso cayó con la reserva abierta). **No se reenvía solo.** Se mira el buzón del destinatario; si no llegó, quien tenga `route.activityemails.resend` lo reenvía con **Resend** |
| El cron no corre | Activity › Jobs. Mientras tanto, el programador interno sigue enviando, y **Send now** recupera a mano lo que venció |
| Volver atrás (rollback) | Apagar las variables. El código puede quedarse: apagado no hace nada. Las migraciones `0025` (reenvíos) y `0024` (envíos) se pueden bajar, pero se pierde su historial (la auditoría queda en `audit_event`) |

## 7. Qué no hace
- No manda correos viejos al encenderlo: solo los vencidos dentro de `MAIL_RECOVERY_WINDOW_HOURS`.
- No cierra jornadas, no cambia End Work y no envía notas reales.
- No envía a direcciones escritas: siempre al correo de la cuenta del destinatario, con su interruptor encendido.
