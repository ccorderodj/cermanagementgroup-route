# CER Route — El despliegue repone la configuración, en vez de perderla
## Reporte 001 · Paso 2 de 3

**Origen:** la integración de routing desapareció del entorno compartido y nada podía reponerla
**Rama:** `feature/converge-deploy-configuration` (desde `dev`)
**Fecha:** 2026-10-07

---

## 1. Resultado ejecutivo

La causa de fondo del incidente no fue que algo borrara la integración de TomTom. Fue que **nada en el repositorio declaraba que esa integración debía existir**.

Verificado: en todo el código, el único sitio que crea esa fila es la pantalla de administración (`settings_router.py:188`). Ninguna migración la toca — sólo la crea la línea base. Así que cuando desapareció, no había nada que la repusiera, y el kilometraje estuvo **seis días sin calcular**: 54 viajes con evidencia completa terminalizados por un motor que no existía.

**Ahora el despliegue la repone.** Un paso nuevo, `converge`, va detrás de las migraciones y reconcilia la configuración que un despliegue puede dejar atrás:

```text
Alembic     ->  el ESQUEMA        (ya existía)
converge    ->  la CONFIGURACIÓN  (esto)
```

Y cubre las tres clases que tienen el mismo problema, no sólo la que mordió:

| Qué | Historia |
|---|---|
| Capacidades y concesiones a los roles | **mordió cuatro veces** |
| Valores estándar de cada compañía | no ha mordido; morderá en cuanto un checkpoint añada una lista |
| Integración `road_routing` | **mordió una vez, seis días** |

Lo que impide que vuelva a ocurrir no es el comando: es el **test de lista cerrada**. Cada función de siembra del repositorio tiene que estar clasificada a mano —converge, o no converge con su motivo escrito—. Añadir una `seed_*` nueva sin clasificarla rompe la suite. Probado por mutación.

Este es el **paso 2 de 3**. El paso 1 (avisar cuando se pierde una configuración) está en el MR !64.

---

## 2. El ajuste del App Spec

Dos cambios, y nada más. El spec completo y comentado está en `_cer_delivery/APP_SPEC_cerroute-dev.yaml`.

**Uno — una variable nueva:**

```yaml
- key: ROUTE_TOMTOM_API_KEY
  scope: RUN_TIME
  type: SECRET
  value: <<< PEGAR AQUI LA CLAVE DE TOMTOM >>>
```

`RUN_TIME` basta: un job corre en tiempo de ejecución, igual que `DB_PASS`, que el job ya usa. La clave se guarda **cifrada** en la base con `PLATFORM_MASTER_KEY`, que ya está presente. Nunca en claro.

**Dos — una línea en el `run_command` del job `migrate`:**

```bash
set -e
...
python -m alembic -c app/alembic.ini upgrade head
python -m app.db.scripts.converge          # ← nuevo
```

`set -e` ya estaba, y es lo que hace que un fallo de la convergencia detenga el despliegue en vez de dejarlo salir verde.

**Los secretos existentes no se tocan.** El archivo entregado lleva marcadores explícitos en su lugar para que nadie los sustituya por error al copiar.

---

## 3. Lo que `converge` hace, y lo que no

```text
app/db/scripts/converge.py

PASOS = (
    capacidades y concesiones de rol   -> reutiliza align_role_capabilities
    valores estándar por compañía      -> provision_standard_values, todas
    integración road_routing           -> desde ROUTE_TOMTOM_API_KEY
)
```

* **Sólo añade.** No revoca, no desactiva, no borra.
* **Es idempotente.** La segunda pasada dice `total de cambios: 0`.
* **No crea compañías ni usuarios.** Eso es una decisión, no una reconciliación, y sigue siendo del `bootstrap`.
* **Deja rastro** en `platform_audit_event`, sin actor, porque no lo pidió una persona desde una pantalla.

### Las tres reglas de la integración, por orden

1. **Sin `ROUTE_TOMTOM_API_KEY`, no toca nada.** Un entorno con motor auto-alojado por `ROUTE_ROUTING_URL`, o que todavía no eligió proveedor, no quiere que un despliegue le invente uno.
2. **Si la fila existe, se respeta.** Que un administrador haya elegido OSRM, o la haya deshabilitado a propósito, es decisión suya. Esto **repone lo que falta; no corrige lo que hay.**
3. **El secreto se guarda si falta.** Es el caso de la fila que sobrevivió pero perdió su credencial: el adaptador no se monta y el síntoma es idéntico a no tener integración.

