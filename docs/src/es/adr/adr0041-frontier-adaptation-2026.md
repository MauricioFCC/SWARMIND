# ADR-0041: Frontier Adaptation 2026 — MCP Stateless, OTel GenAI, DeltaChannel, Agent Factory y Skills 2026

## Estado
**Fase 1 IMPLEMENTADO + Fase 2 IMPLEMENTADO (2026-08-08)** — Tras dos rondas de
investigación web exhaustiva (agosto 2026): (a) sistemas agénticos y opencode v1.18.x
(anomalyco/opencode, 195k stars); (b) skills de programación frontier, análisis de
textos científicos y legales, y construcción de agentes on-demand (arXiv 2604.27882,
SWE-bench Pro, agentskills.io, LegalGraphRAC ACL 2026, OpenScholar, Terminus).
Mesa de trabajo con verificación IDP sobre el harness en ambas fases: se descartaron
las recomendaciones ya implementadas o de bajo ROI; se adoptan 6 deltas con impacto
verificable y ciclo TDD corto.

> **ADR interno**: no se pushea a remoto; vive solo en el repo local (regla del proyecto).

## Contexto
La investigación frontier 2026 identificó 10 recomendaciones accionables para
SWARMIND. El análisis IDP (no reimplementar lo existente) sobre el código actual:

