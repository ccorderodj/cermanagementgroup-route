# CER Route · H-2 + R-1 · Evidencia complementaria para certificación

**Reporte 001** · 8 de octubre de 2026
**Alcance:** los cinco puntos que el Product Owner pidió antes de certificar R-1.
Ningún cambio de código, de permisos ni de pruebas.
**Base evaluada:** `dev` en `27dd30b`

---

## Status

`COMPLETED WITH PENDING VALIDATION`

| Punto | Estado | Evidencia |
|---|---|---|
| 1 · Validación conjunta H-2 + R-1 | **VALIDATED** | §2 |
| 2 · Today vs User Activity, mismo supervisor y fecha | **VALIDATED en copia local**, con una salvedad de redondeo | §3 |
| 3 · Viaje 460 en el entorno operativo | **BLOCKED** — sin acceso; consulta preparada | §4 |
| 4 · Compatibilidad de consumidores | **VALIDATED**, con una corrección a R-1 001 | §5 |
| 5 · Fallo preexistente documentado | **SIN CAMBIOS**, sigue fallando igual | §6 |

---

## 1 · Antes de todo: los dos MR ya están fusionados

La instrucción «no fusionar los MR sin autorización de CER» parte de que siguen
abiertos. **No lo están:**

| MR | Merge commit | Autor | Hora (UTC) |
|---|---|---|---|
| !72 · H-2 | `2087d37` | César Cordero | 08/10 19:10 |
| !76 · R-1 | `27dd30b` | César Cordero | 08/10 21:02 |

Se fusionaron desde GitLab, no desde este trabajo: el agente no fusiona. `dev`
local y `origin/dev` coinciden en `27dd30b`.

**No sé si `dev` ya está desplegado**, y no puedo comprobarlo. Si lo está, H-2 y
R-1 están en manos de usuarios sin certificar, y el §5 —el bundle cacheado— deja
de ser hipotético.

**Lo que sí tiene de útil:** `dev` contiene ahora H-2 y R-1 juntos, que es
exactamente el estado que el punto 1 pide validar. Toda la evidencia de este
documento se tomó sobre ese estado integrado, no sobre las ramas por separado.

---

## 2 · Validación conjunta H-2 + R-1 · `VALIDATED`

### 2.1 · No comparten un solo archivo

```
H-2 (2087d37)  live/dao.py · RouteTodayLivePage.tsx · test_live_today.py · E2E H-2
R-1 (27dd30b)  activityexplorer/{dao,router,schemas}.py · ExplorerActivityCards.tsx
               · types/index.ts · test_activity_explorer.py · E2E R-1

archivos en común: ninguno
```

No hay conflicto de código posible. Lo que podría existir es una **interacción de
comportamiento** —las dos pantallas leen los mismos viajes— y eso es lo que mide
la regresión y el cruce del §3.

### 2.2 · Regresión sobre `dev` integrado · 1089 ejecutados · 1 fallo preexistente

```
uv run pytest -m "not browser"          17 min 19 s · exit 1

1073 PASS
   1 FAILED   test_provisioning_alignment   (preexistente, §6)
   0 errores
  15 skipped
```

**Idéntica a la regresión de R-1 sobre su rama**: el mismo número de
correctos, el mismo único fallo, en la misma posición del orden de ejecución.
Integrar H-2 y R-1 no movió ningún resultado. Dentro de esa cifra están las
suites de las dos entregas —`test_live_today` (H-2) y `test_activity_explorer`
(R-1)— y la prueba que cruza las millas entre pantallas,
`test_mileage_cross_surface`.

### 2.3 · E2E de las dos entregas · 4/4 PASS · exit 0

```
H-2  test_escritorio_una_fila_y_el_panel_correcto                PASSED
H-2  test_movil_una_fila_y_su_detalle                            PASSED
R-1  test_escritorio_el_detalle_muestra_el_trayecto_sin_parada   PASSED
R-1  test_movil_conserva_su_disposicion_aprobada                 PASSED
4 passed in 59 s
```

Capturas regeneradas sobre `dev`, fuera del árbol versionado:
`var/screenshots/h2/` (4) y `var/screenshots/r1/` (2).

El bundle se reconstruyó antes de ejecutarlas: el existente era anterior a dos
fuentes de R-1. Un E2E contra un bundle viejo daría un verde que no prueba nada,
y ya pasó una vez en este proyecto.

---

## 3 · Today vs User Activity, mismo supervisor y fecha · `VALIDATED en copia local`

### 3.1 · Dónde y cómo

- **Entorno:** copia local de `cerroute` (`db-dev-cer-route`, compañía `1`), con
  datos **reales** hasta el 08/10/2026 y **desfasada** respecto a las capturas
  del Product Owner (reconciliación 002, §0). **No es producción.**
