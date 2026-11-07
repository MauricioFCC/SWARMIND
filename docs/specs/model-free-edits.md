# Spec — Edits frugales con beam-free (opencode-go) + SSOT seteable

> Estado: **implemented** — Dueño: `.opencode/agents/beam-patcher.md`,
> `.opencode/commands/patch-free.md`, `.opencode/config/model_runtime.yaml`
> y `harness/model_router/edit_runtime.py` — Frontera: 2026-10-31.
> Fuentes verificadas (OpenCode v2): [Agents](https://opencode.ai/v2/docs/agents),
> [Commands](https://opencode.ai/v2/docs/commands),
> [Models (free + variantes)](https://opencode.ai/v2/docs/models) y
> [Models tooling (catalogo vivo)](https://opencode.ai/llms.txt).
> Catalogo: `opencode-go/beam-free` (activo, gratuito, lanzado 2026-10-05).

## 1. Problema

Los modelos v4.1 flash estan dimensionados para tareas exigentes; los **edits
menos exigentes** (renombres, tweaks triviales, cadenas de texto, tocar a uno
varios archivos) gastan budget de tokens del modelo default mientras el
catalogo trae un modelo **gratuito y activo** (`opencode-go/beam-free`) que
puede cubrirlos.

## 2. Decisiones

| # | Decision | Fundemento |
|---|---|---|
| N1 | Subagente `beam-patcher` (`mode: subagent`) fijado al modelo frugal | subagente = fresh context + permisiones propias (spec Agents) |
| N2 | Comando `/patch-free` rapido | entry point de una sola tecla en el TUI; compone instrucciones |
| N3 | Modelo frugal mas un **id estable** (`beam-free`), NO ref = uid de mono-proveedor | providers puede cambiar; beam-free esta registrado activo hoy |
| N4 | Solo un SSOT: `.opencode/config/model_runtime.yaml` | unica fuente para `edits_model`; la mirror en agente `.md` documenta el default (N6) |
| N5 | Env override `SWARMIND_EDITS_MODEL` tiene la mayor precedencia | convencion SSOT de env-portabilidad del harness (NAM/EDV) |
| N6 | Los `.md` fijan el default y los changes del yaml no lo mueven | drift signal: si cambias yaml debes cambiar el md (rita check `test_mirror_default`) |
| N7 | `#beam-free` SOLO para edits micro; la instancia actual es frugal | el modelo default es deepseek-v4.1-flash y debe seguir en control del routing de razonamiento |
| N8 | module `edit_runtime.py` **puro** (`Path` + `os.environ`, sin red/E/S) | domain puro, mis test hermeticos |

## 3. Cable

```
                 ┌─────────────────────────────────────────────┐
                 │  ENV: SWARMIND_EDITS_MODEL  (top precedence)│
                 │  .opencode/config/model_runtime.yaml (SSOT) │
                 │  DEFAULT "opencode-go/beam-free" (NAM)      │
                 └─────────────────────────────────────────────┘
                        │                          │
                        v                          v
        harness/model_router/edit_runtime.py   .opencode/agents/beam-patcher.md
        (resolve_edits_model/tier)             .opencode/commands/patch-free.md
                                               (consume el modelo del agente)
```

## 4. Criterios de aceptación

| Crit | Requisito | Evidencia |
|---|---|---|
| AC-1 | precedence env > yaml > constant con id bien formado o `None`. | `test_model_runtime.py` (8 casos) |
| AC-2 | YAML SSOT con default `beam-free`. | `resolve_reviewed` + shapes test |
| AC-3 | `beam-patcher.md` legal (frontmatter parsea, model fija beam-free, permisos con `edit: allow` + web/subagent/shell deny). | test de live test parse |
| AC-4 | `/patch-free` cmd disponible y ligado al agente. | mismo test |
| AC-5 | Mirror default yaml ≈ agente .md (sign bidder drift). | test de estructura |
| AC-6 | `edit_runtime` es pure (0 red, 0 build side-effects). | hermetic import test |
| AC-7 | Suite total y tooling verde (ruff, vulture, gates). | records de CI |

## 5. Como setear (settle) interno

```bash
# el top (ENV SSOT):
setx SWARMIND_EDITS_MODEL "opencode-go/beam-free"

# o el SSOT del filesystem (mismo dual en repo editado):
#   .opencode/config/model_runtime.yaml -> edits_model: "opencode-go/beam-free"
```

Para cambiar el default global (N6): cambia el yaml `.opencode/config/edit_runtime.yaml`
y actualiza el `model:` del frontmatter en `.opencode/agents/beam-patcher.md`
para mantener el mirror test verde (`test_ssot_default_matches_agent_frontmatter`).

## 6. References

- agents mode+model frontmatter y permisos (doc Uh Digital, Verified 2026-10-31)
- comando `model` (Command frontmatter: supported)
- variants: `open-and-run` usa `#type-deep`; beam-free sin variantes en el catalogo.
