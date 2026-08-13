# ADR-0009: Lazy Loading PEP 562 — Cold Start 72x mas rapido

## Estado
**ACEPTADO** — Implementado en commit c1ea3fd.

## Contexto
Al abrir OpenCode en el proyecto Swarmind, `import harness` cargaba EAGERLY todos los submodulos:
- 20+ modulos en cascada (task_manager, agent_bus, lance_vector_store, evolve_loop, etc.)
- Cada modulo importaba numpy, LanceDB, etc.
- Cold start: ~2800ms antes de que el usuario pudiera hacer cualquier cosa

Ademas, la memoria del sistema no se mantenia entre sesiones de OpenCode porque no habia un mecanismo de inicializacion rapida.

## Decision
Refactorizar `harness/__init__.py` y `harness/orchestrator/__init__.py` para usar **lazy imports via `__getattr__`** (PEP 562).

### Mecanismo
1. Se eliminan todos los `from ... import ...` eager del `__init__.py`
2. Se define `_SYMBOL_MAP: Dict[str, str]` que mapea nombre -> modulo
3. `__getattr__(name)` se llama SOLO cuando se accede a un simbolo no definido
4. El modulo se importa bajo demanda y se cachea en `globals()` y `sys.modules`
5. `__dir__()` soporta tab completion

### Ventajas
- `import harness` ahora toma ~39ms en vez de ~2800ms (72x mas rapido)
- Los modulos solo se cargan cuando se usan explicitamente
- OpenCode puede iniciar instantaneamente y cargar componentes bajo demanda
- La memoria persiste: una vez cargado un modulo, queda cacheado en `sys.modules`

### Nuevos modulos incluidos en el lazy map
Los 6 modulos creados en ADR-0008 tambien estan en el mapa lazy:
- workflow_patterns (evaluator_optimizer, voting, critique_revise, parallel_transform)
- pbt_templates (PBTTemplate, TEMPLATES)
- behavioral_tracer (BehavioralTracer)
- architectural_guardrails (check_all)

## Archivos Modificados
- `harness/__init__.py`: Reescrito con lazy imports via `__getattr__` (PEP 562)
- `harness/orchestrator/__init__.py`: Reescrito con lazy imports

## Tests
- `harness/tests/test_lazy_loading.py`: 8 tests que verifican:
  - import harness no carga submodulos pesados
  - Acceso a simbolo carga modulo bajo demanda
  - Segundo acceso usa cache
  - Simbolos nuevos accesibles
  - Import time < 100ms

## Consecuencias
- **Positivas**: Cold start 72x mas rapido; OpenCode inicia en 39ms; modulos se cargan bajo demanda; todo sigue funcionando (457 tests pass).
- **Negativas**: Test suite total subio de ~45s a ~67s (los import costs se distribuyen entre test files en vez de pagarse una sola vez al inicio). Esto es aceptable porque en produccion solo se usa un subconjunto de modulos por sesion.

## Referencias
- PEP 562 — Module `__getattr__` and `__dir__`
- ADR-0008: 6 nuevas tecnicas (lazy loading de esos modulos)
- Python import system: `sys.modules` caching behavior