| # | Recomendación | Veredicto IDP |
|---|---------------|---------------|
| 1 | Hook `experimental.session.compacting` | ✅ YA: `plugin/compaction-context.js` (ADR-0039 #3) |
| 2 | MCP stateless 2026-07-28 | 🔴 **DELTA**: `mcp_client.py:132` usa handshake `initialize` stateful; sin `server/discover` ni catálogos cacheables |
| 3 | Agent Skills estándar (agentskills.io) | ✅ YA: skills con `SKILL.md` + frontmatter + permisos por patrón |
| 4 | Token economics en capas (routing/caching) | ✅ YA: token_budgets.yaml + ShapedCache + small_model diferido documentado (ADR-0039) |
| 5 | OTel GenAI semantic conventions | 🔴 **DELTA**: `opentelemetry_agent.py:135-138` usa atributos propios `agent.*`; el estándar estable 2026 es `gen_ai.*` |
| 6 | Agentic TDD como contrato | ✅ YA: ADR-0033 + `test_tdd_strict.py` + abstention_policy |
| 7 | Durable execution DeltaChannel | 🔴 **DELTA**: WAL existe (`write_ahead_log.py`) pero guarda entradas completas; sin snapshot delta cada K ni resume flat |
| 8 | Guardrails en capas | ✅ YA: `memory_guard.py` + tool_guardian + security_guard |
| 9 | Shepherd orchestrator-guided scaling | ⏸ Diferido: requiere refactor de coordinación; P2 |
| 10 | MetaClaw/Letta evolución continua | ✅ YA: `metaclaw.py` + evolve loop; Letta-style diferido |

**Fuentes de la investigación** (agosto 2026):
- MCP spec stateless 2026-07-28: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- OTel GenAI semconv estable: https://opentelemetry.io/blog/2026/genai-observability/
- DeltaChannel (LangChain): https://www.langchain.com/blog/delta-channels-evolving-agent-runtime
- opencode v1.18.x: https://github.com/anomalyco/opencode/releases

## Decisión e Implementación (TDD — test primero, código después)

### FASE 1 — Sistemas agénticos y opencode (TOP-10, 8 P1 + 2 P2)

### H1. Cliente MCP stateless (spec 2026-07-28) — `harness/tools_sandbox/mcp_client.py`
Migrar del handshake `initialize` obligatorio a protocolo stateless:
- Cada request es self-describing (versión + capabilities en `_meta`); sin `initialize`/`Mcp-Session-Id` obligatorios.
- Nuevo RPC `server/discover` para descubrimiento de capacidades.
- List responses cacheables: respetar `ttlMs`/`cacheScope` del server en `list_tools`.
- Headers `Mcp-Method`/`Mcp-Name` en requests.
- **Compatibilidad**: si el server rechaza el modo stateless, fallback a `initialize` (server legacy).
- Mantener la API pública actual (`connect`, `list_tools`, `call_tool`) → 0 impacto en consumidores.

### H2. OTel semantic conventions GenAI estables — `harness/observability/opentelemetry_agent.py`
Migrar atributos propios `agent.*` a semconv GenAI 2026:
- Spans: `invoke_agent` / `chat` / `execute_tool` (nombres estándar).
- Atributos: `gen_ai.provider.name` (nuevo) + legacy `gen_ai.system`; `gen_ai.request.model`;
  `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`; `gen_ai.response.finish_reasons`.
- Mantener `agent.*` como atributos custom adyacentes (no romper dashboards existentes).
- `trace_agent` emite span `invoke_agent` con `gen_ai.provider.name=swarmind`.

### H3. DeltaChannel — durable execution con checkpoints delta — `harness/orchestrator/delta_channel.py` (nuevo)
Checkpointing por pasos inspirado en LangChain DeltaChannel:
- WAL por paso: cada mutación registra solo el **delta** (cambio incremental).
- Snapshot completo cada **K pasos** (K=50 default, constante nombrada).
- `resume()` reconstruye estado: snapshot base + replay de deltas (resume flat).
- Reducción de storage ~40x frente a full-snapshot por paso (O(N²) → O(N)).
- Integración opcional con `TaskOrchestrator`/WAL existente (sin romper API actual).

### FASE 2 — Skills frontier, agentes on-demand y configuración del usuario (TOP-10 v2)

> Segunda investigación (2026-08-08): programación (SWE-bench Pro failure modes,
> verification-first), ciencia (OpenScholar, CiteGuard, ARA reproducibility), legal
> (LegalGraphRAG, sanción Corte Suprema Colombia feb-2026 por citas apócrifas IA,
> criterios T-323-24), y construcción de agentes por el usuario (arXiv 2604.27882,
> agent_factory 5-layer prompt, catálogos multi-agent).

### H4. Agent Factory on-demand + recommendation engine — `harness/aifactory/agent_factory.py` + `agent_templates.yaml` (nuevos)
Pipeline arXiv 2604.27882 adaptado: QueryAnalysis → PersonaCraft → AgentFactory →
render de definición de agente opencode nativa (Markdown + frontmatter YAML).
- `AgentTemplateRegistry`: carga catálogo YAML de 8 plantillas base (programming-agent,
  science-review, legal-review, data-analysis, security-audit, documentation,
  frontend-ui, research-synthesis) con `domain_tags`, `required_tools`, `composable`,
  `max_iterations`, `cost_estimate`, `role_mandate`, `reasoning_style`,
  `output_contract`, `guardrails`.
- `AgentRecommender`: recommendation engine — tokeniza la tarea del usuario, hace
  scoring contra `domain_tags`+keywords del template, devuelve el mejor match
  (fallback documentado si no hay coincidencias).
- `OnDemandAgentFactory.generate(task, ...)`: compone la persona (5-layer prompt:
  Identity+Mandate → Tools → Reasoning → Output Contract → Guardrails), crea
  `SpawnConfig` (template_id, model, budget, max_iterations, tool_overrides,
  parent_agent_id para genealogía) y renderiza el Markdown nativo de opencode
  (frontmatter: name, description, mode: subagent, steps, permissions).
- El USUARIO describe su tarea en lenguaje natural → el sistema recomienda plantilla,
  construye el agente específico on-demand, y puede revisar/editar la definición
  antes de ejecutarla (build-time vs runtime).
- Dataclasses frozen, inmutabilidad, errores WHAT+WHY+WHERE, docstrings ES-UTF8.

### H5. Validador de skills al estándar agentskills.io — `harness/memory_rag/skill_frontmatter.py` (nuevo)
Valida que los SKILL.md cumplan el estándar interoperable 2026 (progressive
disclosure L1): `name` (1-64, lowercase-hyphen, == dirname), `description` (1-1024,
qué+hace+cuándo, verbos accionables), `license`, `compatibility`, `metadata`
(author/version), `allowed-tools`.
- `SkillFrontmatterValidator`: `validate_file`, `validate_directory`, `validate_all`.
- `SkillReport` (frozen): valid/errors/warnings + `summary()` legible.
- Resultado real: 32/32 skills válidos (0 errores, warnings de campos opcionales).
- Base para pipeline pre-commit de validación de skills y versionado SVE.

### H6. Skills de dominio actualizados con patrones frontier 2026 (edición de texto)
- **`reviewer.md`** — sección "Revisión Adversarial (frontier 2026)": evaluación del
  diff contra el PLAN (no contra el razonamiento del implementador), contexto fresco,
  check ejecutable (verification-first), tabla de anti-patterns SWE-bench Pro
  (context overflow, endless file reading, stuck-in-loop, tool error, wrong solution).
- **`science-doc/SKILL.md`** — sección "Verificación de Citas y Reproducibilidad":
  CiteGuard-style (retrieval-augmented validation, marca `CITA-NO-VERIFICADA`),
  OpenScholar-style self-feedback, reproducibilidad ARA-style (veredicto
  REPRODUCIBLE/PARCIAL/NO), detección de contradicciones estilo PaperQA2.
- **`legal-doc/SKILL.md`** — sección "Verificación de Vigencia y Citas Legales":
  precedente sanción Corte Suprema Colombia (feb-2026, citas apócrifas IA),
  criterios T-323-24, patrón LegalGraphRAG (Researcher→Auditor→Adjudicator),
  verificación de vigencia (VIGENTE/MODIFICADO/DEROGADO/INEXEQUIBLE) contra SUIN/
  relatorías/Kelsen MCP, marca `APÓCRIFA-REVISAR`, diagnostic checklists por norma.

### No-acciones (documentadas, evitando YAGNI)
- Shepherd scaling (P2), A2A 1.0 (P3), routing Terminus (P3) y marketplace externo
  (P3) se difieren; no hay consumo que los justifique hoy.
- Sandboxing Codex-style se difiere: el harness corre local con permisos de opencode.

## Consecuencias
- **Positivas**: cliente MCP futuro-proof (spec 2026-07-28); trazabilidad estándar
  interoperable (Langfuse/Grafana Tempo/Aspire); tareas long-running resilientes sin
  O(N²) de storage; el usuario puede construir agentes muy específicos on-demand en
  lenguaje natural (con revisión humana); skills interoperables con el estándar
  agentskills.io (Claude Code/Codex/opencode); análisis científico y legal con
  verificación de citas/vigencia (mitiga sanción por citas apócrifas IA);
  suite TDD crece ~100 tests.
- **Negativas**: fallback legacy añade rama de compat en MCP; semconv GenAI añade
  atributos sin eliminar los legacy (leve redundancia); el validador de skills
  reporta warnings en los 32 skills (campos opcionales del estándar no presentes).
- **Riesgos**: servidores MCP antiguos pueden rechazar requests sin `initialize` →
  mitigado con fallback; DeltaChannel requiere batching-invariance en reducers →
  documentado en el módulo; el recommender de agentes es keyword-based (mejorable a
  embedding-based en iteración futura).

## Verificación (DoD)
- [x] Tests TDD para H1/H2/H3/H4/H5 (red → green → refactor) con docstrings ES-UTF8.
- [x] H6: secciones añadidas en reviewer.md, science-doc/SKILL.md, legal-doc/SKILL.md.
- [x] Suite completa pasa (4068+ tests); ruff limpio; sin `except: pass` silencioso.
- [x] Validador agentskills.io: 32/32 skills válidos (0 errores).
- [x] Agent Factory demo: tarea legal → recomienda legal-review → genera Markdown opencode.
- [x] API pública sin breaking changes.
- [x] ADR interno marcado IMPLEMENTADO (sin push).
