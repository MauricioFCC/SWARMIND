# ADR-0025: Frontier Coding Quality & Legal NLP 2026

## Estado
**ACEPTADO** — Implementado en commit 1a61355.

## Contexto
Investigacion profunda de 10+ papers 2026 identifico 2 areas de mejora critica:
1. **Coding Quality**: Property-Based Testing como especificacion ejecutable + Refinement Types
2. **Legal/Academic NLP**: CLAUSE Benchmark, LegalSeg rhetorical roles, causal citation analysis

## Decisiones e Implementacion

### 1. Property-Based Testing (Hypothesis)
**Papers aplicados:**
- **Agentic PBT** (NeurIPS 2025, arXiv:2510.09907): 56% de reportes fueron bugs validos
- **Semantic Triangulation** (arXiv:2511.12288): +24% seleccion correcta de programas

**Implementacion:** `harness/tests/test_pbt_core.py` — 20 tests de propiedad:
| Componente | Propiedades | Tests |
|-----------|------------|-------|
| Semantic Cache | Roundtrip, idempotencia, monotonicidad | 9 |
| Token Optimizer DAG | Sin ciclos, speedup >= 1.0, orden topologico | 4 |
| Structured Prompt | Formatos distinguibles, no vacio | 6 |
| Token Budget | Remaining no negativo, usage_pct <= 100% | 1 (stateful) |

### 2. Refinement Types (Contratos de Codigo)
**Implementacion:** Validaciones tipo-refinement en `AgentBus.post_message()` y `AsyncAgentBus`:
- `assert len(channel) > 0` - canal no vacio
- `assert message_type in _VALID_MESSAGE_TYPES` - tipo valido
- `assert iteration >= 0` - iteracion no negativa
- 25 tests de cobertura en `test_agent_bus_refinement.py`

### 3. Investigacion Legal NLP (documentada para implementacion futura)
| Paper | Tecnica | Aplicacion |
|-------|---------|------------|
| **CLAUSE** (arXiv:2511.00340) | 7500+ contratos perturbados, 10 anomalias | Suite de validacion para legal-doc |
| **LegalSeg** (NAACL 2025) | RhetoricLLaMA + GNN para roles retoricos | Segmentacion semantica de contratos |
| **MALBO** (arXiv:2511.11788) | Bayesian Optimization para equipos multi-agente | Composicion optima de revisores de tesis |
| **GNN Link Prediction** (arXiv:2506.22165) | Prediccion de citas juridicas (+4.7%) | Red de precedentes para legal-doc |

## Consecuencias
- **Tests totales:** 2628 (+45 de calidad)
- **ADRs totales:** 25
- **Papers 2026 integrados:** 14 nuevos
- **Errores prevenidos:** Refinement types atrapan errores en desarrollo, no en produccion
- **Cobertura de propiedades:** Semantic Cache, Token Optimizer, Structured Output, Token Budget

> **DEPRECADO** � Este ADR ha sido integrado en ADRs posteriores.
> - ADR-0021: Contenido fusionado en [ADR-0028](adr0028-frontier-gaps-2026-v2.md)
> - ADR-0025: Contenido cubierto por [ADR-0036](adr0036-agentic-qa-pipeline-2026.md)
> - ADR-0026: Contenido fusionado en [ADR-0027](adr0027-agentic-governance-cx-2026.md)
> - Ver [SUMMARY.md](../SUMMARY.md) para la estructura actualizada.

## Deprecacion
**Fecha:** Julio 2026
**Razon:** Compactacion de ADRs para eliminar redundancia.
**Reemplazado por:** ADR-0028, ADR-0036, ADR-0027 respectivamente.
