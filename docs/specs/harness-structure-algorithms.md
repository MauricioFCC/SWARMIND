# Spec — Estructura, arquitectura y algoritmos del harness (ciclo 11.61)

> Estado: **implemented** — Dueño: harness (transversal) — Frontera: 2026-10-30.
> Alcance: mejoras estructurales y algorítmicas derivadas de los specs
> `kernel-event-driven-nautilus.md` y `o-n-2-hotspots-gate.md`, aplicadas al
> propio SWARMIND (CQE es cliente, no dominio de comparación).

## 1. Proposal

Tres ejes, en orden de impacto:

1. **Estructura**: dar al kernel su propio paquete de borde (`harness/kernel/`)
   y consolidar las implementaciones de bus en el paquete existente
   `harness/orchestrator/agent_bus/` (async, persistente y determinista).
2. **Arquitectura**: congelar la regla "el kernel no conoce el dominio" como
   contrato declarativo (F8) y hacer que los contratos cubran **paquetes**
   completos, no solo archivos sueltos.
3. **Algoritmos**: sustituir búsquedas lineales repetidas por índices
   invertidos (build-once / lookup-many) y deduplicación O(n²) por dict
   ordenado; medir el resultado con un gate de escalas N/2N/4N.

## 2. Decisiones

| # | Decisión | Fundamento | Evidencia |
|---|---|---|---|
| ST-01 | `harness/kernel/` es un paquete de borde con envelope/mailbox/event_log/loop (≤ 200 líneas por archivo) | SRP: el sustrato no depende de agentes ni tools; el adaptador compone | `harness/kernel/*.py` |
| ST-02 | Los buses viven en un solo paquete: `async_bus.py`, `core.py`, `kernel_bus.py` | Descubribilidad + import estable `from ...agent_bus import KernelBus` | `agent_bus/__init__.py` |
| ST-03 | El docstring del paquete lista solo módulos existentes (se eliminó el drift `status.py`/`utils.py`) | DOC veraz: documentación que miente es deuda | `agent_bus/__init__.py` |
| AR-01 | Contrato F8 `kernel-agnostico`: `harness.kernel` solo puede importar `harness.kernel.*` | Aísla el núcleo; impide que el kernel se acople al orchestrator | `scripts/architecture_contracts.toml` |
| AR-02 | Los contratos F8 se evalúan por **prefijo de paquete** (módulo + submodulos) | Un contrato sobre un paquete no debe exigir una entrada por archivo | `check_declarative_contracts()` |
| AR-03 | Invariante de replay: el event log solo contiene mensajes **aceptados** por el buzón | Si hay backpressure no debe existir un evento fantasma con `seq` consumida | `KernelLoop.submit` + `test_submit_backpressure` |
| AL-01 | `find_server_for_tool` usa índice invertido `tool → server` (O(1) amortizado) | Antes: O(servidores × tools) por llamada; ahora build-once | `MCPManager._tool_server_index` + 4 tests |
| AL-02 | `servers_for_task` deduplica con dict ordenado en vez de `name not in list` | Elimina el peor caso O(n²) conservando el orden del catálogo | `mcp_catalog.servers_for_task` |
| AL-03 | Gate de complejidad por ratio adimensional (mínimo de 7 muestras × mediana de 3 rondas, GC off) con baseline de ratios y piso de ratchet | Portable entre máquinas; mide crecimiento, no velocidad absoluta; el ruido no decide el veredicto | `scripts/check_complexity.py` |
| AGR-01 | Ninguna función nueva supera 30 líneas (F5 sin tocar el ratchet) | La deuda no crece; se extraen helpers en lugar de ampliar el baseline | F5 929 → 929 |

## 3. Criterios de aceptación

| Crit | Requisito | Evidencia |
|---|---|---|
| AC-ST1 | `harness/kernel/` importa 0 módulos de `harness` fuera de sí mismo. | F8 `kernel-agnostico` en verde (`check_architecture --gate`). |
| AC-ST2 | `from harness.orchestrator.agent_bus import KernelBus` funciona y expone subscribe/publish/drain/replay/stats. | `harness/tests/test_kernel_bus.py` (11 tests). |
| AC-ST3 | El event log no registra mensajes rechazados por backpressure. | `test_full_mailbox_raises_typed_error_and_does_not_log`. |
| AC-AL1 | `find_server_for_tool` no re-escanea servidores en cada llamada y refleja cambios de registro. | `test_reverse_index_is_reused` + 3 tests de invalidación. |
| AC-AL2 | El gate de complejidad falla ante ratio superlineal y ante regresión vs baseline. | `harness/tests/test_check_complexity.py` (11 tests). |
| AC-AL3 | CI bloquea con `check_complexity.py --gate` y T2 muta los 9 módulos de memoria gobernada. | `.github/workflows/ci.yml` (jobs `complexity` y `mutation`). |
| AC-AGR1 | Nuevas funciones ≤ 30 líneas: F5 del ratchet no aumenta. | `check_architecture --gate --ratchet` = 0. |

## 4. Siguientes pasos (P1/P2)

- **P1 — AC-KN5**: migrar `run_commands` y `agent_dispatcher` a `KernelBus`
  con `trace_id` correlacionado y timeouts tipados (contrato externo intacto).
- **P1 — mypy strict incremental**: empezar por `harness/kernel/` y
  `harness/domain/` con `[[tool.mypy.overrides]]`; CI con `-n auto`.
- **P2 — ruff preview con ratchet**: activar `preview=true` solo en lint y
  bajar RUF069/PERF401 por módulo (nunca auto-fix masivo de reglas meta).
- **P2 — 8N en el gate**: añadir escala 8N cuando el job baje de 2 min.

## 5. Referencias

- [NautilusTrader architecture](https://nautilustrader.io/docs/latest/concepts/architecture/)
- [iai-callgrind / gungraun regressions](https://gungraun.github.io/gungraun/latest/html/regressions.html)
- [ALGOBENCH (arXiv 2607.00062)](https://arxiv.org/pdf/2607.00062)
- [Fenwick 1994](https://doi.org/10.1002/spe.4380240306)
