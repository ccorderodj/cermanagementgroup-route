# CER Route — Perder una configuración ya no es silencioso
## Reporte 001 · Paso 1 de 3

**Origen:** la integración de routing desapareció del entorno compartido y nadie se enteró durante seis días
**Rama:** `fix/alert-on-lost-configuration` (desde `dev`)
**Fecha:** 2026-10-07

---

## 1. Resultado ejecutivo

El sistema **sí detectó** la pérdida de la configuración de TomTom, en la primera ejecución del chequeo tras ocurrir. La repitió **77 veces durante seis días**. Y no avisó a nadie, por decisión del código:

```python
FAILURES = (DEGRADED, AUTH_FAILED, UNREACHABLE)      # not_applicable NO está

if alert and anterior == HEALTHY and estado in FAILURES:
    await notify_platform_admins(...)
```

Cuando el motor pasó de configurado a no configurado, el estado cambió a `not_applicable`, que no estaba en la lista. La alarma no se generó.

El incidente se descubrió porque un supervisor miró una pantalla llena de ceros.

**Corregido.** La regla ya no es una lista de estados, sino la pregunta correcta: *¿estaba sano y ya no lo está?*

Este es el **paso 1 de 3** del plan acordado. Los otros dos —verificar el motor en el propio despliegue, y declarar la integración para que un despliegue la reponga en vez de perderla— son entregas aparte.

---

## 2. Por qué `not_applicable` no estaba en la lista, y por qué eso era defendible

No fue un descuido. `not_applicable` significa **«no está configurado»**, y como estado **inicial** es correcto y no es una alarma: que una instalación nueva no tenga correo configurado todavía no es un incidente, es una decisión pendiente. Avisar de eso haría que cada instalación empezara mandando correos sobre el correo que aún no existe.

Lo que faltaba es la distinción entre **ausencia** y **pérdida**:

```text
(nada)   -> not_applicable     nunca se configuró      no es alarma
healthy  -> not_applicable     se configuró y se perdió   ES alarma
```

La segunda transición es una regresión, igual que `healthy → unreachable`. Sólo que su causa no es que algo falle, sino que algo desapareció.

---

## 3. La corrección

Una función con nombre, en vez de una lista que hay que acordarse de mantener:

```python
def es_regresion(anterior: str | None, estado: str) -> bool:
    """¿Algo que estaba sano dejó de estarlo?"""
    return anterior == HEALTHY and estado != HEALTHY
```

```python
if alert and es_regresion(anterior, estado):
```

**Por qué `!= HEALTHY` y no una lista ampliada.** Porque la lista es exactamente lo que falló. Con esta regla, un estado nuevo que alguien añada mañana queda cubierto sin que nadie tenga que recordar incluirlo. `FAILURES` se conserva —sigue describiendo los estados que son un fallo *por sí mismos*— y ahora lleva un comentario que lo dice.

**El aviso distingue los dos casos**, porque la acción es distinta:

| Transición | Asunto | Cuerpo |
|---|---|---|
| `healthy → not_applicable` | *«… is no longer configured»* | *«was configured and working … Something removed it»* |
| `healthy →` fallo | *«… is failing»* | *«was healthy and the scheduled check now reports {estado}»* |

Uno pide investigar por qué falla. El otro, volver a configurarlo. Mezclarlos mandaría a quien lo lea a buscar en el sitio equivocado.

---

## 4. Validación

**96 tests · 0 fallos · 0 errores · 1 saltado · todos `exit 0`**, por lotes separados.

### Los cuatro tests nuevos

| Test | Qué fija |
|---|---|
| `test_perder_una_configuracion_avisa_a_los_administradores` | `healthy → not_applicable` **sí** avisa, con el asunto correcto |
| `test_no_configurado_desde_el_principio_no_es_una_alarma` | nunca configurado **no** avisa |
| `test_recuperarse_tampoco_es_una_alarma` | volver a `healthy` no avisa |
| `test_la_regla_es_estaba_sano_y_ya_no` | la regla, sin base de datos ni correo, incluido un estado futuro inventado |

Los tres primeros conducen el camino real: sustituyen el chequeo `_road_routing`, ejecutan dos veces el ciclo programado y miran el buzón.

El segundo y el tercero son **controles negativos**, y son los que hacen válido al primero: sin ellos, un sistema que avisara siempre pasaría la comprobación de arriba y habríamos cambiado seis días de silencio por ruido constante.

### Detección probada por mutación

Devolví la condición a la forma anterior:

```text
1 failed, 16 passed
  test_perder_una_configuracion_avisa_a_los_administradores
```

Falla exactamente el que debe, y sólo ése. Revertido, 17/17 verde.

### Lotes

