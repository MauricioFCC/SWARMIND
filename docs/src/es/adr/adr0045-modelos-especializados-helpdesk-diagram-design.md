# ADR-0045: Modelos Especializados (analogía Helpdesk) + Skill Diagram-Design

> **Estado:** Aprobado (2026-08-13)
> **Fecha:** 2026-08-13

## Contexto

Se evaluó la analogía de un **equipo de Soporte Técnico de TI** como modelo
mental para la especialización de modelos en SWARMIND:

| Rol helpdesk | Tipo de modelo | Descripción |
|---|---|---|
| 🎧 **Helpdesk N1** | LLM | Atiende dudas generales, conversa y redacta respuestas |
| 🛠️ **Administrador de Sistemas** | LAM | No solo habla: ejecuta acciones, presiona botones, automatiza flujos |
| 🏢 **Mesa de Soporte Especializada** | MoE | Un router asigna el ticket al experto (BBDD, redes, seguridad) |
| 👁️ **Técnico en Sitio** | VLM | Entiende imágenes: diagnostica leyendo capturas de pantalla o diagramas |
| ⚡ **Laptop/Toolbox de Diagnóstico** | SLM | Modelos pequeños ultrarrápidos que corren localmente sin depender de la nube |

**Principio clave:** el secreto en ingeniería de IA no es usar el modelo más
grande para todo, sino **enviar el ticket al especialista correcto**.

### Auditoría contra el código real (2026-08-13)

| Concepto | ¿Implementado en SWARMIND? | Evidencia |
|---|---|---|
| LLM (Helpdesk N1) | ✅ Sí | `harness/model_router/multi_provider/` — múltiples proveedores LLM (GPT, Claude, etc.) |
| LAM (SysAdmin ejecuta) | ✅ Sí | `tools_sandbox/mcp_executor.py`, `mcp_manager.py`, `speculative_tool_exec.py`, `sandbox_loop.py`, `qa/agent.py` (autónomo con MCP) |
| MoE (router→especialistas) | ✅ Parcial | `complexity_router/` (señales heurísticas: largo, keywords, dominios) + `difficulty_router` + `route_with_fallback` (confianza <0.7 → frontier) |
| VLM (visión) | ❌ **GAP** | 0 referencias a `image_url`/`vision`/`screenshot`/`multimodal` en el código |
| SLM (local sin nube) | ⚠️ Parcial | Enruta a modelos "small" remotos; no ejecuta SLM on-device (sin ollama/llama.cpp) |

## Decisión

1. **NO implementar código nuevo** con la analogía (violaría IDP: LLM/LAM/MoE
   ya existen). Documentar el mapeo como gap analysis.
2. **Registrar los 2 GAPs** (VLM, SLM local) como candidatos de roadmap futuro:
   - **VLM (ADR-0046 propuesto)**: análisis de capturas de pantalla, PDFs,
     diagramas de error, diagnostico visual.
   - **SLM local (ADR-0047 propuesto)**: backend fallback offline con
     llama.cpp/ollama para tareas de baja complejidad sin nube.
3. **Adoptar el skill `diagram-design`** (upstream `cathrynlavery/diagram-design`
   v2.3, 14.3k stars) como `.opencode/skills/diagram-design/` para cubrir la
   generación de diagramas editoriales autocontenidos HTML+SVG.

### Skill diagram-design — detalle

- **27 tipos visuales**: architecture, IT current-state, flowchart, sequence,
  state machine, ER/data model, timeline, swimlane, quadrant, radar/spider,
  loop/flywheel, nested, tree, org chart, layer stack, Venn, pyramid/funnel,
  bar, line, Gantt, scatter, high-level, process, medallion, data flow,
  DP integration, DP security matrix.
- **146 archivos** (~2 MB): SKILL.md (568 líneas) + `references/` (39)
  + `scripts/` (self_check, drawio_extract, mermaid_extract) + `assets/`
  (100+ ejemplos HTML).
- **Capacidades**: redibujar .drawio/.mmd, onboarding de brand tokens desde
  URL/skill/carpeta, export SVG/PNG, patrones semánticos, motion accesible,
  estilo sketchy.
- **Licencia MIT** compatible con SWARMIND.

## Consecuencias

### Positivas
- Cobertura de diagramas editoriales de alta calidad sin reinventar (IDP).
- El gap analysis documenta deuda técnica futura (VLM/SLM) para el roadmap.
- 30 → 31 skills registrados (`skills_registry.yaml`).

### Negativas
- El skill no cubre visión en runtime: los diagramas los genera el agente, no
  los *lee* el sistema (el GAP VLM sigue abierto).
- ~2 MB de assets en el repo (aceptable: autocontenido, sin dependencias).

## Alternativas consideradas

1. **Mermaid/DrawIO nativos** — RECHAZADO: output menos editorial, requiere
   tooling externo.
2. **Reimplementar diagramas propios** — RECHAZADO: reinvención, viola IDP.
3. **Adoptar diagram-design como skill** — ACEPTADO: autocontenido, MIT,
   comunidad activa (14.3k stars).

## Commit

- `SKILL` — `.opencode/skills/diagram-design/` (146 archivos) + registro en
  `skills_registry.yaml`.
