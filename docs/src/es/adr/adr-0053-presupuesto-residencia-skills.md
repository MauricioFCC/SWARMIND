# ADR 0053: Presupuesto de Residencia de Skills y Tiering

## Estado
Aplicado | Implementado en `harness/context/skill_residency.py` (extiende ADR-0052) | Propietario: @coordinator

## Contexto
El paper "@skills: Attention Is All You Have" (arXiv 2608.12610, SylphAI, ago 2026) demuestra que las
descripciones de skills instaladas pagan un impuesto permanente de **50–280 tokens en CADA mensaje**
(distancia decay + standing tax + dilution) y compiten por **menos de 100 slots confiables de
auto-trigger** por agente. Con 56,804 skills publicadas compitiendo por ese presupuesto, el modelo
install-only estrangula el ecosistema: los autores escriben "bids" en vez de descripciones (~20x tokens),
los usuarios instalan menos de lo que podrían, y lo instalado se olvida.

SWARMIND tiene **35 skills** en `.opencode/skills/`, todas potencialmente residentes. El registry
(`skills_registry.yaml`) no mide tokens. Dos evidencias independientes (este paper + SkillsBench del
ADR-0052: precisión de retrieval colapsa de 29.6%@5 a 3.3%@100 skills) apuntan al mismo fenómeno.

## Decisión
Adoptar el modelo de **tres tiers** del protocolo @skills para el inventario de skills de SWARMIND:

| Tier | Costo residente | Mecanismo |
|------|-----------------|-----------|
| REFERENCE | 0 tokens | Se lee en el punto de uso (`@skills:<path>`), muere con la sesión |
| SAVED | 0 tokens | Copia vendida al árbol git del proyecto (`.atskills/`), sin residencia |
| INSTALLED | frontmatter (50–100 tok) | Único tier que dispara sin ser pedido; reservar para <10 esenciales |

Implementación:
1. `audit_residency(skills_dir)` — parsea el frontmatter YAML de cada SKILL.md, estima tokens
   (heurística ~4 chars/token) y produce un `ResidencyReport` inmutable con el costo total si
   todas fueran instaladas.
2. `recommend_tiers(report, essential)` — clasifica: esenciales → INSTALLED, resto → REFERENCE.
3. Constantes del paper como fuente única: `RESIDENT_SLOT_BUDGET = 100`,
   `TARGET_RESIDENT_MAX = 10`, `DESC_TOKEN_RANGE = (50, 280)`.

## Consecuencias
### Positivas
- El costo de una skill pasa de default a decisión explícita; 35 skills alcanzables con <10 residentes.
- Presupuesto de atención medible y auditable (número visible, revisable como diff).
- Coherente con ADR-0052: la poda recomendada por salud de librería ahora tiene mecanismo de tiers.
- Composición determinista: co-firing N skills por referencia explícita vs lotería probabilística.

### Negativas
- Las skills no residentes requieren invocación explícita (el agente debe saber que existen).
- Requiere disciplina periódica de auditoría (script ejecutable, no proceso automático).

## Alternatives Considered
1. **Mantener todas instaladas**: paga el standing tax completo y degrada el trigger (evidencia SkillsBench).
2. **Plugin bundling**: sin control por-skill dentro del bundle (dominant harness no lo ofrece).
3. **AGENTS.md monolítico**: siempre cargado, cero setup, pero sin trigger selectivo ni granularidad.

## Relacionado
- ADR 0052: Habilidades de Agente (salud de librería de skills)
- Paper: https://arxiv.org/abs/2608.12610 — Protocolo: https://github.com/SylphAI-Inc/atskills
