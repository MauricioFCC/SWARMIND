# ADR-0021: Frontier Gaps 2026 — Estado del Arte para AGENTIC

## Estado
**ACEPTADO** — Investigacion completada, gaps identificados, implementacion parcial.

## Contexto
AGENTIC alcanzo 1904 tests, 29 skills, 8 agentes. Analisis de 40+ papers julio 2026
identifica 5 gaps frontier con mayor ROI para alcanzar estado del arte.

## Gaps Identificados

### #1: Agent Capsules (arXiv:2605.00410)
- **Impacto**: -51% tokens, calidad identica (+0.02)
- **Implementacion**: capsule.execute(calls, strategy) en agent_capsules.py
- **3 estrategias**: compound (-51%), two_phase (-35%), sequential (baseline)

### #2: SePO (arXiv:2606.04465)
- **Impacto**: +4.49 pts accuracy, prompt auto-optimizacion
- **Estado**: Pendiente de implementacion
- **Requiere**: evolutionary archive, multi-task pool

### #3: CADVP v1.1 + Binding Drift (arXiv:2606.04896 + arXiv:2607.18316)
- **Impacto**: 0% fallos en canales A2A (vs 69-98% sin el)
- **Estado**: Pendiente
- **Requiere**: 13-dim verification protocol

### #4: DLP + HALO (arXiv:2607.18847 + arXiv:2607.17883)
- **Impacto**: 100% reduccion de fugas, 6 capas anti-hallucination
- **Estado**: Pendiente

### #5: Agentix + Helium
- **Impacto**: 4-15x throughput, 1.56x scheduler speedup
- **Estado**: Pendiente

## Gaps Adicionales (Julio 2026)
| Gap | Paper | Impacto |
|-----|-------|---------|
| SLIC Contribution Attribution | arXiv:2607.18255 | -93.3% costo atribucion |
| Phionyx Deterministic Runtime | arXiv:2607.18246 | 31% menos overhead |
| ZifaMem Structured Memory | arXiv:2607.17564 | +11.4% coherencia |

## Roadmap de Implementacion
1. Agent Capsules → COMPLETADO (agent_capsules.py, 8 tests)
2. SePO → Proxima iteracion
3. CADVP + BD → Proxima iteracion
4. DLP + HALO → Futuro
5. Agentix + Helium → Futuro
