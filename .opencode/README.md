# .opencode System — Universal Multi-Agent Framework v2026

> **🏦 Doctrina Hedge Fund**: Este sistema puede operar bajo la doctrina de **Hedge Fund Institucional**.
> Los LLMs actúan como gestores del fondo (CIO, PM, Quant, CRO, COO). Cada tarea es una asignación
> de capital con riesgo/reward, mandato y stop-loss. Más información en `skills/hedgefund/SKILL.md`.

Sistema multi-agente evolutivo con orquestación Swiss Watch, memoria vectorial LanceDB,
auto-mejora ASI-Evolve, **Token Economics v2026** (Harness Effect: -41% costo, -44% tiempo),
y routing adaptativo con cutting-edge competitive programming y text analysis techniques.

---

## Estructura

```
.opencode/
├── agents/              # 5 agentes core + 3 sub-agentes evolve
│   ├── coordinator      # Swiss Watch orchestrator (punto de entrada unico)
│   ├── builder          # Implementacion + optimizacion + CP techniques
│   ├── scientist        # Investigacion + AI/ML + text analysis
│   ├── guardian         # Calidad + testing vanguardia + seguridad
│   ├── evolve           # Meta-agente: auto-mejora continua
│   ├── evolve-researcher/  # Sub-agente: investigacion para evolve
│   ├── evolve-engineer/    # Sub-agente: ingenieria para evolve
│   └── evolve-analyzer/    # Sub-agente: analisis para evolve
├── config/              # Configuracion central
│   ├── project_config.yaml    # Metadata del proyecto v2.1.0
│   ├── routing_rules.yaml     # Keywords/regex → agente destino
│   └── token_budgets.yaml     # Limites de tokens por rol
├── core/                # Modulos base del framework
│   ├── base_principles.md     # 9 categorias universales (ARQ, SEG, DOC...)
│   ├── base_skill_template.md # Plantilla v3 con FDE + Evolve + C.A.S.E.
│   ├── fde_principles.md      # 7 pilares FDE + glosario + checklist
│   ├── guardrails.py          # Pre/post pipeline (19 checks)
│   ├── prompt_optimizer.py    # Compresion, budget, relevance scoring
│   ├── registry.py            # Skill registry con contratos
│   ├── router_v2.py           # Grafo de estado + multi-agent patterns
│   ├── router_a2a.py          # Agent-to-Agent protocol
│   ├── router_scoring.py      # Multi-agent pattern scoring
│   └── skill_schema.json      # Schema v3
├── skills/              # 10 skills activos
│   ├── alpha-research/        # Factor research, ML, feature engineering
│   ├── evolve/                # Meta-skill: self-improvement loop
│   ├── healthtech/            # Healthtech, HIPAA, clinical systems
│   ├── hedgefund/ ⭐          # Doctrina fundacional
│   ├── legal-doc/             # Legal document analysis, Colombia law
│   ├── math-doc/              # Mathematical document processing
│   ├── pos-retail/            # Point of sale, retail
│   ├── quant-trading/         # Quantitative trading strategies
│   ├── risk-execution/        # Risk management, position sizing
│   └── science-doc/           # Scientific document analysis
└── .gitignore
```

---

## Agentes (5 core + 3 sub-agentes)

| Agente | Rol | Cutting-Edge 2026 |
|--------|-----|-------------------|
| **coordinator** (default) | Swiss Watch orchestrator — DifficultyRouter → ScaleDecider → PaCoRe → Consolidar | Token Economics (-38% tokens), Dynamic Scaling 3-11 agentes, Failure Governance 6 tipos + Circuit Breaker, Structured Compaction (-41% costo) |
| **builder** | Implementacion + optimizacion algoritmica | TDAD/TDFlow (92-94% pass), PaCoRe parallel reasoning, PROBE/AdverTest adversarial loop, 30+ tecnicas CP (Stoer-Wagner, SMAWK, HLD, Segment Tree, Matrix Exp.) |
| **scientist** | Investigacion + papers + AI/ML + text analysis | PaCoRe/LTS/Helium (1.56x speedup), 38-metric catalogue, Doc-Researcher multimodal, Arg-LLaDA sufficiency-aware, Multi-Granularity Discourse Parsing |
| **guardian** | Calidad + testing vanguardia + seguridad | PROBE (+9.79% mutation), SpecOps (F1 0.89), AdverTest (+8.56%), SMART (72.24% validity), FuzzAgent (179K branches), PBT, Mutation Testing |
| **evolve** (meta) | Auto-mejora ASI-Evolve | Agentic RL Scaling (KAT-Coder, PaCoRe Train, 6.2x speedup), Spec Evolution (SURS), Role Evolution (AOSE), FDE Checklist, Autobuilder |

---

## Arquitectura

### Core Pillars
- **FDE** — Forward Deployment Engineering: 7 pilares (DELTA, MISSION, GLUE, VALUE, DIPLOMACY, RESILIENCE, EVOLVE)
- **C.A.S.E.** — Clarify → Architect → Solve → Evaluate: marco universal de razonamiento
- **ASI-Evolve** — Autonomous self-improvement loop: cognition store, experiment DB, RL scaling, spec evolution

### Token Economics v2026 (Harness Effect)
Costo/task = f(harness) > f(modelo). El orquestador es la palanca mas grande de eficiencia.

