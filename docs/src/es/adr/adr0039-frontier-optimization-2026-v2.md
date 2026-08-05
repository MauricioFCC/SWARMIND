# ADR-0039: Frontier Optimization 2026 v2 — Tokens, Agentes y Configuración

## Estado
**PARCIALMENTE IMPLEMENTADO (2026-08-04)** — Consulta web frontier realizada el
2026-08-04. 12+ fuentes verificadas por fetch directo (docs opencode 1.18, Anthropic
Engineering, arXiv 2026). Complementa ADR-0013, ADR-0014, ADR-0031. Aplicado vía
ADR-0040: H8 (compaction.prune + tool_output + mcp_timeout en opencode.json).
Pendiente: setCacheKey/provider options (requiere conocer providers), small_model +
steps por agente, plugin de compactación custom, routing adaptativo (Σ-Mem),
memoria gobernada (PatchBoard/MemClaw), stop rules (CONVOLVE).

## Contexto
SWARMIND tiene Token Economics v2026 implementado (Cache-Shape -38%, Structured
Compaction -41%, Scoped Context Spawn -44%, Failure-Spend Governance, PaCoRe, LTS
Shared Memory). La frontera 2026 confirma la tesis central: **el contexto es el
recurso finito y el context engineering la disciplina**. Tres hallazgos nuevos:

1. **Context rot es medible y mitigable**: agentes de código degradan 8/10 → 3/10 al
   pasar de 11K a 299K tokens (arXiv 2607.17937); monitores LLM fallan 2-30× con
   transcriptos >800K tokens (2605.12366). El contexto largo corrompe decisiones.
2. **Toda transformación de contexto invalida el KV-cache**: compaction/prune/spawn
   causan re-prefill costoso; SmoothAgent (2607.00151) reduce TTFT hasta 11.9×
   ejecutando transformaciones en lookahead. La disciplina de cache debe PROGRAMAR
   cuándo compactar/podar, no reaccionar.
3. **Sistemas multi-agente queman ~15× tokens vs chat** (Anthropic, producción):
   routing adaptativo + memoria gobernada son los dos levers con más evidencia
   (Σ-Mem; PatchBoard: 45.5K vs 368.3K tokens/tarea).

## Decisión e Implementación (recomendaciones priorizadas)

### 1. Tool-output pruning nativo (compaction.prune) — est. 15-25% input en sesiones largas
El "toque más liviano y seguro de compaction" (Anthropic): el resultado crudo de una
tool ya llamada no se necesita en el historial. A diferencia del compaction (invalida
KV-cache completo), el prune preserva el prefijo y mantiene la cache aprovechable.
```json
"compaction": { "auto": true, "prune": true, "reserved": 10000 }
```
Riesgo: una tool output puede re-necesitarse en debugging profundo → activar en
subagentes/long-horizon, verificar coherencia post-prune.

### 2. Cache-shape con setCacheKey + prefijo estable — est. 30-45% costo (providers con caching)
`provider.<id>.options.setCacheKey: true` (opencode 1.18) fuerza cache key. La
fórmula Effective-Input-Price de SWARMIND (inp × miss_ratio × price + out × price)
es exactamente lo que optimiza prompt caching: **un miss cuesta 2× (write+read)**.
Disciplina: ordenar system prompts como prefijo estable e inmutable (skills, reglas,
instructions primero; contenido volátil último). Reordenar skills entre sesiones
destruye el hit-ratio. Solo aplica a providers con prompt caching (no OSS local).

### 3. Compaction afinado + hook de plugin — est. 20-35% input en sesiones >200K
`compaction.reserved` (buffer anti-overflow) + plugin con hook
`experimental.session.compacting` para inyectar "contexto que debe persistir"
(estado de tarea, decisiones, archivos activos). SWARMIND ya tiene Structured
Compaction; el plugin formaliza la customización sin forkear opencode. ARC
(2601.12030): gestión activa/reflexiva supera a pasiva hasta +11% accuracy.

### 4. Subagentes con salida condensada + artefactos a filesystem — est. 40-60% tokens del líder
Patrón Anthropic multi-agent: cada subagente explora decenas de miles de tokens pero
retorna 1,000-2,000 condensados; escribe artefactos a filesystem y pasa referencias
livianas al coordinador. **Contra-evidencia**: Deep Agentic Search (2608.01507) —
41.8% de fallos ocurren en el hand-off planner→subagente (fallos silenciosos) y para
read-only el retrieval directo gana 65.2% vs 46.2% a menos de la mitad del costo.
⇒ SWARMIND debe VERIFICAR los resúmenes de subagente (checks estructurales) y no
delegar lo que un grep/retrieval resuelve.

