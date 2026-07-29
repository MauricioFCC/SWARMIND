# ADR-0028: Frontier Gaps 2026 v2 — Governance Decay, NLT, Multi-User

## Estado
**ACEPTADO** — Investigacion completada. Implementacion priorizada.

## Contexto
Investigacion de 15+ papers julio 2026 + analisis de proyectos similares (VoltAgent, trigger.dev, PraisonAI, IntentKit) identifico 3 gaps criticos y 7 de alto valor.

## Gaps Criticos Implementados

### 1. Constraint Pinning (arXiv:2606.22528)
**Problema:** Context compaction puede borrar constraints de seguridad silenciosamente.
**Implementacion:** `GovernanceGuard` con invariantes protegidas contra compaction.
**Archivo:** `harness/orchestrator/governance_guard.py`

### 2. Natural Language Tools (arXiv:2607.03953)
**Problema:** Tool calling estructurado tiene -93% errores pero formato rigido.
**Implementacion:** Modo opcional NLT para tool calling en lenguaje natural.
**Archivo:** `harness/orchestrator/natural_language_tools.py`

### 3. Multi-User Governance (arXiv:2606.21856)
**Problema:** Sin permisos multi-usuario, el sistema no escala organizacionalmente.
**Implementacion:** Permisos basados en roles con execution hooks.
**Archivo:** `harness/orchestrator/multi_user_governance.py`

## Proyectos Analizados
| Proyecto | Stars | Gap en AGENTIC |
|----------|-------|----------------|
| VoltAgent/subagents | 23.8k | Marketplace de skills |
| trigger.dev | 15.8k | Despliegue serverless |
| PraisonAI | 8.5k | Workforce autonomo 24/7 |
| IntentKit | 6.5k | Modo cluster distribuido |

## Papers Aplicados
| Paper | Gap | Impacto |
|-------|-----|---------|
| arXiv:2606.22528 | Governance Decay | CRITICO |
| arXiv:2607.03953 | Natural Language Tools | ALTO |
| arXiv:2606.21856 | Multi-User Governance | CRITICO |
| arXiv:2607.25446 | Organizational Science | ALTO |
| arXiv:2607.13591 | Learned Adaptive Memory | ALTO |

## Consecuencias
- **Nuevos modulos:** 3 (governance_guard, nlt, multi_user)
- **ADRs totales:** 28
- **Gaps cerrados:** 3/3 criticos, 2/7 alto valor

