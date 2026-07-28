# Investigación Aplicada — AGENTIC 2026

Técnicas frontera 2026 investigadas e implementadas en el sistema multi-agente.

## Creative AI (ReDNA pipeline)
**Paper:** arXiv:2605.28465 (ReDNA) + arXiv:2604.18005 (Diversity Collapse)
**Implementación:** CreativeWorktable con pipeline divergente/convergente

| Fase | Descripción | Método |
|------|-------------|--------|
| Divergente | Agentes generan ideas libremente (independientes) | `CreativeWorktable.divergent_phase()` |
| Convergente | Ideas evaluadas por novedad (40%) + factibilidad (60%) | `CreativeWorktable.convergent_phase()` |
| Integración | Top 3 ideas combinadas en propuesta final | `CreativeWorktable.integration_phase()` |

**Anti-Diversity Collapse:** Topología sparse, rondas de generación aislada, presión divergente 30%, penalización a autoridad 10%.

## Agent Capsules (-51% tokens)
**Paper:** arXiv:2605.00410
**Implementación:** `harness/orchestrator/agent_capsules.py`

| Estrategia | Ahorro | Calidad |
|-----------|--------|---------|
| COMPOUND | -51% tokens | 0.85 quality floor |
| TWO_PHASE | -35% tokens | 0.92 quality floor |
| SEQUENTIAL | 0% (baseline) | 1.0 quality |

## Structured Output (-40% tokens)
**Paper:** arXiv:2604.12301 (Local-Splitter)
**Implementación:** `harness/orchestrator/token_optimizer.py`

Reemplaza texto libre con JSON Schema tipado. Modos: JSON_SCHEMA (-40%), MARKDOWN (-20%), FREE_TEXT (baseline).

## DAG Pipeline Parallelism (1.5-2.4x speedup)
**Paper:** arXiv:2606.01533 (MACU) + arXiv:2604.15186 (Scepsy)
**Implementación:** Algoritmo de Kahn en `token_optimizer.py`

Construye grafo de dependencias y ejecuta tareas independientes en paralelo.

## Knowledge Graph
**Paper:** arXiv:2605.27864 (FundaPod)
**Implementación:** `harness/memory_rag/knowledge_graph.py`

Grafo local-first (NetworkX + JSON) que conecta: skills con agentes, ADRs con skills, decisiones con conceptos. Seed automático desde skills_registry.yaml y ADRs.

## SecurityGuard
**Fuente:** OWASP Top 10 for LLMs 2025, OWASP Agentic AI Top 10
**Implementación:** `harness/orchestrator/security_guard.py`

| Defensa | Descripción |
|---------|-------------|
| Prompt Injection | 13 patrones de detección (ignore, jailbreak, system prompt reveal) |
| Secrets Detection | API keys, tokens AWS, claves privadas |
| Agent Boundaries | Builder no deploya, Guardian no bypass, Evolve no modifica prompts |
| Runtime Security | Comandos peligrosos (rm -rf), SSRF a metadata endpoints |

## Persistent Memory
**Inspiración:** Engram (ASDT project)
**Implementación:** `harness/memory_rag/persistent_memory.py`

Memoria cross-session en JSON local. Métodos: store(), recall(), get_session(), get_agent_memory().

## Epic Mode
**Inspiración:** Traycer Epic mode
**Implementación:** `EpicMode` en `worktable.py`

Workflow multi-paso: Plan -> Execute -> Review -> Iterate hasta completar. Max 3 iteraciones por defecto.

## Property-Based Testing
**Paper:** arXiv:2510.09907 (Agentic PBT, NeurIPS 2025)
**Implementación:** `harness/tests/test_pbt_core.py` (20 tests de propiedad) + Hypothesis en toda la suite

| Componente | Propiedades verificadas |
|-----------|----------------------|
| Semantic Cache | Roundtrip, idempotencia, monotonicidad hits+misses |
| Token Optimizer DAG | Sin ciclos, speedup >= 1.0, orden topológico |
| Structured Prompt | Formatos distinguibles, no vacío |
| Token Budget | Remaining no negativo, usage_pct <= 100% |
| Vector Store | Resultados <= top_k, IDs únicos, scores ordenados |
| Agent Capsules | Ahorro >= 0%, calidad >= floor configurado |

## Refinement Types
**Inspiración:** Type-first development, Liquid Rust
**Implementación:** Validaciones assert en AgentBus.post_message() y AsyncAgentBus

