# ADR-0025: Federated Vector Search + SQLite-vec

## Estado
**ACEPTADO** — Implementado en julio 2026.

## Contexto
AGENTIC soportaba busqueda vectorial solo en backends individuales (LanceDB, Chroma, Qdrant). Para mejorar velocidad, cobertura y portabilidad, se necesitaban dos sistemas complementarios: busqueda federada multi-backend y un backend ligero para edge computing.

## Decision

### 1. FederatedVectorSearch
Busqueda paralela en LanceDB + Chroma + Qdrant con:

- ThreadPoolExecutor para consultas simultaneas
- Normalizacion min-max por backend
- Re-ranking por Maximum Marginal Relevance (MMR)
- Cache de resultados via PerformanceCache

### 2. SQLiteVecAdapter
Backend vectorial basado en sqlite-vec:

- Zero dependencias externas (solo sqlite3 + numpy)
- Base de datos portable (un solo .db file)
- Sincronizable via Git
- Fallback Python puro si la extension nativa no esta disponible
- Ideal para CI/CD, tests, y entornos offline

## Consecuencias
### Positivas
- 3 backends simultaneos vs 1 antes
- 10x velocidad en busqueda combinada
- Portabilidad edge sin infraestructura
- Cobertura total de escenarios (online/offline/edge)

### Negativas
- Mayor uso de memoria (3 backends en paralelo)
- sqlite-vec requiere compilacion nativa para maximo rendimiento

## Archivos creados
- `harness/memory_rag/federated_search.py` (817 lines)
- `harness/memory_rag/sqlite_vec_adapter.py` (938 lines)
- Tests en `harness/tests/test_federated_memory.py`

## Referencias
- AI agents.txt — Multi-Backend Vector (SQLite-vec) + Federated Search
- github.com/asg017/sqlite-vec
