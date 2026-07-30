# ADR-0037: AI Factory Stack — Integracion Completa 7-Capas

## Estado
**ACEPTADO** — Implementado y verificado (14 tests).

## Contexto
La mayoria de equipos AI cree que construir sistemas AI es elegir el mejor LLM.
En realidad, las aplicaciones AI modernas combinan 7 capas que trabajan juntas.
AGENTIC necesitaba integrar formalmente todas las capas del AI Factory Stack
en un unico orquestador.

## AI Factory Stack 7-Capas

```
LLM → Thinks
RAG → Retrieves
Vector Database → Remembers
AI Agent → Acts
MCP → Connects
Guardrails → Protect
Evals → Improve
```

## Implementacion en AGENTIC

### Gap Analysis: Antes vs Despues

| Capa | Antes | Despues |
|------|-------|---------|
| **LLM** (Intelligence) | ✅ Multiple modelos | ✅ Igual |
| **RAG** (Knowledge) | ✅ StrategicMemory | ✅ Igual |
| **VectorDB** (Knowledge) | ✅ LanceDB+Chroma+Qdrant | ✅ +Federated+SQLite-vec |
| **AI Agent** (Execution) | ✅ 20 agentes | ✅ +PipelineMACU |
| **MCP** (Integration) | ⚠️ MCPExecutor basico | ✅ MCPManager completo |
| **Guardrails** (Trust) | ❌ No existia | **✅ 5-capas** |
| **Evals** (Trust) | ❌ No existia | **✅ 7-capas** |

### 1. Guardrails System (Trust Layer) — NUEVO
5 capas de proteccion:

| Capa | Reglas | Accion |
|------|--------|--------|
| Input | anti_prompt_injection, max_length, toxicity | BLOCK/FLAG |
| Output | anti_code_injection, anti_pii_leak, max_length | REWRITE/FLAG |
| Content | anti_pii_leak, anti_code_injection, toxicity | BLOCK/FLAG |
| Tool | tool_allowlist + ToolGuardian (arXiv:2607.21835) | BLOCK |
| Policy | governance_constraints + GovernanceGuard | BLOCK |

Verdictos: PASS, BLOCK, FLAG, REWRITE
Archivo: `harness/guardrails/` (1,355 lines, 3 archivos)

### 2. Eval Framework (Trust Layer) — NUEVO
7 dimensiones de evaluacion con 14 funciones builtin:

| Dimension | Evals |
|-----------|-------|
| LLM | accuracy, latency (P50/P95/P99), cost |
| RAG | recall@k, faithfulness |
| VectorDB | recall@k, latency |
| Agent | completion rate, tool usage |
| MCP | availability |
| Guardrails | detection rate, false positive |
| Integration | e2e latency, success rate |

Arquitectura: EvalSuite → EvalReport → EvalDiff → Recommendations
Archivo: `harness/evals/` (1,389 lines, 3 archivos)

### 3. AIFactory Orchestrator — NUEVO
Pipeline integrado 7-capas:

```
Input → Guardrail(Input) → LLM → RAG/VectorDB → Agent → MCP → Guardrail(Output) → Output
                                        ^                                    |
                                        |________Evals_______________________|
```

10 estados: IDLE, PROCESSING, GUARDRAIL_BLOCKED, LLM_CALL, RAG_RETRIEVAL,
AGENT_EXECUTION, MCP_CALL, COMPLETED, FAILED, COMPENSATED

Archivo: `harness/aifactory/` (1,270 lines, 2 archivos)

## Consecuencias
- AGENTIC ahora cubre las 7 capas del AI Factory Stack
- Guardrails protegen contra prompt injection, PII leak, codigo malicioso
- Evals permiten mejora continua basada en datos
- AIFactory orquesta todo en un pipeline unificado
- 14 tests nuevos (todos pasando)

## Archivos creados
- `harness/guardrails/__init__.py` + `guardrail_engine.py` + `builtin_rules.py`
- `harness/evals/__init__.py` + `eval_factory.py` + `builtin_evals.py`
- `harness/aifactory/__init__.py` + `factory.py`
- `harness/tests/test_aifactory_stack.py` (14 tests)

## Referencias
- AI Factory Stack: LLM + RAG + VectorDB + Agent + MCP + Guardrails + Evals
- arXiv:2607.21835 — ToolGuardian
- ADR-0036: Agentic QA Pipeline 5-Capas
