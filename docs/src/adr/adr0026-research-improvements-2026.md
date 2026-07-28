# ADR-0026: Investigacion Aplicada — Atlas Graph, Governance, Meta Ads

## Estado
**ACEPTADO** — Investigacion completada. Mejoras implementadas.

## Contexto
Investigacion de 4 documentos en PROP-INVEST-PAPERS + referencias web:
1. **Propuesta Meta Ads Optimizer**: Skill especializado en publicidad digital con BOAD, ShapleyFlow, MetaClaw
2. **Orquestacion Agentica CX**: Framework de gobernanza para agentes autonomos
3. **Guia Diseno y Arquitectura**: Principios de sistemas distribuidos (DDIA, DevOps Handbook)
4. **Mapa Vivo Arquitectura (Atlas)**: Grafo de conocimiento arquitectonico con C4 model

## Mejoras Implementadas

### 1. Atlas Knowledge Graph — Enhanced con C4 Model
**Archivo:** `harness/memory_rag/knowledge_graph.py` (actualizado)
- Soporte para C4 model (Context, Container, Component, Code)
- Relaciones entre nodos: depends_on, produces, consumes, feeds, serves, runs_on, monitors
- Query por lenguaje natural sobre el grafo
- Seed automatico desde estructura del proyecto

### 2. Agente de Gobernanza
**Archivo:** `harness/orchestrator/governance_agent.py` (nuevo)
- Framework de supervision para decisiones autonomicas
- Registro de decisiones con contexto, alternativas y justificacion
- Evaluacion de riesgos pre-deploy
- Trazabilidad completa de decisiones de agentes

### 3. Skill Meta Ads Optimizer
**Archivo:** `.opencode/skills/meta-ads-optimizer/SKILL.md` (nuevo)
- Optimizacion de campanas Meta Ads con BOAD, ShapleyFlow
- 12 sub-skills: campaign-architect, creative-analyzer, audience-builder, budget-allocator
- Integracion con quant-trading para risk management de budget

## Papers y Referencias
| Fuente | Aporte | Implementacion |
|--------|--------|----------------|
| BOAD (Bandit Optimization) | Budget allocation multi-campana | Skill meta-ads-optimizer |
| ShapleyFlow (ACL 2026) | Atribucion causal cross-channel | Knowledge Graph relaciones |
| MetaClaw (arXiv:2603.17187) | Adaptive creative optimization | Creative analyzer |
| Atlas Architecture Map | Grafo de conocimiento vivo | Knowledge Graph C4 |
| CX Agentic Orchestration | Gobernanza de agentes | Governance Agent |
| DDIA (Kleppmann) | Sistemas distribuidos | Principios arquitectonicos |
| DevOps Handbook | Tres vias DevOps | CI/CD principles |

## Consecuencias
- **Nuevos skills:** 1 (meta-ads-optimizer)
- **Skills totales:** 30
- **Modulos nuevos:** governance_agent.py
- **Knowledge Graph:** Mejorado con C4 model y NLP queries
- **ADRs totales:** 26
