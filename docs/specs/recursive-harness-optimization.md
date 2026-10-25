# Spec — Optimizacion de Recursividad (Harness2 + Reflexion + DSPy)

> Estado: proposed — Dueño: harness/evolve_loop — Frontera: 2026-10.
> Referencias: Harness² (Google Research), Reflexion (Shinn et al. 2023, arXiv:2303.11366),
> DSPy (Khattab et al. 2023, arXiv:2310.03714), ASI-Evolve.

## 1. Objetivo

Mejorar el harness recursivo (Harness²) para que la auto-mejora sea acotada,
medible y token-eficiente: profundidad maxima configurable, early-stopping por
convergencia, memoria episodica de reflexiones, y compilacion declarativa de
pipelines (DSPy-style) para optimizar prompts sin hard-coding.

## 2. Problemas actuales

- `harness/harness2/` y `harness/evolve_loop/recursive_harness.py` existen pero
  no tienen early-stopping ni budget de tokens por recursion.
- Las reflexiones (Reflexion) no se persisten en memoria central; se pierden
  entre sesiones.
- Los prompts son strings hard-coded; no hay compilacion declarativa (DSPy).

## 3. Diseno

### 3.1 Bounded recursion
- `max_depth` (default 3) configurable via env `HARNESS_MAX_DEPTH`.
- `max_tokens_per_recursion` (default 4000) — aborta si se excede.
- Early-stopping: si el score no mejora en 2 iteraciones consecutivas, parar.

### 3.2 Memoria episodica de reflexiones
- Persistir reflexiones en RuscaDB (coleccion `reflections`) con FTS.
- Recuperar reflexiones relevantes via GraphRAG antes de cada recursion.
- Evitar repetir errores ya reflexionados (dedup por similitud).

### 3.3 Compilacion declarativa (DSPy-style)
- Abstraer cada paso del harness como un modulo declarativo con inputs/outputs.
- Un compilador optimiza los prompts (few-shot, chain-of-thought) contra una
  metrica objetivo usando bootstrap de demos.
- Los modulos se persisten en RuscaDB (coleccion `harness_modules`).

### 3.4 Recursion segura
- Cada recursion crea un snapshot (RuscaDB MVCC `execute_at`) para rollback.
- Si la recursion falla, restaurar el snapshot anterior.
- Limite de tiempo por recursion (`RECURSION_TIMEOUT_SEC`, default 120).

## 4. Componentes nuevos

- `harness/evolve_loop/bounded_recursion.py`: `BoundedRecursion(max_depth, max_tokens, timeout)`.
- `harness/evolve_loop/reflection_memory.py`: `ReflectionMemory(store)` sobre RuscaDB.
- `harness/evolve_loop/dspy_compiler.py`: `HarnessCompiler(modules, metric)`.

## 5. Outcome medible

- Recursion depth <= max_depth en todos los casos.
- Early-stopping reduce tokens en >= 30% vs recursion fija.
- Reflexiones persisten y se recuperan entre sesiones.
- Tests: `test_bounded_recursion.py`, `test_reflection_memory.py`.

## 6. Esfuerzo estimado

- Fase 1 (bounded recursion): 2 dias.
- Fase 2 (reflection memory): 1 dia.
- Fase 3 (DSPy compiler): 1 semana.
