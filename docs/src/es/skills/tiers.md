# Tiers de Residencia de Skills — @skills en SWARMIND

> Fuente: paper **"@skills: Attention Is All You Have"** (arXiv:2608.12610) + **ADR-0053** (`harness/context/skill_residency.py`) + SkillsBench (retrieval colapsa 29.6%@5 → 3.3%@100).

## El problema
Cada skill instalada paga **50–280 tokens en CADA mensaje** (standing tax) y compite por **<100 slots confiables de auto-trigger**. Con 34 skills y 5270 tokens si todas fueran INSTALLED, el modelo install-all estrangula el ecosistema.

## Los tres tiers

| Tier | Costo residente | Cuándo |
|------|-----------------|--------|
| **REFERENCE** | 0 tokens | Se lee en el punto de uso (`@skills:<path>`); long tail, one-offs |
| **SAVED** | 0 tokens | Copia vendida al proyecto (`.atskills/`); playbooks del equipo (10–30) |
| **INSTALLED** | frontmatter (~50–100 tok) | Solo lo que debe disparar sin ser pedido; **máximo 10** |

## Recomendación 2026-09-06 (34 skills)
- **INSTALLED (≤10):** las de uso diario del harness (coordinator/builder/guardian): `architecture`, `security-audit`, `data-science`, `evolve`, `frontend-uiux`, `rust-lang`, `devops-infra`, `swarm-release-ops`, `atdd-spec`, `quant-trading` (ajustar por proyecto).
- **REFERENCE (resto):** dominio y long tail, invocación explícita por nombre.
- **Fusionadas:** `responsive-ui` → `frontend-uiux` v1.2.0 (2026-09-06).

## Auditar
```bash
uv run python -c "
from pathlib import Path
from harness.context.skill_residency import audit_residency, recommend_tiers
rep = audit_residency(Path('.opencode/skills'))
print(rep.total_skills, rep.resident_if_all_tokens, rep.warnings)
"
```
