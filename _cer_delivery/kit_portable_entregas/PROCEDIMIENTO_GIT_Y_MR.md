# Git y merge request

## 1. Rama
```bash
git checkout {{RAMA_BASE}} && git pull --ff-only origin {{RAMA_BASE}}
git checkout -b <tipo>/<tema-corto>
```

| Tipo | Cuándo |
|---|---|
| `feature/` | Funcionalidad nueva |
| `fix/` | Corrección de un defecto |
| `docs/` | Solo documentación o informes (diagnósticos, reportes) |
| `chore/` | Mantenimiento sin cambio funcional |

Comprobar `git branch --show-current` **antes de escribir código**.

## 2. Commit
- Asunto corto, en el idioma del proyecto, que diga **qué cambia**. El cuerpo
  dice **por qué** y qué queda fuera.
- Antes de commitear, revisar que no se cuelen finales de línea CRLF si el
  proyecto usa LF: `git diff --cached --stat` y el lint del proyecto.
- Si el asistente participa, terminar con su línea de coautoría, por ejemplo:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

- **Nunca** reescribir historia ya publicada (amend, rebase, force push) sin
  autorización expresa.
- **No saltar** los hooks (`--no-verify`).

## 3. Push y MR

### GitLab sin `glab` (opciones de push)
Dos trampas, aprendidas en CER Route:

1. **Las opciones solo valen en el PRIMER push de la rama.** Si la rama ya está
   en el remoto, `-o merge_request.create` se ignora en silencio
   («Everything up-to-date»).
2. **No admiten saltos de línea.** La descripción va en una sola línea; el
   detalle, en el reporte.

```bash
git push -u origin <rama> \
  -o merge_request.create \
  -o merge_request.target={{RAMA_BASE}} \
  -o "merge_request.title=<titulo>" \
  -o "merge_request.description=<una linea: que cambia, validacion, ruta del reporte>"
```

La URL del MR aparece en la salida (`remote: https://…/merge_requests/NN`).
Hay que copiarla en el cierre de la iteración.

### GitHub (con `gh`)
```bash
git push -u origin <rama>
gh pr create --base {{RAMA_BASE}} --title "<titulo>" --body-file <reporte.md>
```

## 4. Lo que no se hace
- **Fusionar.** El MR espera revisión y certificación.
- **Borrar ramas del remoto** sin que se pida. Borrar las locales ya fusionadas
  sí, con `git branch -d` (que se niega si no están fusionadas).
- **Commitear `.env`**, secretos o volcados de datos personales.

## 5. Siguientes pushes a la misma rama
Un commit nuevo en la misma rama actualiza el MR abierto; basta con `git push`.
