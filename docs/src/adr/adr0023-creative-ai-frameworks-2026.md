# ADR-0023: Creative AI Frameworks v2026 — ReDNA, Diversity Collapse, IdeaForge

## Estado
**ACEPTADO** — Implementado en commit eb9e1ec.

## Contexto
AGENTIC no incorporaba ningún framework de creatividad computacional. Investigación de 10+ papers julio 2026 identificó 3 brechas críticas:

1. **Diversity Collapse** (arXiv:2604.18005): Sistemas multi-agente para ideación sufren *structural coupling* — la interacción entre agentes *contrae* la exploración. Topologías densas aceleran convergencia prematura. **Crítico**: modelos más fuertes → diversidad marginal decreciente.

2. **ReDNA** (arXiv:2605.28465): Benchmark de pensamiento divergente en 2 niveles (path-level y action-level). Propone pipeline: generar N ideas libremente → seleccionar bajo restricciones → integrar.

3. **IdeaForge** (arXiv:2605.13311): Knowledge Graph + multi-metodología (TRIZ, Design Thinking, SCAMPER) con agentes especializados para innovación sistemática.

## Decisión e Implementación

### 1. CreativeWorktable — Pipeline ReDNA
**Archivo:** `harness/orchestrator/worktable.py` (+202 lines)

Tres fases del proceso creativo:

| Fase | Método | Descripción |
|------|--------|-------------|
| **Divergente** | `divergent_phase()` | Generar N ideas libremente, agentes independientes |
| **Convergente** | `convergent_phase()` | Seleccionar bajo restricciones (novelty*0.4 + feasibility*0.6) |
| **Integración** | `integration_phase()` | Combinar top 3 ideas en propuesta final |

**Protección contra Diversity Collapse:**
- Topología sparse por defecto (no fully-connected)
- `independence_rounds=2`: rondas de generación aislada antes de compartir
- `divergence_pressure=0.3`: forzar opiniones disidentes
- `authority_penalty=0.1`: penalizar deferencia a agente senior

### 2. Integración en Worktable
- `debate()` acepta nuevo parámetro `creative_mode: bool = False`
- Cuando es `True`, deriva a `_creative_debate()` que ejecuta ReDNA completo
- Lógica existente del debate normal intacta (0 regresión)

### 3. Tests
- 45 tests en `harness/tests/test_creative_worktable.py`
- Cobertura: CreativeIdea, CreativeConfig, fases divergente/convergente/integración, debate creativo, config personalizada, rangos de novedad/factibilidad

### 4. Papers Investigados (10+)
| Paper | Hallazgo | Aplicación |
|-------|----------|------------|
| **ReDNA** (arXiv:2605.28465) | Pipeline divergente→convergente | CreativeWorktable |
| **Diversity Collapse** (arXiv:2604.18005) | Topologías densas matan diversidad | Config sparse, independence_rounds |
| **IdeaForge** (arXiv:2605.13311) | KG multi-metodología | InnovationScore planning |
| **AutoWorldBuilder** (arXiv:2607.09403) | DAG scheduler + compresión 90% | Integración contextual |
| **MUTATE** (arXiv:2605.28465) | Métricas de divergencia path/action-level | Catálogo extendido |
| **MusicSwarm** (arXiv:2509.11973) | Estigmergia peer-to-peer | Topología descentralizada |
| **AutoSOTA** (arXiv:2604.05550) | 8 agentes, 105 SOTA models | Pipeline multi-rol |
| **MacGyver** (2311.09682) | Creative problem-solving | Reflection pattern |
| **IDVSCI** (arXiv:2506.18348) | Dual-Diversity Review | Evaluación heterogénea |

## Consecuencias
- **Tests totales:** 2308 (+45 creativos)
- **Worktable:** 528 lines + 202 creativos = 730 lines (<900 ✓)
- **Nuevas capacidades:** CreativeWorktable con 3 fases, CreativeConfig, 7 métodos públicos
- **Papers aplicados:** 10+ papers frontier 2026 integrados
- **0 regresión:** 62 tests existentes intactos