Canal no vacío, message_type válido, iteración no negativa, timeout positivo. 25+ tests de cobertura.

## Legal NLP
**Papers:** SaulLM-7B (2025), Arg-LLaDA, MiningLegalBench (2026), LegalSeg (NAACL 2025)
**Implementación:** `harness/memory_rag/legal_analyzer.py`

| Capacidad | Técnica |
|-----------|---------|
| NER jurídico | Patrones para normas, cortes, cargos, fechas |
| Argument mining | Extrae ratio decidendi y obiter dicta |
| Clasificación | 6 tipos: sentencia, demanda, contrato, concepto, norma |
| Comparación | Por entidades compartidas entre documentos |

## Routing por Scoring Ponderado
**Implementación:** `DelegationEngine.auto_route()` refactorizado

Keywords largas tienen más peso que cortas (evita falsos positivos). Dos niveles: frases completas (alto peso) + palabras individuales (bajo peso). Bilingüe español/inglés.

## GovernanceAgent (ADR-0027)
**Implementación:** `harness/orchestrator/governance_agent.py`

| Capacidad | Descripción |
|-----------|-------------|
| Políticas de gobernanza | Reglas de compliance aplicadas a decisiones multi-agente |
| Auditoría | Trazabilidad de decisiones con metadata de governance |
| Validación de acciones | Verificación contra políticas antes de ejecución |
| Reportes | Generación de reportes de cumplimiento por agente y operación |

## AgentCostController
**Implementación:** `harness/orchestrator/agent_cost_controller.py`

| Capacidad | Descripción |
|-----------|-------------|
| Detección de loops | Monitoreo de ciclos de ejecución con timeout configurable |
| Control de costos | Límite de tokens por agente y por operación |
| Circuit breaker | Corte automático al superar umbrales de costo/iteración |
| Reporte de uso | Estadísticas de consumo por agente y sesión |

## BusinessContext
**Implementación:** `harness/orchestrator/business_context.py`

| Capacidad | Descripción |
|-----------|-------------|
| Glosario de términos | Diccionario de términos de negocio con definiciones y sinónimos |
| Contexto semántico | Resolución de ambigüedades terminológicas entre agentes |
| Herencia de contexto | Propagación de contexto entre sesiones y operaciones |
| Validación semántica | Verificación de consistencia terminológica en decisiones |

## OpenTelemetry Agent
**Implementación:** `harness/observability/opentelemetry_agent.py`

| Capacidad | Descripción |
|-----------|-------------|
| Trazabilidad distribuida | Spans por operación de agente con contexto padre-hijo |
| Métricas | Contadores de operaciones, duración, errores por agente |
| Exportación OTLP | Envío a collector OpenTelemetry o backend compatible |
| Atributos semánticos | Tags de agente, operación, estado, duración |

## AgentBenchmark
**Implementación:** `harness/orchestrator/agent_benchmark.py`

| Métrica | Descripción |
|---------|-------------|
| Accuracy | Precisión de respuestas del agente contra ground truth |
| Latencia | Tiempo de respuesta promedio por operación |
| Uso de tokens | Consumo de tokens por tarea y por agente |
| Tasa de éxito | Proporción de tareas completadas sin errores |

## VectorStoreAdapter
**Implementación:** `harness/memory_rag/vector_store_adapter.py`

| Backend | Estado |
|---------|--------|
| LanceDB | Producción (implementación completa) |
| Chroma | Soporte experimental |
| Qdrant | Soporte experimental |

**API unificada:** create_collection, add, search, delete, list_tables, clear — independientemente del backend subyacente.

## Métricas del Sistema

| Componente | Test | Estado |
|-----------|------|--------|
| Tests totales | 2,900+ | ✅ |
| Skills | 30 (100% SKILL.md + SKILL.min.md) | ✅ |
| ADRs | 27 | ✅ |
| Proyectos | 6 activos | ✅ |
| GPU | RTX 4060 8GB (6x search, 3.2x embedding) | ✅ |
| Token savings | -51% cápsulas, -40% structured output | ✅ |
| Vector stores | 3 (LanceDB, Chroma, Qdrant) | ✅ |
| Observabilidad | OpenTelemetry (trazas, métricas, OTLP) | ✅ |
| Benchmarks | AgentBenchmark (4 métricas) | ✅ |
