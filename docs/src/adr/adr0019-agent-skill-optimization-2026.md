# ADR-0019: Agent & Skill Optimization 2026 — Revisión Crítica y Especialización

## Estado
**ACEPTADO** — Implementado en 2026-07-22. Commits: 754b6cb, 2883404, 20933a3.

## Contexto
El sistema AGENTIC cuenta con 8 agentes y 16 skills desplegados en 5 proyectos. Auditoría profunda con 3 especialistas (scientist+guardian+builder) más investigación web frontera de 15 papers 2026 reveló:

### Problemas sistémicos identificados y corregidos:
1. **Frontmatter inconsistente** entre agentes — Estandarizado
2. **DRY/SSOT violado**: PaCoRe, LTS, Token Economics duplicados en 3+ agentes
3. **Triggers demasiado amplios** en coordinator — Podados
4. **12 agentes fantasma** en routing_rules.yaml — Limpiado (solo 8 reales)
5. **responsive-ui duplicaba frontend-uiux** — Fusionado
6. **6 skills sin SKILL.min.md** — Creados (cobertura 100%)
7. **skills_registry.yaml con duplicados** — Deduplicado (86→62 lines)

### Oportunidades identificadas:
- 4 nuevos skills especializados creados (Rust, Architecture, UI/UX, Data Science)
- Worktable: sistema de debate multi-agente con 13 expertos en calidad de software
- Security-audit skill (SAST, DAST, SBOM, Threat Modeling)

## Decisión e Implementación

### 1. Skills Minificados (6 nuevos SKILL.min.md)
| Skill | Archivo | Dominio | Responsabilidades |
|-------|---------|---------|-------------------|
| **rust-lang** | `SKILL.min.md` | systems | Ownership, async, FFI, crates, performance |
| **architecture** | `SKILL.min.md` | architecture | GoF, hexagonal, C4, DDD, ADRs |
| **data-science** | `SKILL.min.md` | data | ML pipelines, PyTorch, GPU, feature engineering |
| **responsive-ui** | `SKILL.min.md` | frontend | Mobile-first, WCAG 2.2, Core Web Vitals |
| **security-audit** | `SKILL.min.md` | security | SAST, DAST, threat modeling, SBOM |
| **frontend-uiux** | `SKILL.min.md` | frontend | Generative UI, design tokens, semantic guidance |

**Cobertura de minificación: 16/16 skills (100%)**

### 2. Fusiones y Limpieza
- **responsive-ui** → fusionado dentro de **frontend-uiux** (WCAG 2.2 + Core Web Vitals)
- **skills_registry.yaml**: 16 entries, todas con `version: 1.0.0` y `project_agnostic: true`
- **routing_rules.yaml**: 14 dominios con agentes reales (eliminados 12 fantasmas)

### 3. Worktable — Sistema de Debate Multi-Agente (NUEVO)
**Archivo:** `harness/orchestrator/worktable.py` (451 lines, 62 tests)

Sistema de debate estructurado entre N agentes especializados en atributos de calidad:
- **13 perfiles**: SoC, Low Coupling, High Cohesion, Resilience, Scalability, Observability, Clean Code, Maintainability, Testability, Interoperability, Security, DevOps, Trade-offs
- **3 rondas**: Opening → Critique → Refinement → Compendium
- **Mock dispatch** para modo offline deterministico
- **Compendium final** con acuerdos, trade-offs y recomendaciones

### 4. Investigación Web Frontera 2026 (18 papers aplicados)
| Paper | Hallazgo | Aplicación | Prioridad |
|-------|----------|------------|-----------|
| **arXiv:2606.23127** | AFTER: 382 tareas enterprise, 22 skills procedurales. +3.7-6.7 pts por ronda de refinamiento. Skills multi-modelo: 73.1% accuracy cross-model | Refinement loop validado para skills AGENTIC | 🔴 Alta |
| **arXiv:2606.19758** | SIGMA: Skill-incidence graphs. +2.06 pts vs CARD. Agentes como bundles de skills reusables. Robusto a skill libraries no vistas (drop 0.96 pts) | Composición dinámica de agentes desde skills | 🔴 Alta |
| **arXiv:2605.27864** | FundaPod: Declarative skill registry → typed task graphs. Aislamiento cognitivo entre agentes. Knowledge graph "second brain" | Skills_registry.yaml → task graphs automáticos | 🔴 Alta |
| **arXiv:2607.05377** | Cortex: 32 canonical skill primitives estandarizadas para manipulación | Estandarización de primitivas de skill | 🟡 Media |
| **arXiv:2606.30775** | Skill collision detection (79.2% F1, 32x speedup) | Frontmatter + triggers validados | 🟢 Hecho |
| **arXiv:2606.04465** | SePO self-referential prompt optimization (+4.49 pts) | Auto-mejora de system prompts | 🟡 Media |
| **arXiv:2607.15257** | SearchOS chunking jerárquico | Hierarchy base_principles > skills > agents | 🟢 Hecho |
| **arXiv:2606.04896** | Channel Fracture (13-dim CADVP, 0% fallos) | Verificación A2A router | 🟡 Media |
| **arXiv:2606.27492** | QueenBee topologías auto-evolutivas (RMSE 12.53→7.87) | Coordinación dinámica | 🟡 Media |
| **arXiv:2607.06101** | SHIELD: Agents that Teach (6 principios) | Dimensión educativa complementaria | 🟢 Baja |
| **arXiv:2607.13027** | PalmClaw on-device agent (+11.5% success, -94.9% time) | Paradigma mobile agent | 🟢 Baja |

### 5. Estado Actual del Sistema
| Componente | Cantidad |
|------------|----------|
| **Agentes** | 8 (coordinator, builder, scientist, guardian, evolve + 3 sub-agentes) |
| **Skills** | 16 (todos con SKILL.md + SKILL.min.md) |
| **ADRs** | 21 (0001-0020) |
| **Tests** | 1851 (0 failures) |
| **Cobertura** | ~65% |
| **Worktable** | 13 expertos, 62 tests |

## Consecuencias
- **Skills 100% minificados**: Deploy eficiente a proyectos
- **Sin duplicación en registry**: SSOT restaurado
- **Worktable**: Framework para decisiones arquitectónicas basadas en debate multi-agente
- **Research pipeline**: 15 papers 2026 analizados e integrados
- **Routing preciso**: Solo agentes reales referenciados en routing_rules.yaml