### 5. small_model + steps + modelos baratos por agente — est. 10-20% costo total
`small_model` para títulos/resúmenes/compaction; `agent.<name>.model` barato para
subagentes exploratorios, frontier solo para líder/síntesis (patrón Opus+Sonnet).
`agent.<name>.steps: 5-10` corta loops infinitos (Failure-Spend Governance nativo).
Agentic Abstention (2606.28733): la mayoría de sistemas no sabe cuándo parar.

### 6. Routing adaptativo basado en confiabilidad (Σ-Mem) — evolución de LTS Shared Memory
Σ-Mem (2607.27958): memoria de confiabilidad online que registra evidencia de
competencia por agente y sirve para routing sin respuesta + votación ponderada;
supera a majority voting y al mejor peer fijo en OOD. SLMs as Multi-Agent Routers
(2608.00030): router pequeño SFT+RL, NDCG@10 0.918 vs 0.539 de LLM por intención,
120ms (-82.4% latencia). El routing por intención (routing_rules.yaml) es
fundamentalmente limitado: no ve el contenido recuperado.

### 7. Memoria compartida gobernada (PatchBoard / MemClaw / MAPLE-Guard)
PatchBoard (2605.29313): estado compartido por mutaciones JSON Patch validadas contra
schema: 84.6% éxito vs 30.8% LangGraph y 8× menos tokens. MemClaw (2606.24535):
4 modos de fallo del fleet-memory (leakage, stale propagation, contradiction,
provenance collapse) con primitivas: scoped retrieval, temporal supersession,
provenance tracking. MAPLE-Guard (2608.00426): la memoria compartida es un canal de
ataque durable; gates en write/retrieval/promoción bajan ASR 38.2% → 0.9%.

### 8. Stop rules / abstención explícita (CONVOLVE)
2606.28733: la abstención es decisión secuencial (responder/abstenerse/recopilar).
CONVOLVE destila trayectorias en reglas de parada reutilizables: recall oportuno
26.7 → 57.4 sin tocar parámetros. Complemento empírico del Failure-Spend Governance:
falta un detector de "seguir gastando no va a ayudar".

### 9. Configuración clave de provider (opencode.json)
```json
"provider": { "<id>": { "options": { "timeout": 600000, "chunkTimeout": 30000, "setCacheKey": true } } }
```
Timeout default 300s es insuficiente para reasoning largo; chunkTimeout aborta
streams muertos. Extra: `permission.task` (contención de qué subagentes puede
invocar cada agente, globs, última regla gana), `subagent_depth: 1-2`,
`attachment.image` (auto_resize 2000×2000, max_base64 5MB), `snapshot: false` en CI.

## Riesgos y límites
- **Prune**: tool outputs re-necesarios en debugging profundo (mitigación: solo
  long-horizon + verificación post-prune).
- **Caching**: miss cuesta 2×; prefijo inestable revierte el ahorro; TTLs cortos
  (5-60 min) en algunos providers requieren sesiones largas/batch.
- **Compaction agresivo pierde contexto sutil** (advertencia explícita Anthropic) +
  invalida KV-cache (SmoothAgent). Preferir prune sobre compact cuando sea posible.
- **Compresión de prompts de control**: CompressAgent (2608.01056) — 75% retención
  mantiene 92.7% éxito; colapsa bajo 50%. Compression Paradox (2603.23528):
  ahorro de input no garantiza ahorro total (expansión de output).
- **Subagentes**: 41.8% fallos silenciosos en hand-off; verificar outputs.
- **Routing adaptativo**: requiere feedback de correctitud; cold-start sin datos.
- **Modelos baratos**: degradan compaction/títulos en tareas finas; medir success-rate
  por agente/modelo antes de fijar defaults.

## Fuentes (verificadas 2026-08-04)
- https://opencode.ai/docs/config/ | https://opencode.ai/docs/agents/ | https://opencode.ai/docs/plugins/
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://www.anthropic.com/engineering/multi-agent-research-system
- arXiv: 2607.00151 (SmoothAgent), 2606.29718 (Context Rot), 2607.17937 (coding agents),
  2605.12366 (classifier rot), 2601.12030 (ARC), 2606.25656 (19-53% menos tokens),
  2608.01056 (CompressAgent), 2605.04426 (Telegraph English), 2603.23528 (Compression
  Paradox), 2608.01507 (Deep Agentic Search), 2607.27958 (Σ-Mem), 2608.00030 (SLM
  routers), 2607.25446 (Adaptive Org Routing), 2605.29313 (PatchBoard),
  2606.24535 (MemClaw), 2608.00426 (MAPLE-Guard), 2606.28733 (Agentic Abstention),
  2606.14445 (tap), 2411.04468 (Magentic-One), https://github.com/a2aproject/A2A
