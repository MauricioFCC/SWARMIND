# ADR-0010: Frontier Agents & Skills 2026

## Estado
**ACEPTADO** — Implementado en commit 306e9c4.

## Contexto
Swarmind implementa agentes especializados (builder, scientist, guardian, coordinator, evolve) con skills registrados. Hasta ahora las técnicas incorporadas cubrían patrones de flujo (WFP), testing (PBT), contexto (CEN), trazabilidad (BTR), guardrails (AGR) y versionado (SVE) — ADR-0008 — y lazy loading — ADR-0009.

Sin embargo, el panorama de investigación 2026 ha producido **25+ frameworks y papers nuevos** en 5 especialidades que Swarmind debe incorporar para mantenerse en la frontera:

1. **Builder**: SWE-Master (post-training SWE agents), BOAD (bandit agent design discovery), SWE-World (Docker-free training), AOrchestra (dynamic sub-agent creation), ParaManager (lightweight orchestrator), ShapleyFlow (game-theoretic workflow attribution)
2. **Scientist**: MetaClaw (continual meta-learning), MARS (metacognitive reflection), Hyperagents/DGM-H (self-referential self-improvement), Memento-Skills (skill-as-memory), Native Self-Evolution, ERL (experiential reflective learning), POLARIS (policy repair for small models)
3. **Guardian**: MuTON/mewt (language-agnostic mutation testing from Trail of Bits), AdverTest (adversarial dual-agent testing), SWE-Mutation benchmark (ACL 2026), CDBench (zero-sum game benchmark), UAgent (adversarial co-evolution), SWE-ABS (adversarial benchmark strengthening), PROBE (PBT adversarial refinement)
4. **Coordinator**: AdaptOrch (topology-aware orchestration, 12-23% improvement), NeuralFSM (learned FSM coordination), MPAC (multi-principal protocol, 95% overhead reduction), Symphony-Coord (bandit-based routing), LAS (LLM-as-Scheduler, 50.5% token reduction), StructAgent (state-centered framework), Enterprise event-driven orchestration patterns
5. **Evolve**: MetaClaw, MARS, Hyperagents, Memento-Skills, Native Evolution, ERL integration en el loop ASI-Evolve

6. **Frontend UI/UX**: Nuevo skill `frontend-uiux` con 7 papers y 10 frameworks de Generative UI 2026 (A2UI v0.9, OpenUI, Geeklego 3-tier tokens, StyleSeed 74 rules, 7onic, useVyre, UDS, LLUI)

## Decision
Actualizar los 4 agentes, 2 skills (evolve, base_principles) y crear 1 skill nuevo (frontend-uiux) con los hallazgos de investigación web frontera 2026.

### 1. Builder — Nuevas técnicas de codificación Swarmind

| Técnica | Referencia | Impacto |
|---------|-----------|---------|
| **SWE-Master** | arXiv:2602.03411 | 61.4% SWE-bench Verified (32B). LSP-driven tools para navegación semántica de codebases. Post-training: teacher-trajectory synthesis + long-horizon SFT + RL con execution feedback. |
| **BOAD** | Bandit Optimization for Agent Design | 53.12% SWE-bench Verified. Multi-armed bandit descubre automáticamente jerarquías multi-agente óptimas con presupuesto limitado. |
| **SWE-World** | Docker-free surrogate environments | 55.0% SWE-bench, 68.2% TTS@8. SWT (Transition Model) simula feedback paso a paso, SWR (Reward Model) simula test results. |
| **ParaManager** | Lightweight orchestrator | Small model con SFT+RL para descomposición paralela de subtareas. State-aware execution. |
| **ShapleyFlow** | ACL 2026 | Cooperative game-theoretic attribution para workflows agenticos. Shapley values guían dónde invertir capacidad de modelo. |

### 2. Scientist — Auto-mejora e investigación continua

| Técnica | Referencia | Impacto |
|---------|-----------|---------|
| **MetaClaw** | arXiv:2603.17187 | +32% accuracy, 8.25x task completion. Skill-driven fast adaptation + opportunistic policy optimization via RL con process reward model. Sin GPU local via proxy architecture. |
| **MARS** | Metacognitive Agent Reflective Self-improvement | Single-cycle recurrence. Principio-based reflection + procedural reflection. Supera multi-turn recursive con mucho menos costo. |
| **Hyperagents (DGM-H)** | Self-referential agents | Task agent + meta agent en programa editable. Meta-level improvements transfieren entre dominios. Self-accelerating. |
| **Memento-Skills** | Skill-as-memory | 26.2% y 116.2% mejora relativa en GAIA y HLE. 41-235 skills aprendidos. Cognition store como skill library. Router entrenado con RL. |
| **Native Self-Evolution** | Reward-free exploration | +20% WebVoyager/WebWalker. Qwen3-14B supera Gemini-2.5-Flash. Outcome-based reward solo en training. |
| **ERL** | Experiential Reflective Learning | +7.8% Gaia2. Heuristics > raw trajectories para transferencia entre skills. |
| **POLARIS** | Godel Agent policy repair | 7B model mejora consistentemente en MGSM, DROP, GPQA, LitBench. Policy repair sin fine-tuning costoso. |
| **ShapleyFlow** | Game-theoretic attribution | 9 LLMs, 1500+ tareas, 7 dominios. Atribuye mejora a componentes específicos del workflow. |

