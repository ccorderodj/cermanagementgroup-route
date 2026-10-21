# Plantilla: resumen para {{DESTINATARIO}}

**Cuándo:** «hazme el resumen para {{DESTINATARIO}}». Va en el chat (y se ofrece
publicarlo como página); no es el reporte técnico.

**Reglas:**
- **Estructura fija.** {{DESTINATARIO}} compara entregas entre sí; si cambia la
  forma, se nota y se reclama.
- **Lenguaje de negocio.** Nada de nombres de archivo, endpoints ni tablas
  salvo que hagan falta para una acción.
- **Copiar la tabla «Estado del proyecto» del resumen anterior** y
  actualizarla: la parte actual primero y en negrita, las demás líneas vivas
  debajo.
- **Cifras reales:** «12 de 12», «Sin fallos nuevos. Solo el de siempre».
  «Todavía no» cuando no se comprobó.

---

```markdown
Written for: {{DESTINATARIO}}, que decide el proyecto y lo lee en clave de negocio.

---

# {{PROYECTO}}: <qué cambia, en lenguaje llano>
**<fecha larga>** · <código o etapa> · MR !NN

## En una frase
<Qué se consiguió y qué falta, en una o dos frases.>

## Qué pasaba
<Solo si hubo un problema: qué veía el usuario o el negocio.>

## Qué cambia
- **<Cambio>.** <Consecuencia para el negocio.>
- **<Lo que NO cambia>**, si alguien podría preocuparse.

## Cómo se comprobó

| Comprobación | Resultado |
|---|---|
| <Lo comprobado, en lenguaje de negocio> | N de N |
| Toda la batería | N de N. Sin fallos nuevos. Solo <los de siempre> |
| En el entorno real | **Todavía no**: <por qué> |

## N cosas que conviene saber
1. **<Riesgo, límite o decisión implícita>.** <Una o dos frases.>
2. **<...>.** <...>

## Lo que necesito de ti

| Decisión | Mi recomendación |
|---|---|
| Certificar esta entrega | Fusionar el MR !NN |
| <Decisión de negocio> | <Recomendación concreta> |

## Estado del proyecto

| Parte | Estado | Quién tiene la pelota |
|---|---|---|
| **<Esta entrega>** | **<Hecho (MR !NN), sin desplegar>** | **<Tú: certificación>** |
| <Parte viva 2> | <Integrado / Pendiente / Bloqueado> | <Quién> |
| <...> | | |

## Pendientes operativos
<Párrafo o lista corta: lo que tiene que hacer alguien fuera del código, en orden.>

**Siguen abiertos:** <temas antiguos sin cerrar>.

**Esfuerzo:** unas N horas-agente en esta entrega. <Lo que queda, si aplica.>

---

Si lo quieres como página con enlace para compartir, dímelo y lo publico.
```