- **Método:** las mismas funciones que sirven las pantallas —`today_rows` de
  Today, `agregados_por_dia` y `paradas_del_dia` de User Activity— sobre el
  08/10, para **todos** los supervisores con jornada. Sólo lectura.

### 3.2 · Resultado

```
user  supervisor          Today  UA total  UA suma   Today  UA     Today  UA
                          millas   millas  detalle   activ. activ. pend.  pend.
 274  Frank Tijerino         0.0      0.0      0.0      0      0   no     no
 271  Humberto Aleman        0.0      0.0      0.0      1      1   no     no
 270  Karina Aguirre        62.5     62.5     62.5      1      1   sí     sí
 272  Lazaro Muniz          21.7     21.7     21.8      3      3   no     no
 269  Manuel Garcia         64.5     64.5     64.5      2      2   sí     sí
 267  Rodrigo Test2          0.0      0.0      0.0      3      3   sí     sí
 273  Xochilt Obando        36.5     36.5     36.4      3      3   no     no
```

| Comprobación | Resultado |
|---|---|
| Millas: Today = total de User Activity | **7 de 7** |
| Actividades: Today = contador de User Activity | **7 de 7** |
| Pendiente: Today = User Activity | **7 de 7** |
| Suma del detalle = total | **5 de 7 exactos; 2 a 0,1 mi** |

### 3.3 · La salvedad: el redondeo · `CONFIRMED`

```
user 272: 34 995 m → 21,7 mi      tarjetas: 9,0 + 12,8 + 0,0 = 21,8
user 273: 58 686 m → 36,5 mi      tarjetas: 0,0 + 12,7 + 23,7 = 36,4
```

El total redondea **una vez**, sobre la suma de metros. Cada tarjeta redondea
**su** viaje. La suma de lo visible puede separarse del encabezado hasta
±0,05 mi por tarjeta.

- **No lo introduce R-1.** Las tarjetas de parada ya se sumaban así antes; R-1
  sólo añade tarjetas.
- **Sí corrige lo que afirmé en R-1 001** («el total se reconcilia sumando lo
  visible»). La prueba de navegador lo comprobaba con un solo viaje con millas, y
  ahí el redondeo no puede aparecer. La afirmación correcta es: *el detalle
  explica el total salvo redondeo a la décima*.
- **Cuál de los dos números es el correcto** es una decisión de producto, no un
  defecto: el total sobre metros es el más exacto. No se cambia nada sin
  autorización.

### 3.4 · El caso observado, en la copia local

```
user 270 · 08/10 · Today 62,5 mi pendiente · User Activity 62,5 mi pendiente
   trip 447  recruiting  62,5 mi  calculado   con parada
   trip 460  home         0,0 mi  pendiente   sin parada   ← ahora aparece
   trip 464  office       0,0 mi  pendiente   sin parada   ← ahora aparece
```

Las dos pantallas dicen lo mismo, y el regreso a casa **existe en el detalle**.
En esta copia todavía no tiene millas porque se tomó antes de calcularlas (§4).

---

## 4 · Viaje 460 en el entorno operativo · `BLOCKED`

**No tengo acceso a la base del entorno de las capturas**, y no voy a
materializar credenciales para conseguirlo. Lo que sí está validado es lo que
depende del código: en la copia local el viaje 460 aparece en el detalle, como
`Home`, sin parada y marcado pendiente (§3.4).

Lo que falta depende de un dato que sólo existe allí: **cuántas millas tiene
hoy el viaje 460**. Una consulta de sólo lectura lo cierra:

```sql
SELECT t.id, t.current_purpose, t.status,
       tm.state,
       ROUND(COALESCE(tm.total_meters, 0) / 1609.344, 1) AS millas,
       (SELECT count(*) FROM activity_execution ae
         WHERE ae.trip_id = t.id)                           AS paradas,
       ws.user_id, ws.session_date
FROM trip t
JOIN work_session ws ON ws.id = t.work_session_id
LEFT JOIN trip_mileage tm
       ON tm.trip_id = t.id AND tm.company_id = t.company_id
WHERE t.id IN (447, 460, 464);
```

**La consulta está probada**, en la copia local, para que no falle por una
columna mal escrita al ejecutarla allí:

```
447  recruiting  closed   calculated           62.5  1 parada   user 270  2026-10-08
460  home        closed   pending_calculation   0.0  0         user 270  2026-10-08
464  office      arrived  pending_calculation   0.0  0         user 270  2026-10-08
```

**Resultado que cierra el punto:** `trip 460 · home · calculated · ≈ 63,0 mi ·
0 paradas`. Después, abrir User Activity para ese supervisor y el 08/10: debe
haber una tarjeta `Home` con esa cifra, `Outcome —`, y el encabezado debe
cuadrar con la suma salvo redondeo (§3.3).

**Si devuelve otra cosa**, la diferencia de 63,0 mi tiene una segunda causa que
no se ha encontrado, y conviene saberlo antes de certificar.

