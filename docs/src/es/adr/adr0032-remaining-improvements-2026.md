# ADR-0032: Remaining Improvements — Shared Cache, Event Bus, Spec Decoding, KV Cache, A2A

## Estado
**ACEPTADO** — Implementado Julio 2026.

## Contexto
Analisis DOFA identifico 5 mejoras prioritarias para completar el stack de Swarmind. Investigacion web frontier (15+ papers) confirmo las tecnicas optimas.

## Mejoras Implementadas

### 1. SharedSemanticCache (ROI: Alto)
Cache semantico compartido entre agentes con LRU+TTL+embedding.
- **Hit rate tracking**: Metricas de acierto/fallo por agente
- **Eviccion inteligente**: LRU + expiracion por TTL
- **Busqueda por similitud**: Embedding + cosine similarity > threshold
- **Thread-safe**: RLock para acceso concurrente

**Archivo:** `harness/memory_rag/shared_cache.py`
**Tests:** 6 tests

### 2. EventBus Pub/Sub (ROI: Alto)
Comunicacion asincrona entre agentes mediante eventos.
- **Canales tematicos**: `task:complete`, `agent:online`, etc.
- **Wildcards**: `task:*`, `agent:*`, `*`
- **4 prioridades**: CRITICAL > HIGH > NORMAL > LOW
- **Filtros**: Por funcion, por agente, max eventos

**Archivo:** `harness/orchestrator/event_bus.py`
**Tests:** 6 tests

### 3. SpeculativeDecoder (ROI: Alto)
Decodificacion especulativa para acelerar generacion LLM.
- **Arquitectura drafter+verifier**: Modelo pequeno propone, grande verifica
- **4 estrategias**: EXACT_MATCH, SEMANTIC, PROBABILITY, HYBRID
- **Configurable**: n_draft, max_iterations, temperature, top_k
- **Metricas**: acceptance_rate, time_saved, tokens_drafted/accepted

**Basado en:** FailFast (Pan et al., NeurIPS 2025), DEER (Cheng et al., 2025)
**Archivo:** `harness/orchestrator/speculative_decoder.py`
**Tests:** 3 tests

### 4. KVCacheSharing (ROI: Medio)
Cache compartido de KV entre agentes secuenciales.
- **Busqueda exacta**: Reuso de cache identico
- **Busqueda por prefijo**: Reuso parcial para prompts similares
- **LRU eviction**: Mantiene capacidad limitada
- **Estimacion de memoria**: Bytes ahorrados por reuso

**Basado en:** Q-KVComm (Kriuk & Ng, 2025), G-KV (Liao et al., 2025)
**Archivo:** `harness/memory_rag/kv_cache_sharing.py`
**Tests:** 4 tests

### 5. A2AProtocol (ROI: Medio)
Protocolo estandarizado de comunicacion entre agentes.
- **5 capas**: Discovery, Message, Tool, Orchestration, Security
- **Roles**: COORDINATOR, WORKER, SPECIALIST, GATEWAY, MONITOR
- **Mensajes tipados**: TASK_REQUEST, DISCOVERY, TOOL_CALL, etc.
- **Handlers**: Registro de callbacks por tipo de mensaje

**Basado en:** A2A v1.0 (Google/Linux Foundation), EACP (Liu et al., 2026)
**Archivo:** `harness/orchestrator/a2a_protocol.py`
**Tests:** 4 tests

## Resultados

| Mejora | Tests | Lines | Papers |
|--------|-------|-------|--------|
| SharedSemanticCache | 6 | 225 | ShapedCache |
| EventBus | 6 | 310 | MACU, Helium |
| SpeculativeDecoder | 3 | 255 | FailFast, DEER, FLy |
| KVCacheSharing | 4 | 220 | Q-KVComm, G-KV |
| A2AProtocol | 4 | 285 | A2A, EACP, AMACP |
| **Total** | **23** | **~1,295** | **8 papers** |

### Papers Frontier Aplicados (total: 26)
| Paper | Implementacion |
|-------|---------------|
| FailFast (Pan et al., 2025) | SpeculativeDecoder |
| DEER (Cheng et al., 2025) | SpeculativeDecoder |
| FLy (Li et al., ICLR 2026) | SpeculativeDecoder |
| Q-KVComm (Kriuk & Ng, 2025) | KVCacheSharing |
| G-KV (Liao et al., 2025) | KVCacheSharing |
| A2A v1.0 (Google/LF) | A2AProtocol |
| EACP (Liu et al., 2026) | A2AProtocol |
| AMACP (Wu et al., 2026) | A2AProtocol |

## Referencias
- ADR-0031: Frontier Improvements 2026 — Multi-API, Prompt Compression, GoT