| Lote | Tests | Fallos | Err | Skip | Exit | Seg |
|---|---:|---:|---:|---:|---:|---:|
| `test_platform_diagnostics.py` (+4 nuevos) | 17 | 0 | 0 | 0 | 0 | 24 |
| `test_platform_config_store.py` | 12 | 0 | 0 | 0 | 0 | 20 |
| `test_platform_key_rotation.py` | 2 | 0 | 0 | 0 | 0 | 14 |
| `test_platform_adapters.py` | 12 | 0 | 0 | 0 | 0 | 8 |
| `test_road_routing_wiring.py` | 8 | 0 | 0 | 0 | 0 | 5 |
| `test_route_mileage_engine.py` | 24 | 0 | 0 | 1 | 0 | 84 |
| `test_permission_catalog.py` | 7 | 0 | 0 | 0 | 0 | 6 |
| `test_public_surface.py` | 14 | 0 | 0 | 0 | 0 | 10 |

* `import app.main` → **ok**
* **Migraciones** → `NOT APPLICABLE`
* **Frontend** → `NOT APPLICABLE`: ningún archivo de interfaz cambió

---

## 5. Lo que esto **no** resuelve

Hay que decirlo, porque sin lo siguiente este cambio sirve de poco:

**El correo saliente no está configurado en el entorno compartido.** Medido en los datos restaurados:

```text
email            not_applicable   "Email is not configured in Settings."
email_fallback   not_applicable   "No fallback email provider is configured in Settings."
```

`notify_platform_admins` manda correo y captura el fallo de envío como un aviso en el registro. **Sin correo, la alarma sigue disparando al vacío.** Este delta hace que la alarma exista; configurar el correo es lo que hace que llegue.

Es configuración, no código, y es la acción de mayor valor por minuto invertido de toda esta investigación: hace visible **cualquier** degradación futura, no sólo ésta.

**Y no evita la pérdida.** Avisa cuando ocurre. Que un despliegue no pueda llevarse la configuración por delante es el paso 3.

---

## 6. Los tres pasos, y dónde estamos

| | Paso | Estado | Horas-agente |
|---|---|---|---:|
| **C** | Avisar cuando se pierde una configuración | **ESTE DELTA** | ≈ 3,1 |
| B | Que el despliegue verifique el motor y falle si no responde | pendiente | ≈ 2,5 |
| A | Declarar la integración para que el despliegue la reponga | pendiente | ≈ 4,0 |

Más una acción operativa que no es de desarrollo: **configurar el correo saliente**.

---

## 7. Asuntos restantes

**Dentro de este alcance: ninguno.**

**Acción operativa, por orden de valor:**

1. **Configurar el correo saliente** en `/admin/platform/settings`. Sin esto, este delta no cambia nada en la práctica.
2. **Reponer los 54 viajes** ahora que TomTom está `Verified`:
   ```bash
   python -m app.db.scripts.reprocess_failed_mileage \
       --company 1 --desde 2026-09-25 --hasta 2026-10-08 --aplicar
   ```
3. Desplegar este cambio. Sólo backend, sin migración.

**Observación, no bloqueante:** no pude determinar qué borró la integración. Descarté las migraciones con evidencia —ninguna toca `platform_integration` ni `platform_secret`, sólo las crea la línea base—, pero la causa concreta queda sin confirmar. El paso A la vuelve irrelevante: si el despliegue repone la configuración, deja de importar quién se la llevó.

---

## 8. Estado propuesto

```text
LOST CONFIGURATION ALERT COMPLETE / READY FOR CER REVIEW
```

---

## 9. Estimación del esfuerzo

| Componente | Líneas |
|---|---:|
| `app/core/platform/diagnostics.py` | +45 / −8 |
| `tests/integration/test_platform_diagnostics.py` | +93 |
| **Total** | **≈ 138 / −8** |

| Tarea | Estado | Volumen | Complejidad | Horas-agente |
|---|---|---|---|---|
| Localizar por qué no sonó la alarma | `DONE` | — | diagnóstico | 0,4 |
| `es_regresion` y el aviso diferenciado | `DONE` | ~45 LoC | backend | 0,6 |
| 4 tests, con dos controles negativos | `DONE` | ~93 LoC | integración | 1,2 |
| Mutación | `DONE` | — | verificación | 0,2 |
| Regresión por lotes (96 tests) | `DONE` | 8 lotes | ejecución | 0,4 |
| Reporte | `DONE` | — | documentación | 0,3 |
| **Subtotal** | | | | **3,1** |
| Margen (+10 %, determinista) | | | | **+0,3** |
| **Total del delta** | | | | **≈ 3,4 h-agente** |

---

## 10. Siguiente paso

Configurar el correo saliente, y decidir si sigo con el **paso B** —que el despliegue verifique el motor y falle si no responde— o directamente con el **paso A**, que es el que impide la pérdida.

Mi recomendación: **A antes que B**. B avisa antes; A hace que no haya nada de qué avisar.
