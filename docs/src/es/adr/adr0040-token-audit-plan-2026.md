# ADR-0040: Auditoría Token-Economics — Plan de Acción H1-H8

## Estado
**IMPLEMENTADO (H1, H3, H4, H5, H6, H7, H8 — 2026-08-04). H2 PENDIENTE (baja prioridad)** —
Auditoría ejecutada el 2026-08-04 por token-budget-auditor (verificación directa de
archivos y ejecución de chequeos). Extiende ADR-0039 (recomendaciones frontier) y
ADR-0013/ADR-0031. Verificación: 176+ tests pasando (suite de sincronía, agentes,
token budgets, orquestador, reglas universales).

## Contexto
La arquitectura de economía de SWARMIND es sólida en diseño (minificación 2-tier
full/min, budgets por rol, cache-shape, compression_levels) pero la auditoría
detectó **3 fugas principales que impiden materializar ~60% del ahorro declarado**:

1. **Mins corruptos o ineficientes** → fallback a tier full (costo 4×).
2. **token_budgets.yaml desconectado del runtime** → SSOT decorativo (el runtime usa
   constantes hardcodeadas DEFAULT_AGENT_BUDGET=4000 / DEFAULT_SESSION_BUDGET=16000
   en `harness/memory_rag/token_budget.py:59-60` para TODOS los agentes).
3. **Routing desalineado** → casi todo cae al catch-all `universal` con 10 agentes
   (routing_rules.yaml:60-63) porque los dominios de routing_rules.yaml no coinciden
   con los de skills_registry.yaml.

## Decisión e Implementación (plan priorizado)

### P0 — Alta prioridad (fugas de tokens)

#### H1. Reparar 10 SKILL.min.md con frontmatter YAML roto — ~20,000 tokens/sesión multi-skill
Verificado con `yaml.safe_load`:
- **YAML-ERROR** (indentación rota): `hedgefund`, `quant-trading`, `alpha-research`,
  `evolve`, `risk-execution` (línea 3: `description:` indentada bajo `name:`).
- **SIN frontmatter**: `healthtech`, `legal-doc`, `math-doc`, `pos-retail`,
  `science-doc`.
El runtime prefiere `.min.md` (`agent_dispatcher.py:218`, `skill_loader.py:165-167`);
frontmatter roto degrada a tier full (hedgefund 19,049B + legal-doc 11,341B + ... =
~80KB ≈ 20,000 tokens).
**Acción**: regenerar con `harness/scripts/compile_skills.py` + añadir test que valide
YAML de los `.min.md` (hoy `test_opencode_config_sync.py:423-425` los excluye).

#### H2. Recompactar 7 skills con minificación ineficiente (ratio 58-89% del full) — ~8,300 tokens
`hedgefund 88%`, `pos-retail 89%`, `healthtech 86%`, `quant-trading 75%`,
`risk-execution 65%`, `alpha-research 60%`, `evolve 58%` = 44.5KB ≈ 11,130 tokens
(72% del presupuesto min de skills). Llevarlos al ratio promedio (4-25%) = ~33KB menos.
**Acción**: reescribir mins con Structured Compaction (secciones + JSON compacto) o
ajustar `compile_skills.py` para omitir tablas de métricas de bajo valor. Riesgo:
sobre-compactar skills densos (hedgefund doctrina, quant-trading API) donde las
tablas son señal.

#### H3. Alinear routing_rules.yaml ↔ skills_registry.yaml — ~2,500 tokens/dispatch
routing_rules.yaml define 15 dominios (quantitative-analysis, risk-management,
trading, ai-ml, memory, ...) que NO matchean los dominios del registry
(quantitative, financial, legal, academic, retail, meta, risk, systems, ...).
Casi ningún skill matchea una ruta → catch-all `universal` (10 agentes).
**Acción**: mapear dominio del registry → ruta de routing (o rutas por skill);
mantener en `universal` solo coordinator + token-budget-auditor. Scoped Context
Spawn (-44% tiempo, -38% tokens) por dispatch con contexto acotado a 2-3 agentes.

### P1 — Prioridad media

#### H4. Deduplicar release-ops.md vs swarm-release-ops/SKILL.md — -85% del agente (~590 tokens/uso)
`agents/release-ops.md:29-53` ≈ `skills/swarm-release-ops/SKILL.md:20-85` (mismo
contenido verificado 1:1). El agente debe quedar en ~400B (rol/permission/reglas
fijas) + referencia al skill (Scoped Context). Elimina drift entre copias.