| Mecanismo | Impacto | Implementacion |
|-----------|---------|----------------|
| Cache-Shape Discipline | -38% tokens | Estructurar I/O para maximizar KV-cache hits |
| Structured Compaction | -41% costo | Compresion por relevancia, no truncacion lineal |
| Scoped Context Spawn | -44% tiempo | Sub-agentes con contexto minimo necesario |
| Phase-Scheduled MAS | -27.3% tokens | Ciclo trifasico 0°/120°/240° activa subconjuntos |
| Observation Masking | -60% obs. tokens | Placeholders para tool outputs grandes |
| Failure-Spend Governance | Elimina runaway | Stop-loss por tarea, WAL obligatorio |

### Routing Graph
Router v2 implementa grafo de estado con:
- **Single-agent**: ruteo directo por intencion (keywords + regex)
- **Multi-agent Sequential**: cadena de agentes (output N → input N+1)
- **Multi-agent Parallel**: agentes en paralelo con merge (concat/vote/priority)
- **Multi-agent Loop**: repite hasta convergencia o max_iterations
- **Dynamic Scaling**: Small(3), Medium(5), Large(8), XLarge(11) agentes

### Guardrail Pipeline
Pre-checks (arquitectura + discovery) y post-checks (seguridad + commits + docs + three whys).
3 severidades: BLOCK / WARN / INFO. 19 checks en total.

---

## Skills Activos (10)

| Skill | Dominio | Cutting-Edge 2026 |
|-------|---------|-------------------|
| **hedgefund** ⭐ | financial | Doctrina fundacional: hedge fund, riesgo/reward, mandato, stop-loss |
| **alpha-research** | quantitative | PaCoRe parallel exploration, LTS shared memory, Harness Effect |
| **quant-trading** | quantitative | PaCoRe parallel exploration, Helium scheduling, Agentix programs |
| **risk-execution** | quantitative | Circuit breaker, failure classification, Token Budget Governance |
| **evolve** | meta | Token Economics, Agentic RL Scaling, Spec Evolution, FDE, Autobuilder |
| **healthtech** | healthtech | PROBE adversarial testing, PBT, SMART mutation testing |
| **legal-doc** | legal | AOSE Hybrid Roles, structured output contracts, RTF+C methodology |
| **math-doc** | academic | PaCoRe parallel reasoning, REPOREASON diagnostic metrics |
| **science-doc** | academic | 38-metric catalogue, LTS shared memory, Token Maxing analysis |
| **pos-retail** | retail | TDAD test-driven compilation, SpecOps testing, FuzzAgent fuzzing |

---

## Quality Improvements 2026

### Error Handling
- **0 silent exceptions**: Todos los `except Exception:` tienen `logger.warning()` con contexto
- **Circuit Breaker**: 3 fallos identicos → causa-aware steering → half-open recovery
- **Failure Classification**: 6 tipos (Rate Limit, Stall, Timeout, Malformed, Outage, Permanent)

### DRY / SSOT
- **Embedding**: `harness/common.fallback_embedding()` es la UNICA fuente de embedding (10+ implementaciones eliminadas)
- **Token Estimation**: `harness/common.estimate_tokens()` es la UNICA fuente de conteo de tokens
- **EMPTY_VECTOR**: Constante centralizada para `np.zeros(384, dtype=np.float32)`
- **Compression**: `common.compression_pct()` y `common.avg_compression_pct()` son las unicas fuentes

### Testing Coverage
- 394 tests pasando
- Cobertura core modules >80%
- Mutation testing, adversarial testing, property-based testing integrados
- Test-Driven AI Agent Definition (TDAD) pipeline

---

## Commands

### Evolve Loop
- `!evolve status` — Estado del loop
- `!evolve run <skill> <rounds>` — Ejecutar N rondas de mejora
- `!evolve cognition add <title> <content>` — Anadir conocimiento
- `!evolve cognition search <query>` — Buscar en cognition store
- `!evolve best <skill>` — Mejor snapshot actual
- `!evolve stats` — Estadisticas del loop

### Delegacion Directa
- `@builder: <tarea>` — Implementacion + optimizacion
- `@scientist: <tarea>` — Investigacion + papers + analisis
- `@guardian: <tarea>` — Testing + calidad + seguridad
- `@evolve: <tarea>` — Auto-mejora del sistema

### Diagnostico
- `!health` — Health check del sistema (3 niveles)
- `!metrics` — Metricas de rendimiento
- `!quality-fix` — Correccion de calidad automatica

---

## Extension

1. Crear `skills/{nuevo-rol}/SKILL.md` usando `core/base_skill_template.md`
2. Anadir routing rules en `config/routing_rules.yaml`
3. Anadir nodo en `core/router_v2.py` `ROUTING_GRAPH`
4. Registrar en `core/skill_schema.json`

---

## Referencias

- `skills/hedgefund/SKILL.md` ⭐ — Doctrina Fundacional
- `core/base_skill_template.md` — Template v3.0 con FDE + Evolve + C.A.S.E.
- `core/fde_principles.md` — 7 pilares FDE + glosario + checklist
- `core/guardrails.py` — Pre/post pipeline con 19 checks
- `core/prompt_optimizer.py` — Compression, budget, relevance scoring
- `core/router_v2.py` — Grafo de estado con multi-agent patterns
- `docs/src/adr/adr0008-token-economy-speed.md` — ADR Token Economics v2026
- `docs/src/adr/adr0009-competitive-programming-2026.md` — ADR CP Techniques v2026
- `docs/src/adr/adr0010-text-analysis-2026.md` — ADR Text Analysis v2026
