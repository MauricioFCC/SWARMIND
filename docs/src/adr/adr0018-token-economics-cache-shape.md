# ADR-0018: Token Economics — Cache Shape + Structured Compaction

## Estado
**PROPUESTO** — Extiende ADR-0008 con técnicas 2026.

## Contexto
ADR-0008 implementó 6 mecanismos de token economy. Análisis de uso real muestra que tres áreas tienen potencial de mejora adicional usando técnicas frontera 2026:

1. **Cache-Shape Discipline** (Mojentum 2026): -38% tokens mediante cache con forma activa
2. **Structured Compaction** (Struct47, LAS51): -41% costo mediante compresión estructurada
3. **Scoped Context Spawn** (Symphony-Coord): -44% tiempo mediante contexto bajo demanda

## Decisión

### 1. Cache-Shape Discipline (semantic_cache.py)
```python
class ShapedCache:
    """Cache con forma activa: LRU + TTL + relevancia."""
    def __init__(self, max_tokens=10000, ttl_sec=3600):
        self._lru = OrderedDict()
        self._ttl = ttl_sec
        self._max_tokens = max_tokens
    
    def get_shaped(self, key, context_window):
        # 1. Hit → refresh LRU, return shaped
        # 2. Miss → compute, shape (compact), store
        # 3. Evict LRU si excede max_tokens
```

### 2. Structured Compaction (context_window_manager.py)
```python
def structured_compact(sections, budget_ratio=0.6):
    """
    1. Calcular importancia (TF-IDF simplificado + recencia)
    2. Preservar secciones críticas (tool results, decisiones)
    3. Comprimir secciones de baja importancia con resúmenes de 1 línea
    4. Observación masking: tool outputs → placeholders
    """
```

### 3. Failure-Spend Governance
- Porcentaje de presupuesto por agente
- Circuit breaker por consumo excesivo
- Write-Ahead Log para idempotencia en cancelaciones/retry

## Consecuencias
- Positivas: Reducción 30-40% tokens totales, mejor costo por tarea
- Negativas: Overhead de cache management (~2% CPU)
- Métricas: Tokens/tarea, tokens/agente, cache hit ratio