#### H5. Consolidar la triada evolve-analyzer/engineer/researcher — ~8KB ≈ 2,000 tokens/loop
Los 3 agentes (2.2-2.6KB c/u, mins al 71-77% sin compactación efectiva) repiten el
loop Learn→Design→Experiment→Analyze que ya vive en `skills/evolve/SKILL.min.md:19`
(ROLE STACKING) y `evolve.agent.min.md:22` (SUB-AGENTES). Sus descripciones son las
más largas del sistema (233-266 chars vs límite 45 tokens del test).
**Acción**: convertir la triada en "modos de rol" del agente evolve; actualizar
`project_config.yaml:107-108` y `test_agent_files.py:24`. Riesgo medio: el harness
referencia la triada en agent_list.

#### H6. Conectar token_budgets.yaml al runtime — -49% en roles ligeros
El YAML declara ser SSOT (token_budgets.yaml:3) pero solo lo lee
`test_opencode_config_sync.py` (validación de nombres). El runtime usa 4000 flat.
**Acción**: que `TokenBudgetManager` (token_budget_manager.py) cargue el YAML y
aplique role_budgets (guardian/token-budget-auditor 2048 vs 4000 flat), junto con
compression_levels y compression_threshold: 0.85. Riesgo: estrangulamiento; calibrar
con monitoring.metrics (cache_hit_rate, failure_spend_ratio).

#### H7. base_principles.md Nivel 3 bajo demanda — -6,169 tokens/agente
`core/base_principles.md` = 39,240 chars ≈ 9,810 tokens; N1+N2 (líneas 17-89) ≈
3,641 tok; N3 (líneas 91-537, "referencia detallada") ≈ 6,169 tok. Con
`include_principles: always` en 5 roles, N3 inyectado hace que coordinator (4096)
exceda su budget (3,641+636 = 4,277).
**Acción**: N1+N2 siempre; N3 a `base_principles_full.md` bajo demanda (Progressive
Disclosure). Riesgo bajo: scientist/evolve lo cargan a demanda.

### P2 — Prioridad baja

