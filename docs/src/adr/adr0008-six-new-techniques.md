# ADR-0008: Workflow Patterns + PBT Templates + Context Engineering

## Estado
**ACEPTADO** — Implementado en commit 152b99f.

## Contexto
AGENTIC implementa delegacion a especialistas, buenas practicas de codigo, ejecucion paralela y economia de tokens. Sin embargo, carece de:

1. **Workflow Patterns**: El TaskPlanner genera DAGs genericos sin patrones de flujo nombrados (Evaluator-Optimizer, Voting, Critique-Revise, Parallel-Transform).
2. **Property-Based Testing Templates**: No hay generacion automatica de invariantes desde templates con holes rellenables.
3. **Context Engineering**: No hay principios explicitos de como organizar el contexto inyectado.
4. **Behavioral Tracing**: No se registran las decisiones de los agentes (solo outputs).
5. **Architectural Guardrails**: No se valida que el codigo generado cumpla reglas arquitectonicas.
6. **Semantic Versioning**: Skills y agent prompts no tienen versionado trazable.

## Decision
Incorporar las 6 tecnicas como modulos independientes y principios en base_principles.md.

### 1. Workflow Patterns (WFP)
4 patrones atomicos en `harness/orchestrator/workflow_patterns.py`:
- **Evaluator-Optimizer**: generator_fn → evaluator_fn → loop hasta threshold
- **Voting**: N generator_fn → evaluator_fn rankea → mejor se entrega
- **Critique-Revise**: generator_fn → critic_fn → loop hasta sin criticas
- **Parallel-Transform**: N transform_fn → merge_fn fusiona

### 2. Property-Based Testing Templates (PBT)
Catalogo en `harness/orchestrator/pbt_templates.py`:
- 7 templates: sorting_stable, idempotent, pure_function, boundary, roundtrip, commutative, associative
- Cada template tiene holes `{nombre}` que el LLM rellena
- `suggest_templates()` hace matching por keywords en descripcion

### 3. Context Engineering (CEN)
Principios en context_injector.py y base_principles.md:
- **Least-Recent Context First**: Lo mas relevante al principio
- **Structured Chunking**: Bloques con metadatos (tipo, prioridad, tamano)
- **Progressive Disclosure**: Instruccion → Ejemplos → Datos de referencia

### 4. Behavioral Tracing (BTR)
Modulo `harness/orchestrator/behavioral_tracer.py`:
- Cada decision registra: action, chosen, alternatives, rationale, confidence
- Fingerprint SHA256 del comportamiento del agente
- Reportes de consistencia y auditoria por agente

### 5. Architectural Guardrails (AGR)
Modulo `harness/orchestrator/architectural_guardrails.py`:
- 4 guardrails builtin: type_hints, function_length, no_except_pass, forbidden_imports
- `check_all()` ejecuta todos los guardrails sobre codigo generado

### 6. Semantic Versioning (SVE)
Versionado MAJOR.MINOR.PATCH para skills y agent prompts:
- MAJOR: Cambio incompatible en comportamiento
- MINOR: Nueva funcionalidad backward-compatible
- PATCH: Correccion backward-compatible

## Archivos Creados
- `harness/orchestrator/workflow_patterns.py`: 4 patrones de flujo
- `harness/orchestrator/pbt_templates.py`: 7 templates PBT
- `harness/orchestrator/behavioral_tracer.py`: Trazabilidad de decisiones
- `harness/orchestrator/architectural_guardrails.py`: 4 guardrails

## Archivos Modificados
- `harness/memory_rag/context_injector.py`: +!WFP!+!PBT!+!CEN!+!BTR!+!AGR!+!SVE!
- `.opencode/core/base_principles.md`: +WFP+PBT+CEN+BTR+AGR+SVE en N1 y N2

## Tests
- `harness/tests/test_workflow_patterns.py`: 12 tests
- `harness/tests/test_pbt_templates.py`: 8 tests
- `harness/tests/test_behavioral_tracer.py`: 6 tests
- `harness/tests/test_architectural_guardrails.py`: 8 tests

## Consecuencias
- **Positivas**: Agentes usan patrones de flujo probados; PBT reduce alucinaciones 59%; contexto mejor organizado; decisiones auditables; codigo validado contra reglas; versionado trazable.
- **Negativas**: ~20 tokens extra en firma universal; 4 modulos nuevos que mantener; ~1-2s adicionales por validacion de guardrails.

## Referencias
- arXiv:2605.15425 — Runtime-Structured Task Decomposition (retry cost -51%)
- arXiv:2607.09072 — Agentic Proof and Property-Based Testing via Templates (-59% alucinaciones)
- arXiv:2606.16988 — Agent Trajectories as Programs (behavioral fingerprints 85.7%)
- arXiv:2606.25257 — How Devs Maintain Agent Instructions (ACF evolution)
- ADR-0006: Idempotencia
- ADR-0007: DocStrings + Error Readability