### 3. Guardian — Mutation testing adversarial

| Técnica | Referencia | Impacto |
|---------|-----------|---------|
| **MuTON/mewt** | Trail of Bits 2026 | Tree-sitter parsing language-agnostic (FunC, Tolk, Tact, Solidity, Rust, Go). SQLite persistence, two-phase campaigns, AI skill para campaign optimization. |
| **AdverTest** | Adversarial dual-agent | +8.56% fault detection vs mejores LLM methods, +63.30% vs EvoSuite. Test generation agent ↔ Mutant generation agent. |
| **SWE-Mutation** | ACL 2026 Findings | 2,636 mutated variants, 9 lenguajes. Solo 10.20% verification rate en LLMs. Swarmind mutation strategy reduce detection rate 71.04% → 39.81%. |
| **CDBench** | Zero-sum game benchmark | Code Defenders: Attacker introduce mutantes, Defender escribe tests. Modelos reasoning fallan 57-80% como attackers. |
| **UAgent** | Adversarial co-evolution | TG Agent + MG Agent. 92% accuracy en boundary-case. Framework-agnostic (Python/Java). |
| **SWE-ABS** | Adversarial benchmark strengthening | 50.2% instances strengthened (25.1x mejora). Rechaza 19.78% de patches que antes pasaban. |
| **PROBE** | ACL 2026 Findings | +9.79% mutation score. 45 bugs reales en librerías top-tier. Counter-implementation validation. |

### 4. Coordinator — Orquestación avanzada

| Técnica | Referencia | Impacto |
|---------|-----------|---------|
| **AdaptOrch** | arXiv:2602.16873 | 12-23% mejora sobre baselines static single-topology. 4 topologías canónicas: parallel, sequential, hierarchical, hybrid. Topology Routing Algorithm. |
| **NeuralFSM** | Learned FSM coordination | 6.74-19.39% mejora. Temporal Coordination Controller con Graph Networks. Sparse routing, dual-defense protection. |
| **MPAC** | Multi-Principal protocol | 95% reduction en coordination overhead. 4.8x wall-clock speedup. 21 message types, 3 state machines, Lamport-clock watermarking. |
| **Symphony-Coord** | Bandit-based routing | Two-stage dynamic beacon: candidate screening + LinUCB selector. Regret bounds sublineales. Maneja distribution shifts. |
| **LAS** | LLM-as-Scheduler | 50.5% token reduction, 36% latency reduction. Cascade: lightweight gate + LLM scheduler. Applicable a cualquier workflow existente. |
| **StructAgent** | State-centered framework | Qwen3.5-9B: 27.0% → 46.9% OSWorld. Estado unificado + workflow con verifier-backed transitions. |
| **Enterprise Patterns** | Event-driven orchestration | Task Manager con priority inference, related-event merging, preemption. 14-75% reducción latency alta prioridad. |

### 5. Evolve — Meta-skill de auto-mejora

Integración directa en `.opencode/skills/evolve/SKILL.md`:
- **MetaClaw**: Skill-driven fast adaptation + opportunistic policy optimization en ventanas de inactividad
- **MARS**: Metacognitive reflection single-cycle en cada Learn→Design→Experiment→Analyze
- **Hyperagents (DGM-H)**: Meta-agent auto-referencial que mejora su propio mecanismo de mejora
- **Memento-Skills**: Cognition store como skill library persistente con router contrastivo
- **Native Self-Evolution**: Exploration agent que genera World Knowledge antes de task execution
- **ERL**: Extracción de heuristics desde trayectorias de mejora, retrieval en nuevos ciclos

### 6. Frontend UI/UX — Nuevo skill profesional

Creación de `.opencode/skills/frontend-uiux/SKILL.md` (~580 líneas, 18 secciones):

