# ADR-0033: TDD + Agentes como Fuente Unica de Verdad — Spec-First, Code-Second

## Estado
**ACEPTADO** — Implementado Julio 2026.

## Contexto

El plan maestro `docs/research/TDD + Agentes como Fuente Unica de Verdad.txt`
define la transformacion de Swarmind de enjambre experimental a **SDLC autonomo,
gobernado y matematicamente verificable**: el humano deja de revisar codigo y solo
aprueba especificaciones. Los tests son la ley; el codigo generado por el agente es
un detalle de implementacion desechable (Uncle Bob, "Spec-First, Code-Second").

Para cubrir los gaps del plan se investigaron dos repositorios frontier 2026:

1. **OmniRoute** (diegosouzapw/OmniRoute, 36.1K estrellas): AI Gateway con 19
   estrategias de routing, scoring multi-factor con pesos validados (suma=1.0),
   resiliencia de 3 scopes (circuit breaker por proveedor / cooldown por conexion /
   lockout por tripla con success-decay), virtual factory, admission control,
   fusion con quorum, y ~50 quality gates anti-alucinacion.
2. **Headroom** (headroomlabs-ai/headroom, 63.6K estrellas): capa de compresion de
   contexto con **CCR reversible** (Compress-Cache-Retrieve: el original siempre es
   recuperable via tool), Success-Correlation (aprende del fallo→exito, no cataloga
   fallos), escritura marcada e idempotente (`<!-- headroom:learn:start/end -->`),
   CacheAligner (estabiliza prefijo para KV-cache), effort routing y evals de
   preservacion de accuracy.

Mas 12 busquedas web sobre el estado del arte 2026 (papers arXiv:2604.26615,
2603.17973, 2602.00180; practicas de Anthropic, GitHub Spec Kit, Meta ACH,
Atlassian, Sonar, Halyard, SurePrompts) que confirman:
- El test que falla es el unico contrato que un agente no puede falsear.
- "Tests Beat Instructions": la suite de tests es el unico archivo de instrucciones
  que el agente no puede malinterpretar (Caimito, 2026).
- Builder-Validator con separacion de herramientas (el validador es read-only).
- Feedback externo, nunca auto-review (Huang et al., ICLR 2024).
- Contexto sobre procedimiento (TDAD: el mapa codigo→tests supera al manual TDD).
- Coverage diferencial + mutation como gate de verdad (la cobertura miente).
- AGENTS.md canonico y portatil como SSOT de configuracion (Linux Foundation).

## Decision

### 1. Nuevo flujo de trabajo TDD estricto (`tdd_strict`)

Se implementa `harness/orchestrator/workflows/tdd_strict.py` con un DAG que
**bloquea la escritura en `src/` hasta que los tests sean auditados y aprobados**:

```
NIVEL 0 (Spec): scientist define invariantes + tests PBT (Hypothesis);
                guardian audita exhaustividad y casos borde.
NIVEL 1 (Green): builder implementa hasta que los tests pasen;
                 guardian ejecuta mutation testing.
NIVEL 2 (Confianza): coordinator genera Test Confidence Report (sin mostrar codigo).
```

Reglas de oro por fase (SurePrompts "tres prohibiciones"):
- **RED**: prohibido implementar; el unico trabajo es el test que falla correctamente.
- **GREEN**: prohibido tocar el test; solo implementacion minima.
- **REFACTOR**: prohibido cambiar comportamiento; solo la cualidad nombrada.

### 2. Decision Trace obligatorio (`X-Swarmind-Decision`)

Cada salto del AgentBus registra `{strategy, agent, provider, latency_ms, score}`
(espejo de `X-OmniRoute-Decision`). Sin trazabilidad no hay auditoria ni evals de
routing. Se implementa `harness/orchestrator/decision_trace.py`.

### 3. Resiliencia de 3 scopes (OmniRoute)

Se extiende Failure Governance con:
- **Cooldown por conexion/instancia** con backoff exponencial ×2 y guard
  anti-thundering-herd.
- **Lockout por tripla** (recurso+agente+modelo) con **success-decay**: cada exito
  divide el contador de fallos a la mitad (`failure_count = floor(f/2)`); a 0 se
  borra el lockout.
- **HALF_OPEN con probe lazy** (sin timers de fondo).
- Estados terminales (ban/degraded) separados de cooldowns transitorios.

Se implementa `harness/orchestrator/resilience_governance.py`.

### 4. CCR reversible (Headroom)

`structured_compact()` devuelve `(texto_compacto, hash, original_cacheado)` y se
registra `swarmind_retrieve(hash, query)` con busqueda BM25 sobre el original.
La compactacion deja de ser destructiva: nada se pierde jamas. Se implementa
`harness/memory_rag/reversible_compaction.py`.

