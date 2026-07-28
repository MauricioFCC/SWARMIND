# Investigacion Aplicada — AGENTIC 2026

Tecnicas frontera 2026 investigadas e implementadas en el sistema multi-agente.

## Creative AI (ReDNA pipeline)
**Paper:** arXiv:2605.28465 (ReDNA) + arXiv:2604.18005 (Diversity Collapse)
**Implementacion:** CreativeWorktable con pipeline divergente/convergente

| Fase | Descripcion | Metodo |
|------|-------------|--------|
| Divergente | Agentes generan ideas libremente (independientes) | `CreativeWorktable.divergent_phase()` |
| Convergente | Ideas evaluadas por novedad (40%) + factibilidad (60%) | `CreativeWorktable.convergent_phase()` |
| Integracion | Top 3 ideas combinadas en propuesta final | `CreativeWorktable.integration_phase()` |

**Anti-Diversity Collapse:** Topologia sparse, rondas de generacion aislada, presion divergente 30%, penalizacion a autoridad 10%.

## Agent Capsules (-51% tokens)
**Paper:** arXiv:2605.00410
**Implementacion:** `harness/orchestrator/agent_capsules.py`

| Estrategia | Ahorro | Calidad |
|-----------|--------|---------|
| COMPOUND | -51% tokens | 0.85 quality floor |
| TWO_PHASE | -35% tokens | 0.92 quality floor |
| SEQUENTIAL | 0% (baseline) | 1.0 quality |

## Structured Output (-40% tokens)
**Paper:** arXiv:2604.12301 (Local-Splitter)
**Implementacion:** `harness/orchestrator/token_optimizer.py`

Reemplaza texto libre con JSON Schema tipado. Modos: JSON_SCHEMA (-40%), MARKDOWN (-20%), FREE_TEXT (baseline).

## DAG Pipeline Parallelism (1.5-2.4x speedup)
**Paper:** arXiv:2606.01533 (MACU) + arXiv:2604.15186 (Scepsy)
**Implementacion:** Algoritmo de Kahn en `token_optimizer.py`

Construye grafo de dependencias y ejecuta tareas independientes en paralelo.

## Knowledge Graph
**Paper:** arXiv:2605.27864 (FundaPod)
**Implementacion:** `harness/memory_rag/knowledge_graph.py`

Grafo local-first (NetworkX + JSON) que conecta: skills con agentes, ADRs con skills, decisiones con conceptos. Seed automatico desde skills_registry.yaml y ADRs.

## SecurityGuard
**Fuente:** OWASP Top 10 for LLMs 2025, OWASP Agentic AI Top 10
**Implementacion:** `harness/orchestrator/security_guard.py`

| Defensa | Descripcion |
|---------|-------------|
| Prompt Injection | 13 patrones de deteccion (ignore, jailbreak, system prompt reveal) |
| Secrets Detection | API keys, tokens AWS, claves privadas |
| Agent Boundaries | Builder no deploya, Guardian no bypass, Evolve no modifica prompts |
| Runtime Security | Comandos peligrosos (rm -rf), SSRF a metadata endpoints |

## Persistent Memory
**Inspiracion:** Engram (ASDT project)
**Implementacion:** `harness/memory_rag/persistent_memory.py`

Memoria cross-session en JSON local. Metodos: store(), recall(), get_session(), get_agent_memory().

## Epic Mode
**Inspiracion:** Traycer Epic mode
**Implementacion:** `EpicMode` en `worktable.py`

Workflow multi-paso: Plan -> Execute -> Review -> Iterate hasta completar. Max 3 iteraciones por defecto.

## Property-Based Testing
**Paper:** arXiv:2510.09907 (Agentic PBT, NeurIPS 2025)
**Implementacion:** `harness/tests/test_pbt_core.py` (20 tests de propiedad)

| Componente | Propiedades verificadas |
|-----------|----------------------|
| Semantic Cache | Roundtrip, idempotencia, monotonicidad hits+misses |
| Token Optimizer DAG | Sin ciclos, speedup >= 1.0, orden topologico |
| Structured Prompt | Formatos distinguibles, no vacio |
| Token Budget | Remaining no negativo, usage_pct <= 100% |

## Refinement Types
**Inspiracion:** Type-first development, Liquid Rust
**Implementacion:** Validaciones assert en AgentBus.post_message() y AsyncAgentBus

Canal no vacio, message_type valido, iteracion no negativa, timeout positivo. 25 tests de cobertura.

## Legal NLP
**Papers:** SaulLM-7B (2025), Arg-LLaDA, MiningLegalBench (2026), LegalSeg (NAACL 2025)
**Implementacion:** `harness/memory_rag/legal_analyzer.py`

| Capacidad | Tecnica |
|-----------|---------|
| NER juridico | Patrones para normas, cortes, cargos, fechas |
| Argument mining | Extrae ratio decidendi y obiter dicta |
| Clasificacion | 6 tipos: sentencia, demanda, contrato, concepto, norma |
| Comparacion | Por entidades compartidas entre documentos |

## Routing por Scoring Ponderado
**Implementacion:** `DelegationEngine.auto_route()` refactorizado

Keywords largas tienen mas peso que cortas (evita falsos positivos). Dos niveles: frases completas (alto peso) + palabras individuales (bajo peso). Bilinguie espanol/ingles.

## Metricas del Sistema

| Componente | Test | Estado |
|-----------|------|--------|
| Tests totales | 2,628 | ✅ |
| Skills | 29 (100% minificados) | ✅ |
| ADRs | 25 | ✅ |
| Proyectos | 6 activos | ✅ |
| GPU | RTX 4060 8GB | ✅ |
| Token savings | -51% capsulas, -40% structured output | ✅ |