| Componente | Frameworks/Referencias |
|------------|----------------------|
| **Generative UI** | A2UI v0.9 (declarative), OpenUI, Vercel json-render, arXiv:2604.09577 (83% preferencia) |
| **Design Systems AI-native** | Geeklego 3-tier tokens (GL-T, GL-C, GL-G), StyleSeed 74 rules, 7onic, useVyre, UDS |
| **Semantic Guidance** | ACM 2026 Bridging Gulfs — jerarquía Product→DesignSystem→Feature→Component |
| **UX Benchmarking** | ACL 2026 WiserUI-Bench — 300 pares A/B, razonamiento visual UX |
| **Personalization** | arXiv:2604.09876 — Bayesian active preference learning, kappa=0.25 |
| **WCAG 2.2 AA** | Contraste 4.5:1, focus visible, aria-labels, landmarks, semantic HTML |
| **Core Web Vitals** | LCP <2.5s, FID <100ms, CLS <0.1. Carga progresiva, lazy loading, critical CSS |
| **PBT Templates UI** | 7 templates: render_stable, idempotent_click, boundary_viewport, roundtrip_form, commutative_layout, associative_compose, responsive_invariant |
| **Visual Regression** | Playwright screenshots + pixelmatch diff. Umbral 0.1% regresión. |

## Archivos Creados
- `.opencode/skills/frontend-uiux/SKILL.md` — Skill profesional UI/UX (~580 líneas, 18 secciones)

## Archivos Modificados
- `.opencode/agents/builder.md` — +SWE-Master, BOAD, SWE-World, AOrchestra, ParaManager, ShapleyFlow
- `.opencode/agents/scientist.md` — +MetaClaw, MARS, Hyperagents, Memento-Skills, Native Self-Evolution, ERL, POLARIS, ShapleyFlow
- `.opencode/agents/guardian.md` — +MuTON/mewt, AdverTest, SWE-Mutation, CDBench, UAgent, SWE-ABS, PROBE
- `.opencode/agents/coordinator.md` — +AdaptOrch, NeuralFSM, MPAC, Symphony-Coord, LAS, StructAgent, Enterprise patterns
- `.opencode/skills/evolve/SKILL.md` — +MetaClaw, MARS, Hyperagents, Memento-Skills, Native Evolution, ERL
- `.opencode/core/base_principles.md` — +MCL, MKS, 17 nuevas abreviaturas en N1+N2+abbreviations
- `.opencode/skills/skills_registry.yaml` — +frontend-uiux registrado

## Tests
- **455 passed, 2 failed** (2 pre-existing LanceDB deprecation issues en semantic_cache)
- 0 regresiones por los cambios de agente/skill

## Despliegue
Propagado a 5 proyectos via `scripts/deploy_all.py`:
| Proyecto | Tipo | .opencode | harness | skills |
|----------|------|-----------|---------|--------|
| quant-engine | trading | 58 | 2033 | 7 |
| health-record | healthtech | 58 | 3170 | 5 |
| trading-bot-AIBot | trading | 58 | 337 | 7 |
| pos-system | retail | 62 | 715 | 4 |
| shared_memory | general | 58 | 1723 | 9 |

## Consecuencias
- **Positivas**: Los 4 agentes ahora incluyen 25+ técnicas de frontera 2026; nuevo skill UI/UX profesional con 10 frameworks; evolve loop potenciado con MetaClaw, MARS, Hyperagents; deploy inmediato a 5 proyectos.
- **Negativas**: ~80 tokens extra en perfiles de agente; frontend-uiux no desplegado automáticamente a proyectos (requiere config manual en deploy_all.py).

## Referencias
- arXiv:2602.03411 — SWE-Master: Post-Training for SWE Agents
- arXiv:2602.16873 — AdaptOrch: Topology-Aware Orchestration
- arXiv:2603.17187 — MetaClaw: Continual Meta-Learning for Agents
- arXiv:2604.09577 — LLMs as UI Generators
- arXiv:2604.09876 — Human-Centered Personalization with Generative AI
- arXiv:2507.04469 — Systematic Review on UI Generation with LLMs
- arXiv:2605.15425 — Runtime-Structured Task Decomposition
- arXiv:2606.16988 — Agent Trajectories as Programs
- ACL 2026 Findings — SWE-Mutation, WiserUI-Bench, PROBE, Generative Interfaces
- ACM 2026 — Semantic Guidance Bridging Gulfs
- DIS 2026 — ReFinE: Research-to-Design
- Trail of Bits 2026 — MuTON/mewt mutation testing
- ADR-0008: 6 nuevas técnicas (WFP, PBT, CEN, BTR, AGR, SVE)
- ADR-0009: Lazy Loading PEP 562
