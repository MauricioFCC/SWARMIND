# ADR 0073: Quality/Latency/Tokens Frontera — Votación k-en-1, Session-Affinity y Structured Enforcer

## Estado
Aplicado | `harness/orchestrator/batch_vote.py` + `harness/model_router/session_affinity.py` + `harness/orchestrator/structured_enforcer.py` | Propietario: @coordinator | Fecha: 2026-09-07

## Contexto
Research frontera (sep-2026, 2 tracks: OpenAI/AGI + cost-latency production) sobre calidad de salida, velocidad y ahorro de tokens:

1. **Votación barata** (arXiv 2604.13717): usar el parámetro `n` de la API para k completos cobra el INPUT **una vez** (vs k llamadas = input k×); criteria+ensembling suma +11.9pp de calidad. El voting del orquestador (`parallel_executor`, `DEFAULT_VOTE_N=3`) pagaba input 3×.
2. **Session-affinity routing** (vLLM SAAR): memoria de sesión owned por el router evita switches de modelo: **−79% switches, −78.7% costo**; cada switch pierde cache de prefijo y re-paga prefill.
3. **Structured outputs**: 99.9% adherencia a schema vs <70% sin constraint (**30× menos fallos de parse**); sin schema, 300K+ respuestas malformadas por 1M requests.
4. **Latencia calibrada, no minimizada** (ACM 3772318.3790716): esperas 2s se perciben MENOS thoughtful que 9-20s (se leen como deliberación); delays largos erosionan confianza → en fan-in humano, signal de fase, no respuesta instantánea.
5. **Stacking** (getmaxim/Bifrost): cache+routing+compaction compone a 50-70% total; métrica reina: costo por tarea.
6. **Inferencia local 2026**: MLA −4-6× KV, MTP/self-speculation nativo, FP4 2-4× throughput, INT4 95-99% calidad retenida, prefix caching L7 (hit 35%→70%, TTFT −35%).

IDP verificado: semantic cache ya existe (`semantic_cache.py`), fallback chains ya existen (`provider_executors`), prefix cache ya existe (`prompt_cache_builder.py`) — no reimplementar.

## Decisión
Tres deltas TDD (21 tests):

1. **`batch_vote`** (`harness/orchestrator/batch_vote.py`): votación k-en-1 — `complete_fn(prompt, n=k)`; input cobrado 1× (`effective_input_tokens=input_tokens`), output k×; fallback automático a k llamadas si el proveedor no soporta n>1 (`input_calls=k`); mayoría con quorum (empate → None); `estimate_savings(k)` = (k-1)/k. Mutante M-n-check verificado muerto.
2. **`session_affinity`** (`harness/model_router/session_affinity.py`): tier sticky por `session_id` con TTL (default 1800s, renovable en cada uso), evict por `max_sessions`, metrica `switches_avoided`; decide_fn inyectable (alineado con `CascadeRouter`/`ComplexityRouter`).
3. **`structured_enforcer`** (`harness/orchestrator/structured_enforcer.py`): valida JSON schema simplificado (type/required/properties/minimum); extrae JSON de fences markdown; re-ask con feedback del error concreto (nombra el campo); `StructuredEnforcementError` accionable tras agotar retries.

## Consecuencias
### Positivas
- Votación del gate ≥70 cuesta k× menos input (con proveedores que soportan n).
- Switches de modelo evitados = prefijos cacheados viven más (sinergia con ADR-0066/0068).
- Salidas machine-readable con 30× menos fallos de parse; retries con feedback (no ciego).
- Métrica `switches_avoided` auditable (SAAR-style).

### Negativas
- `structured_enforcer` valida un subset de JSON schema (type/required/properties/minimum) — sin dep externa (jsonschema); ampliar solo si hay caso.
- session_affinity fija tier por sesión: una tarea compleja en sesión "small" no escala (mitigable vía escape_hatch de CascadeRouter).

## Alternatives Considered
1. **k llamadas (status quo)**: input k× — contradice TKN.
2. **jsonschema lib**: dep extra para validación minima; YAGNI hasta necesidad.
3. **Afinidad por agente en vez de por sesión**: rompe el patrón SAAR (la sesión es la unidad de cache).

## Relacionado
- ADR-0066 (prompt-cache TTL), ADR-0068 (cascada STEER), ADR-0065-0072
- arXiv 2604.13717, vLLM SAAR, getmaxim 2026, ACM 3772318.3790716