### 5. Success-Correlation Engine (Headroom learn)

El feedback loop del Circuit Breaker no solo registra fallos: correlaciona
**fallo → exito** en el trace de la sesion y extrae lecciones accionables en 5
categorias (Environment Facts, File Path Corrections, Search Scope, Command
Patterns, Known Large Files), escritas con marcadores idempotentes
`<!-- swarmind:learn:start/end -->` en el contexto de futuros agentes.

Se implementa `harness/orchestrator/success_correlation.py`.

### 6. Gobernanza y economia de tokens

- El `builder` tiene permiso de escritura en `src/`, cero permiso para deploy/env.
- Auditoria inmutable en el WriteAheadLog con justificacion.
- Deteccion de loops: 3 llamadas identicas → matar proceso y escalar al humano.

## Gaps cubiertos (mapeo OmniRoute + Headroom)

| Gap | Fuente | Solucion |
|---|---|---|
| Compaction irreversible | Headroom CCR | Retrieve con BM25 + hash |
| Feedback loop sin success-correlation | Headroom learn | Fallo→exito→leccion accionable |
| Escritura no idempotente de contexto | Headroom markers | `<!-- swarmind:learn:start/end -->` |
| Routing heuristico binario | OmniRoute scoring | Multi-factor con pesos validados |
| Un solo circuit breaker | OmniRoute 3 scopes | Cooldown + lockout + success-decay |
| Sin trazabilidad de decisiones | OmniRoute headers | `X-Swarmind-Decision` |
| Tests que confirman lo que el codigo hace | Estado del arte 2026 | Gates: diff-cover + mutation + PBT |

## Consecuencias

**Positivas:**
- El humano pasa de "escritor de sintaxis" a "arquitecto de especificaciones".
- Cobertura 3561 tests (3514 previos + 47 de Fases 3.1/3.2/3.3); nueva superficie
  TDD/CCR/resiliencia/evaluacion testeable con pytest.
- Ahorro de tokens: compaction reversible + effort routing + CacheAligner.

**Negativas:**
- Costo de infraestructura: cache de originales CCR (SQLite/hash-indexed).
- El flujo TDD estricto aumenta latencia por nivel (auditoria previa a escritura).
- El success-correlation requiere trazas de sesion persistentes (WAL ya existe).

**Riesgos:**
- Headroom es Apache 2.0, OmniRoute MIT: se portan **conceptos**, no codigo
  (sin friccion legal).
- La compresion de codigo debe respetar safety gates (nunca comprimir codigo
  reciente ni contexto de analisis) o rompe el TDD (el builder necesita el codigo).

## Archivos

- `harness/orchestrator/workflows/tdd_strict.py` — DAG TDD estricto + Test Confidence Report
- `harness/orchestrator/decision_trace.py` — Decision Trace (X-Swarmind-Decision)
- `harness/orchestrator/resilience_governance.py` — 3 scopes + success-decay
- `harness/memory_rag/reversible_compaction.py` — CCR (Compress-Cache-Retrieve)
- `harness/orchestrator/success_correlation.py` — fallo→exito→leccion accionable
- `harness/orchestrator/trajectory_evaluator.py` — Agentic Trajectory Evaluator
  (plan maestro Fase 3.1: LLM-as-a-Judge sobre el DAG, deteccion de redundancia
  y sobre-delegacion, veredictos OPTIMAL/ACCEPTABLE/INEFFICIENT)
- `harness/orchestrator/red_teamer.py` — Automated Red-Teaming (Fase 3.2:
  15 vectores adversariales en 4 categorias, bloqueo de deploy con
  HIGH/CRITICAL, generacion de test PBT por vector explotado)
- `harness/orchestrator/continuous_verifier.py` — Continuous Verification
  post-deploy (Fase 3.3: ventana de 30 min, umbral 5%, rollback automatico
  al commit anterior + log para evolve-analyzer)
- `.opencode/agents/builder.md`, `.opencode/agents/guardian.md` — reglas de oro TDD

## Referencias

- Plan maestro: `docs/research/TDD + Agentes como Fuente Unica de Verdad.txt`
- OmniRoute: https://github.com/diegosouzapw/OmniRoute
- Headroom: https://github.com/headroomlabs-ai/headroom
- TDD Governance for Multi-Agent Code Generation: https://arxiv.org/abs/2604.26615
- TDAD (grafo codigo→tests): https://arxiv.org/html/2603.17973v1
- Spec-Driven Development: https://arxiv.org/html/2602.00180v1
- Tests Beat Instructions (Caimito): https://www.caimito.net/en/blog/2026/04/17/tests-beat-instructions-for-ai-coding-agents.html
- Builder-Validator: https://pilot-shell.com/blog/team-orchestration
- GitHub Spec Kit: https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/