`verified_at` queda en nulo a propósito. Este comando **configura, no verifica**. Quien verifica es el chequeo `road_routing`, pidiendo una ruta real — y esa separación es la que evita que un despliegue se declare sano a sí mismo.

---

## 4. Validación

**103 tests · 0 fallos · 0 errores · 0 saltados · todos `exit 0`**, por lotes separados.

### Nuevos

| Archivo | Tests | Qué fija |
|---|---:|---|
| `tests/integration/test_converge.py` | 9 | repone, cifra, es idempotente y **no pisa decisiones** |
| `tests/test_converge_registry.py` | 5 | la lista cerrada: toda siembra queda clasificada |

**Cinco de los nueve son del tipo «no tocó lo que no debía»**, y es deliberado: la mitad peligrosa de este cambio no es que no reponga, es que reponga de más. Un despliegue que revierte en silencio la decisión de un administrador sería un problema peor que el que resuelve.

| Test | Defiende |
|---|---|
| `test_no_cambia_el_proveedor_que_un_administrador_eligio` | OSRM configurado a mano sigue siendo OSRM |
| `test_respeta_una_integracion_deshabilitada_a_proposito` | deshabilitar es una decisión, no una ausencia |
| `test_sin_la_variable_de_entorno_no_toca_nada` | no inventa integraciones |
| `test_no_crea_companias_ni_usuarios` | converger ≠ crear |
| `test_la_segunda_ejecucion_no_cambia_nada` | se puede poner en cada despliegue |

Y `test_la_clave_queda_cifrada_y_se_puede_volver_a_leer` comprueba las dos mitades: que el texto claro **no** aparece en la base, y que `unseal` la recupera.

### La red que impide que esto vuelva a pasar, probada por mutación

Añadí una función `seed_algo_nuevo` sin clasificar:

```text
1 failed, 4 passed
  test_toda_siembra_del_repositorio_esta_clasificada
E  hay funciones de siembra sin clasificar: ['seed_algo_nuevo'].
   Decide si el despliegue debe ejecutarlas (añádelas a converge.PASOS y
   márcalas CONVERGE) o escribe el motivo por el que no puede.
```

Falla, nombra la función y dice qué archivo editar. Retirada, 5/5 verde.

Las exclusiones llevan su motivo escrito, y hay un test que comprueba que **no estén vacías**:

```text
seed_company  -> crea una compañía: un despliegue no puede inventar tenants
seed_admin    -> crea un usuario con contraseña generada
seed_states   -> los estados donde opera un tenant son decisión suya
seed_key_for  -> no siembra; coincide por el nombre, no por lo que hace
```

### Lotes

| Lote | Tests | Fallos | Err | Exit |
|---|---:|---:|---:|---:|
| `test_converge.py` (nuevo) | 9 | 0 | 0 | 0 |
| `test_converge_registry.py` (nuevo) | 5 | 0 | 0 | 0 |
| `test_rte07_admin_access.py` | 11 | 0 | 0 | 0 |
| `test_rte08_activity_capability_alignment.py` | 8 | 0 | 0 | 0 |
| `test_platform_config_store.py` | 12 | 0 | 0 | 0 |
| `test_platform_diagnostics.py` | 17 | 0 | 0 | 0 |
| `test_standard_value_catalog.py` | 12 | 0 | 0 | 0 |
| `test_permission_catalog.py` | 7 | 0 | 0 | 0 |
| `test_public_surface.py` | 14 | 0 | 0 | 0 |
| `test_road_routing_wiring.py` | 8 | 0 | 0 | 0 |

* `import app.main` → **ok**
* **App Spec entregado** → YAML validado: `PRE_DEPLOY`, `set -e`, y `upgrade head` **antes** de `converge`
* **Migraciones** → `NOT APPLICABLE`
* **Frontend** → `NOT APPLICABLE`

---

## 5. Lo que esto **no** resuelve

**No determina qué borró la integración.** Descarté las migraciones con evidencia, pero la causa concreta sigue sin confirmar. Este cambio la vuelve irrelevante: si el despliegue repone la configuración, deja de importar quién se la llevó. Es una respuesta mejor que averiguarlo.

