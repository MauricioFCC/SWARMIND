# ADR 0090: Pulido de Skills y Agentes — Mesa Adversarial + SkillReducer

## Estado
Aplicado | `skill_bundler` extendido + `skill_collision_probe.py` + split data-science + normalización de agentes | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Mesa adversarial (atacante vs steelman) + research frontera (SkillReducer arXiv:2603.29919, Single Rewrite: 79.2% F1 auto vs 79.4% manual, SkillRouter retrieve-and-rerank). Veredicto del juez:
- **Rechazadas** fusiones masivas de agentes (rompen 23 tests/docs/routing) y reescritura total de descripciones (scopes genuinos piden arquitectura, no wording).
- **Aceptadas** mejoras quirúrgicas de alto ROI.

## Decisión
1. **`SKILL_TO_AGENT` 15→35** + dominio `quality` (keywords) + `devops` extendido (todas las skills ruteables).
2. **Agentes normalizados**: `coordinator` sin catch-all (24→19 triggers), `test-writer.agent.min.md` creado, `evolve-analyzer.agent.min.md` reescrito (< .md).
3. **data-science split** (398→69L + `core.md` 95L + `advanced.md` 216L, patrón ADR-0048).
4. **`skill_collision_probe`**: shadow test con queries discriminantes (quant x4, psych x2); misroute reportado con query/esperado/obtenido.

TDD: 5 tests probe + suites existentes (72 bundler/agent + 217 pec/config/frontmatter); ruff 0; validator ✅.

## Consecuencias
### Positivas
- 0 skills huérfanas de routing; colisiones detectadas en CI, no por usuarios.
- Standing tax de data-science −83% en carga base.

### Negativas
- 23 agentes intactos (slots de retrieval sin cambio; mitigado por tiers).

## Alternatives Considered
1. **Fusión masiva de agentes**: rompe tests/docs/routing; rechazada.
2. **Reescritura total de descripciones**: Single Rewrite demuestra que no supera lo manual en scopes genuinos; rechazada.
3. **SkillRouter con embeddings**: YAGNI a 35 skills (documentado en ADR-0075).

## Relacionado
- ADR-0048 (progressive disclosure), ADR-0072 (PEC), ADR-0075 (composición), SkillReducer/Single Rewrite