---

## 5 · Compatibilidad de consumidores · `VALIDATED`, con una corrección

### 5.1 · Quién consume el contrato

| Consumidor | ¿Afectado? |
|---|---|
| Página User Activity (bundle actual) | No: su esquema Zod acepta los nulos |
| `/api/v1` (integración entre aplicaciones) | **No expuesto**: el explorador no está en la API versionada |
| Superficie pública sin sesión | **No expuesto** |
| Webhooks | **No emite** |
| Otros módulos del backend | Ninguno lo importa |
| Pruebas | `test_activity_explorer`, `test_mileage_cross_surface`, `test_rte08_*`, E2E: en la regresión |

El único consumidor real es la propia pantalla.

### 5.2 · La corrección: un navegador con el bundle anterior · `CONFIRMED`

En R-1 001 escribí que los cambios de contrato eran «compatibles hacia atrás».
**Para el servidor, sí. Para un navegador con el bundle anterior en caché, no.**

El bundle se sirve siempre en la misma URL (`/static/javascript/main.js`), sin
huella en el nombre. Un administrador que tenga en caché la versión anterior a
R-1 valida la respuesta con el esquema antiguo. Comprobado con Zod real:

```
fila con parada   esquema anterior: OK
fila sin parada   esquema anterior: RECHAZA activity_execution_id, started_at
```

**Efecto:** en un día con un viaje sin parada —casi todos, por el regreso a
casa— la vista de día muestra un error de contrato en lugar del detalle.

**Lo que no hace:** no enseña datos falsos ni corrompe nada; falla de forma
visible. Se resuelve recargando la página una vez que el navegador pide el
bundle nuevo.

**Acción operativa, sin cambio de código:** tras desplegar `dev`, pedir a los
administradores que recarguen User Activity (`Ctrl+F5`). Que el bundle lleve una
huella en el nombre lo evitaría para siempre, pero es un cambio de build fuera
de este alcance, y se anota, no se propone.

---

## 6 · El fallo preexistente · `SIN CAMBIOS`

```
FAILED test_provisioning_alignment::
       test_the_two_product_roles_hold_exactly_twelve_and_two_capabilities
'route_admin': 14 capacidades, se esperaban 12
```

Las dos de más son `route.live.read` (RTE07) y `route.activity.read` (RTE08).
**No se han tocado permisos, roles, semillas ni la prueba.** Esa prueba existe
para que una ampliación de privilegio no pase sin aprobación de CER, y sigue
haciendo su trabajo: falla hasta que CER decida.

---

## 7 · Hallazgo incidental · comentario obsoleto en una prueba

`tests/integration/test_mileage_cross_surface.py:147` dice que un viaje sin
parada «suma sus millas al día y no tiene tarjeta». **Desde R-1 sí la tiene.**
La prueba sigue siendo correcta —siembra una parada para mirar su tarjeta— pero
el comentario describe el comportamiento anterior.

No se corrige: el Product Owner pidió no hacer cambios adicionales. Es una
línea, para el siguiente cambio que toque ese archivo.

---

## 8 · Estimación

| Tarea | Volumen | Complejidad | Horas-agente |
|---|---|---|---|
| Estado de los MR y solapamiento de archivos | — | determinista | 0,2 |
| Cruce Today vs User Activity y causa del redondeo | ~80 LoC de script | dominio | 0,8 |
| Consumidores del contrato y prueba con Zod | ~30 LoC de script | integración | 0,5 |
| Consulta operativa, probada en local | ~15 LoC SQL | determinista | 0,2 |
| Bundle, regresión y E2E | 21 min de máquina | navegador | 0,6 |
| Reporte y entrega | ~330 líneas | — | 1,0 |
| **Total** | | | **≈ 3,3 h** |

No hubo estimación previa: la petición llegó y se ejecutó. Margen pendiente: el
§4, cuando CER ejecute la consulta, son **0,3 h** si el resultado es el
esperado; si no lo es, abre una investigación que no se puede estimar sin el
dato.

---

## 9 · Git

| | |
|---|---|
| Rama | `docs/h2-r1-certification-evidence` |
| Base | `dev` en `27dd30b` |
| Cambio | sólo este reporte |
| Fusionado | **No.** CER certifica |

---

## 10 · Para certificar

1. **Ejecutar la consulta del §4** en el entorno de las capturas y abrir User
   Activity para ese supervisor y fecha. Es lo único que falta.
2. **Decidir qué hacer con los MR ya fusionados** (§1), y si `dev` está
   desplegado, avisar a los administradores de que recarguen (§5.2).
3. **Aceptar o no la salvedad de redondeo** (§3.3) como comportamiento
   certificado.
4. **El fallo de las 14 capacidades** sigue esperando decisión de CER (§6).

Nada de R-2, H-3 ni R-3 se ha implementado.
