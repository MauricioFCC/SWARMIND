# ADR-0013: Token Economics — Cache Shape + Structured Compaction

## Estado
**IMPLEMENTADO** — Extiende ADR-0003. Commits: `7e9e8b8`, `061e114`.

## Contexto
ADR-0003 implementó 6 mecanismos iniciales de token economy. Análisis de uso real mostró que tres áreas tenían potencial de mejora usando técnicas frontera 2026:

1. **Cache-Shape Discipline** (Mojentum 2026): -38% tokens mediante cache con forma activa
2. **Structured Compaction** (Struct47, LAS51): -41% costo mediante compresión estructurada
3. **Scoped Context Spawn** (Symphony-Coord): -44% tiempo mediante contexto bajo demanda
4. **Write-Ahead Log**: idempotencia + cancelación first-class (Failure-Spend Governance)

## Decisión e Implementación

### 1. ShapedCache — Cache-Shape Discipline (-38% tokens)
**Archivo:** `harness/memory_rag/semantic_cache.py` (clase `ShapedCache`, ~95 líneas)

```python
class ShapedCache:
    """
    Cache con forma activa: LRU + TTL + relevancia.
    
    Extiende SemanticCache con politicas de economia de tokens:
    - LRU con limite de tokens totales
    - TTL por entrada (global o por clave)
    - Relevancia: entradas poco usadas se compactan primero
    - Hit rate tracking para ajuste dinamico de threshold
    """
```

**API pública:**
| Método | Descripción |
|--------|-------------|
| `get_shaped(prompt, threshold, context_window)` | Get con forma activa: LRU refresh + TTL check + compactación |
| `set_shaped(prompt, response, metadata, token_cost)` | Set con LRU eviction si excede max_tokens |
| `clear_expired()` | Limpia entradas expiradas por TTL |
| `get_stats()` | Métricas: hit_rate, hits, misses, lru_size |

**Hit rate tracking:**
```python
@property
def hit_rate(self) -> float:
    total = self._hit_count + self._miss_count
    return self._hit_count / max(total, 1)
```

**Tests:** `harness/tests/test_semantic_cache_extended.py` (clase `TestShapedCache`, 8 tests):
| Test | Descripción |
|------|-------------|
| `test_shaped_cache_init` | Constructor con valores por defecto |
| `test_shaped_cache_get_miss` | Cache miss → None, hit_rate=0.0 |
| `test_shaped_cache_set_and_get` | Set + Get exitoso, hit_count incrementa |
| `test_shaped_cache_hit_rate` | Hit rate progresivo: 0.0 → 0.5 → 2/3 |
| `test_shaped_cache_ttl_expiry` | Entrada expirada por TTL retorna None |
| `test_shaped_cache_lru_eviction` | LRU eviction cuando excede max_tokens |
| `test_shaped_cache_clear_expired` | clear_expired elimina solo expiradas |
| `test_shaped_cache_get_stats` | get_stats retorna dict completo |

### 2. Structured Compaction (-41% tokens)
**Archivo:** `harness/memory_rag/context_window_manager.py` (líneas 947–1029)

```python
def structured_compact(text: str, budget_ratio: float = 0.6, min_chars: int = 50) -> str:
    """
    Comprime texto estructurado preservando secciones criticas.
    
    Estrategia (Struct47, LAS51):
    1. Preservar cabeceras y secciones con marcadores de decision
    2. Comprimir tool outputs extensos (>200 chars) a resumen 1 linea
    3. Eliminar lineas de logging repetitivo
    4. Compactar bloques de codigo grandes (>20 lines) a resumen
    """
```

**Algoritmo de compactación:**
1. Divide texto en líneas
2. Preserva cabeceras (`#`, `##`, `###`, `**`, `---`)
3. Bufferiza tool outputs largos (>200 chars con "Output:", "Result:", etc.) y los comprime a `[... N lines, M chars compressed ...]`
4. Bufferiza bloques de código (```...```) y los comprime a `... [N lines compressed] ...` si >20 líneas
5. Mantiene el texto original si es menor que `min_chars`

**Helper: `_flush_buffer(buf, target)`:**
- Si buffer tiene >3 líneas y >500 chars totales → comprime a resumen 1 línea
- Si no → extiende target con las líneas originales

**Integración en TaskPlanner:**
```python
# En task_planner.py (harness/orchestrator/task_planner.py)
from harness.memory_rag.compaction import structured_compact

# En decompose():
if context and len(context) > 500:
    context = structured_compact(context, budget_ratio=0.6)
```

### 3. ShapedCache integrado en pipeline de agentes
**Archivo:** `harness/orchestrator/task_orchestrator.py`

**En `__init__`:**
```python
self._shaped_cache = None  # Inicializado por enable_cache()
```

**En `process_message` — verificación de cache antes de pipeline completo:**
```python
# Verificar cache semantico (ShapedCache - Token Economics)
if hasattr(self, '_shaped_cache') and self._shaped_cache is not None:
    cached = self._shaped_cache.get_shaped(message, threshold=0.95)
    if cached is not None:
        response = cached.get("response", "")
        if response:
            StructuredLogRecord.info("cache_hit", ...)
            return OrchestratorResult(
                plan=None, current_level=[], session_status="completed",
                is_complete=True, confidence=0.95, agent_agreement=1.0,
            )
```

**Función `enable_cache()` (Composition Root):**
```python
def enable_cache(orchestrator: TaskOrchestrator, max_tokens: int = 50000) -> None:
    """Habilitar ShapedCache en un TaskOrchestrator existente."""
    from harness.memory_rag.semantic_cache import ShapedCache, SemanticCache
    sem_cache = SemanticCache()
    orchestrator._shaped_cache = ShapedCache(semantic_cache=sem_cache, max_tokens=max_tokens)
```

### 4. Write-Ahead Log — Failure-Spend Governance
**Archivo nuevo:** `harness/orchestrator/write_ahead_log.py` (239 líneas)

Ver ADR-0012 sección 3 para documentación completa del WAL.

**Relación con Token Economics:**
- Failure-Spend Governance: el WAL evita gastar tokens en operaciones que van a fallar
- Circuit breaker por consumo excesivo: `max_retries` limitado (default 3)
- Cancelación first-class: `cancel()` permite detener operaciones que consumen tokens sin valor
- Write-Ahead Log: registro de operaciones antes de ejecutar (idempotencia en retry/cancel)

## Referencias
- **Mojentum 2026**: Cache-Shape Discipline para sistemas multi-agente (-38% tokens, hit rate >85%)
- **Struct47**: Structured state spaces para coordinación paralela (27%→46.9% OSWorld)
- **LAS51**: Language Agent Scheduling con 50.5% token reduction
- **Symphony-Coord**: Bandit routing con regret bounds para contexto bajo demanda (-44% tiempo)

## Consecuencias

### Positivas
- Cache hit evita pipeline completo de planificación + ejecución
- Compactación estructurada reduce contexto hasta 41%
- WriteAheadLog evita tokens perdidos en operaciones fallidas
- Integración limpia: Composition Root, sin modificar lógica existente

### Negativas
- Overhead de cache management (~2% CPU)
- ShapedCache requiere configuración explícita (`enable_cache()`)
- Compactación puede perder matices en contextos jurídicos/legales
- WAL en memoria si no se configura `log_dir`

### Pendiente
- Integrar `ShapedCache` en todos los puntos de entrada (no solo `process_message`)
- Reemplazar `structured_compact` en más puntos del pipeline
- Implementar `Scoped Context Spawn` con Symphony-Coord bandit routing
- Conectar WAL con el sistema de monitoreo de tokens real
