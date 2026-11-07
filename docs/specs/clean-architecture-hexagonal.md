# Spec — Clean Architecture Hexagonal (SWARMIND)

> Estado: **implemented** (F1/F2/F4/F6/F8 + ratchet F7 en CI) — Dueño: harness/core — Frontera: 2026-10.
> Referencias: Clean Architecture (Martin 2017), Hexagonal (Cockburn), Fitness Functions (Ford/Parsons/Kua), ArchUnit, tach.

## 1. Objetivo

Garantizar que SWARMIND mantenga una arquitectura hexagonal estricta y verificable:
capas con dependencias unidireccionales, puertos/adaptadores, dominio puro, y
fitness functions automatizadas que bloqueen regresiones arquitectonicas en CI.

## 2. Capas y regla de dependencia

```
Presentation (CLI/UI/MCP) -> Application (use cases) -> Domain (entities, ports)
Infrastructure (adapters: DB, FS, network, LLM) -> Domain (implementa ports)
```

Regla: las dependencias apuntan SIEMPRE hacia Domain. Un adapter nunca depende
de otro adapter; la composicion vive en un composition root.

### 2.1 Capas del repo actual
- `harness/memory_rag/` — Application + Infrastructure (vector stores, RAG).
- `harness/orchestrator/` — Application (agentes, routing, bus).
- `harness/evolve_loop/` — Application (evolucion).
- `harness/domain/` (a crear) — Domain puro: entities, value objects, ports (interfaces).
- `harness/adapters/` (a crear) — Infrastructure: implementaciones de ports.

## 3. Puertos (interfaces abstractas)

Puertos a definir en `harness/domain/ports.py`:
- `VectorStorePort`: insert, search, hybrid_search, delete, clear, stats.
- `EmbeddingPort`: embed(text) -> vector.
- `LLMPort`: complete(prompt) -> text.
- `MemoryPort`: get/set/delete by key.
- `EventBusPort`: publish/subscribe.
- `SkillPort`: load, list, resolve.

Los adaptadores actuales (RuscaDBStore, LanceVectorStore, in-memory) implementan
`VectorStorePort`.

## 4. Fitness functions (automatizadas en CI)

- **F1 — Imports de capa**: no importar `harness.memory_rag.*` desde `harness/domain/*`.
- **F2 — Dominio puro**: `harness/domain/` no importa frameworks (lancedb, numpy, torch, requests, sqlalchemy).
- **F3 — Tamaño de módulo**: ningún archivo > 500 líneas (regla AGR).
- **F4 — Tamaño de función**: ninguna función > 30 líneas (FSZ).
- **F5 — Ciclos de import**: 0 (verificar con `tach` o script).
- **F6 — Aristas prohibidas**: Domain no depende de Infrastructure.

Herramientas: `tach` (ya en deps?), `import-linter`, o script custom en
`scripts/check_architecture.py` (como RuscaDB).

## 5. Migracion (incremental, no big-bang)

1. Crear `harness/domain/ports.py` con Protocols (typing.Protocol).
2. Hacer que `RuscaDBStore`, `LanceVectorStore` implementen `VectorStorePort`.
3. Mover entidades puras (Skill, Agent, Task, MemoryEntry) a `harness/domain/entities.py`.
4. Actualizar imports gradualmente; fitness functions bloquean regresiones.
5. Composition root en `harness/composition.py` cablea adapters.

## 6. Outcome medible

- `python scripts/check_architecture.py` → 0 ciclos, 0 aristas prohibidas.
- `ruff` + `vulture` + tests verdes.
- Coverage domain >= 90%.

## 7. Esfuerzo estimado

- Fase 1 (ports): 1-2 dias.
- Fase 2 (migracion incremental): 1 semana.
- Fase 3 (fitness functions en CI): 1 dia.

## Evidencia (ciclo 11.53)

- Puertos: `harness/domain/ports.py` (`VectorStorePort`, `TextSearchPort`,
  `EmbeddingPort`, `LLMPort`, `MemoryPort`, `EventBusPort`).
- Adaptadores: `RuscaDBStore` y `LanceVectorStore` cumplen el puerto
  (conformance estatica en el job `architecture` de CI).
- Composition root: `harness/memory_rag/vector_store_factory.py`.
- Fitness functions: `scripts/check_architecture.py --gate --ratchet` (F1
  pureza de dominio, F2 frameworks prohibidos, F4 ciclos Tarjan SCC, F6
  conformidad puerto→adaptador, F8 contratos declarativos, F7 ratchet de deuda
  F3/F5 que solo bloquea incrementos) en pre-commit y CI.
- **Decisión (composition root)**: `harness/run.py` es el composition root y
  puede importar `harness.*`; no se separa físicamente en
  Presentation/Application porque los contratos relevantes (domain puro,
  kernel agnóstico, puertos) ya están congelados por F2/F8. El ratchet F3/F5
  sigue bajando la deuda de tamaño sin bloquear el repo.