#### H8. opencode.json sin configuración de economía (6 líneas)
Solo `skills.paths`. Faltan: `small_model` (router por complejidad, -60-80% costo en
tareas simples), `compaction` (auto+prune+reserved, ADR-0039 #1 y #3), límites de
tool output (POOL_TOOL_OUTPUT = 0.20 del presupuesto, token_budget.py:44),
`provider.options` (timeout 600000, chunkTimeout 30000, setCacheKey).
**Acción**: aplicar las configs del ADR-0039 secciones 1-3 y 9.

#### Extra. Higiene
- Generar `.agent.min.md` para release-ops y token-budget-auditor (los únicos sin
  versión compacta; el runtime usa full).
- Limpiar 4 líneas vacías dentro del frontmatter (builder.md:2-5, evolve-*.md:2-5).
- 15 de 22 agentes sin budget en token_budgets.yaml (solo 7 roles) — ver H6.

## Riesgos y límites
- H1/H2: regenerar mins con compile_skills.py puede re-romper frontmatter → el nuevo
  test de validación YAML es prerequisito.
- H3: elegir mapeo canónico de dominios (registry más granular).
- H5: tocar el orquestador que referencia la triada.
- H6: calibrar budgets contra métricas reales antes de endurecer.
- H8: cambiar opencode.json no aplica hasta reiniciar opencode (no hay hot-reload).

## Seguimiento
- P0 (H1-H3): siguiente iteración de builder/evolve-engineer con test de validación.
- P1 (H4-H7): iteración posterior con medición de éxito (catálogo de métricas).
- P2 (H8): aplicar junto con ADR-0039 en la próxima ventana de configuración.

## Registro de implementación (2026-08-04)

### H3 — ALINEADO (DONE)
`routing_rules.yaml` v2.1: ahora cubre los 32 skills reales de `skills_registry.yaml`
con ruta propia (domain = nombre del skill) + mantiene las 14 rutas agrupadoras
existentes (quantitative-analysis, risk-management, trading, ai-ml, memory,
quality, documentation, security, devops, mobile, data, frontend, architecture,
swarm-release-ops) con sus agentes originales preservados (primer agente intacto
para retrocompatibilidad del DelegationEngine). `universal` reducido de 10 agentes
a 2: `[coordinator, token-budget-auditor]`. Verificación: todos los domains son
skills reales o dominios fijos válidos (test_domains_reference_known_skills) y
todos los agentes referenciados existen en `.opencode/agents/*.md`
(test_all_agents_in_routes_exist).

### H7 — IMPLEMENTADO (DONE)
- Creado `.opencode/core/base_principles_full.md` (537 líneas, contenido completo
  N1+N2+N3 + MAPA DE ROLES + ABREVIACIONES) para consulta bajo demanda.
- `.opencode/core/base_principles.md` v2.6.0 reducido a N1+N2 (líneas 17-89
  intactas) + sección "## NIVEL 3 (bajo demanda)" con puntero al full (5 líneas).
- **Injector auditado**: el único loader de principios en código es
  `.opencode/core/prompt_optimizer.py::_load_principles_from_file()` (línea 307),
  que carga EXCLUSIVAMENTE `core/base_principles.md` — ya sin N3, por lo que el
  runtime inyecta solo N1+N2 sin tocar código. Los regex del parser (N1 block,
  tabla N2) siguen matcheando el archivo reducido; el MAPA DE ROLES (estaba en N3)
  degrada con fallback hardcoded (`fallback_roles`) sin error. No existe inyector
  en `harness/` (solo referencias en descripciones de skills/agentes y docs).
- Impacto de tokens: N3 ≈ 24.7K chars (~6.2K tokens) ya NO se inyecta en runtime
  con `include_principles: always` (5 roles core) → se resuelve el overflow del
  budget de coordinator (4,277 > 4,096 documentado en el contexto).

### H1 — IMPLEMENTADO (DONE) — 2026-08-04
Los 10 SKILL.min.md con frontmatter roto (5 YAML-error + 5 sin frontmatter) quedaron
válidos: 31/31 parsean con yaml.safe_load. Reparados por guardian + coordinador
(description con indentación corregida, claves `inherit` restauradas en hedgefund y
evolve). Test de regresión añadido: `TestSkillMinFiles` en
`harness/tests/test_opencode_config_sync.py` (valida delimitador `---`, parse YAML,
name/description no vacíos para todos los SKILL.min.md). Evita el fallback a tier
full (~20K tokens/sesión multi-skill).

### H4 — IMPLEMENTADO (DONE) — 2026-08-04
`agents/release-ops.md` deduplicado: body 2.7KB → 924B (-66%). Conserva rol + reglas
fijas + 2 líneas de conocimiento crítico (uv run, NLTK_DISABLE_IMPORT_SECURITY) +
referencia al skill swarm-release-ops (fuente única). Elimina drift entre copias.
Además: se generaron `.agent.min.md` para release-ops y token-budget-auditor (los
únicos sin versión compacta, preferida por el runtime).

### H5 — IMPLEMENTADO (DONE) — 2026-08-04
Triada evolve-analyzer/engineer/researcher consolidada (enfoque conservador):
bodies compactados a stubs de rol (< 900 chars) con referencia al skill evolve
(ROLE STACKING): 7.297 → 2.923 chars (-59,9%, ~1.100 tokens/loop). Frontmatter
limpiado (4 líneas vacías eliminadas). No se eliminaron archivos (el harness los
referencia en agent_list/routing/tests).

### H6 — IMPLEMENTADO (DONE) — 2026-08-04
token_budgets.yaml ahora gobierna el runtime: `TokenBudgetManager` carga el YAML
(role_budgets, defaults, compression_threshold, compression_levels) con fallback a
las constantes históricas si el archivo no existe y error ruidoso si está corrupto.
Nueva API: get_agent_budget, get_role_budget, get_session_budget,
get_compression_level, get_threshold, has_budget_config. BudgetManager.register_agent
resuelve budget explícito → role_budget YAML → default histórico. 23 tests nuevos
(test_token_budget_yaml.py) + backward compatibility verificada. Nota: guardian y
token-budget-auditor bajan de 4000 a 2048 — calibrar con monitoring.metrics.

### H8 — IMPLEMENTADO (DONE) — 2026-08-04
opencode.json con economía de tokens (validado contra schema oficial):
compaction {auto: true, prune: true, reserved: 10000}, tool_output {max_lines: 200,
max_bytes: 8192}, experimental {mcp_timeout: 30000}. Se omitieron deliberadamente
small_model y provider.options (providers del usuario desconocidos; riesgo de
romper el arranque — pendiente de decisión). `opencode agent list` carga sin
ConfigInvalidError.

### H2 — PENDIENTE (baja prioridad, justificado)
Recompactación de hedgefund (88%), quant-trading (77%), risk-execution (66%),
alpha-research (61%), evolve (59%): el peso de estos mins está en PROSA y pasos
numerados de API CQE (señal, no tablas truncadas — verificado con parser de
bloques). El recorte automático de tablas no produjo ahorro y el ADR advierte
"riesgo alto si se sobre-compactan (contenido denso es señal)". Requiere
reescritura manual cuidadosa de contenido API; beneficio marginal (~8K tokens en
sesiones multi-skill) no justifica el riesgo hoy. Opción sistémica futura: ajustar
compile_skills.py para omitir tablas de métricas en la generación.