**No recupera las millas perdidas.** Los 54 viajes siguen necesitando `reprocess_failed_mileage`.

**Y no sustituye al correo.** El paso 1 (MR !64) hace que una pérdida futura genere un aviso; ese aviso sigue sin llegar a nadie mientras el correo saliente no esté configurado en el entorno compartido.

---

## 6. Los tres pasos

| | Paso | Estado | Horas-agente |
|---|---|---|---:|
| C | Avisar cuando se pierde una configuración | hecho — **MR !64** | 3,4 |
| **A** | Declarar la configuración para que el despliegue la reponga | **ESTE DELTA** | 5,9 |
| B | Que el despliegue verifique el motor y falle si no responde | pendiente | ≈ 2,5 |

Con A hecho, B pierde urgencia: ya no hay una configuración que se pierda sin reponerse. Sigue teniendo valor —detecta una clave caducada o un proveedor caído en el momento del despliegue— pero deja de ser la red que sostiene al resto.

---

## 7. Acción operativa, en orden

1. **Fusionar y desplegar el MR !64** (paso C).
2. **Fusionar este MR**, y después **aplicar el App Spec** de `_cer_delivery/APP_SPEC_cerroute-dev.yaml`: pegar la clave de TomTom en `ROUTE_TOMTOM_API_KEY` y dejar los demás secretos intactos.
3. **Configurar el correo saliente** en `/admin/platform/settings`. Sin esto, el paso C no cambia nada en la práctica.
4. **Reponer los 54 viajes**:
   ```bash
   python -m app.db.scripts.reprocess_failed_mileage \
       --company 1 --desde 2026-09-25 --hasta 2026-10-08 --aplicar
   ```

En el primer despliegue tras el paso 2, el log del job dirá qué repuso. Si la integración ya está sana —lo está ahora, `Verified`— dirá `total de cambios: 0`, que es la respuesta correcta.

---

## 8. Asuntos restantes

**Dentro de este alcance: ninguno.**

**Observación declarada:** la clave de TomTom pasará a existir en dos sitios, el App Spec y la base. Es exactamente como ya vive `PLATFORM_MASTER_KEY`, y el spec de DigitalOcean está versionado y respaldado — la base de un entorno de desarrollo, menos. El intercambio es consciente.

---

## 9. Estado propuesto

```text
DEPLOY CONVERGENCE COMPLETE / READY FOR CER REVIEW
```

---

## 10. Estimación del esfuerzo

| Componente | Líneas |
|---|---:|
| `app/db/scripts/converge.py` | 255 |
| `tests/integration/test_converge.py` | 271 |
| `tests/test_converge_registry.py` | 122 |
| `_cer_delivery/APP_SPEC_cerroute-dev.yaml` | 187 |
| `app/config.py` + `docs/MIGRACIONES_EN_APP_PLATFORM.md` | +56 |
| **Total** | **≈ 891** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Localizar dónde nace la integración y por qué nada la repone | `DONE` | — | análisis | 0,5 |
| `converge.py` con registro cerrado | `DONE` | ~255 LoC | backend | 1,6 |
| Tests de integración (9), cinco de ellos negativos | `DONE` | ~271 LoC | integración | 2,2 |
| Lista cerrada (5) + mutación | `DONE` | ~122 LoC | integración | 0,9 |
| App Spec comentado y validado | `DONE` | ~187 líneas | infraestructura | 0,4 |
| Documentación del job | `DONE` | ~56 LoC | documentación | 0,3 |
| Regresión por lotes (103 tests) | `DONE` | 10 lotes | ejecución | 0,5 |
| Reporte | `DONE` | — | documentación | 0,5 |
| **Subtotal** | | | | **6,9** |
| Margen (+10 %, determinista) | | | | **+0,7** |
| **Total del delta** | | | | **≈ 7,6 h-agente** |

Estimé ≈ 4,0 h para este paso y han sido 7,6. La diferencia está casi toda en los tests: los cinco negativos y la mutación del registro no estaban en mi estimación, y son lo que hace que esto no se convierta en un despliegue que revierte decisiones en silencio.

---

## 11. Siguiente paso

Aplicar el App Spec y desplegar. Después queda sólo el paso B, que ya es opcional — dime si lo preparo.
