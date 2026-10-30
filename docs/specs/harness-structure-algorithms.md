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
| AL-03 | Gate de complejidad por ratio adimensional (mínimo de 5 muestras × mediana de 2 rondas, GC off) con baseline de ratios y piso de ratchet | Portable entre máquinas; mide crecimiento, no velocidad absoluta; el ruido no decide el veredicto | `scripts/check_complexity.py` |
| AL-04 | `factor_dsl._ts_rank` usa Fenwick sobre valores comprimidos | Ventana móvil O(T·W) → O(T log m) con resultado idéntico (midrank) | `_Fenwick` + `TestTsRankEquivalence` + benchmark `alpha.ts_rank` |
| AL-05 | `AlphaZoo` mantiene un set de fórmulas para dedup exacto O(1) antes del loop de similitud | El caso frecuente (duplicado exacto) deja de costar O(n·AST) | `AlphaZoo._formulas` + `TestFormulaIndex` |
| AL-06 | Ratchet de Ruff sobre preview (conteo por regla vs baseline) | Ruff no tiene baseline nativo (issue #1149); solo falla si un conteo sube | `scripts/check_ruff_ratchet.py` + `ruff_baseline.json` |
| AR-04 | `RequestTracker` con `trace_id` + timeout tipado + reloj inyectable | Correlación req/resp determinista, sin `sleep` en tests | `harness/orchestrator/request_tracker.py` |
| AGR-01 | Ninguna función nueva supera 30 líneas (F5 sin tocar el ratchet) | La deuda no crece; se extraen helpers en lugar de ampliar el baseline | F5 929 → 929 |

## 3. Criterios de aceptación

| Crit | Requisito | Evidencia |
|---|---|---|
| AC-ST1 | `harness/kernel/` importa 0 módulos de `harness` fuera de sí mismo. | F8 `kernel-agnostico` en verde (`check_architecture --gate`). |
| AC-ST2 | `from harness.orchestrator.agent_bus import KernelBus` funciona y expone subscribe/publish/drain/replay/stats. | `harness/tests/test_kernel_bus.py` (11 tests). |
| AC-ST3 | El event log no registra mensajes rechazados por backpressure. | `test_full_mailbox_raises_typed_error_and_does_not_log`. |
| AC-AL1 | `find_server_for_tool` no re-escanea servidores en cada llamada y refleja cambios de registro. | `test_reverse_index_is_reused` + 3 tests de invalidación. |
| AC-AL2 | El gate de complejidad falla ante ratio superlineal y ante regresión vs baseline. | `harness/tests/test_check_complexity.py` (13 tests). |
| AC-AL3 | CI bloquea con `check_complexity.py --gate` y T2 muta los 9 módulos de memoria gobernada. | `.github/workflows/ci.yml` (jobs `complexity` y `mutation`). |
| AC-AL4 | `_ts_rank` con Fenwick reproduce el midrank de la versión ingenua (empates y NaN incluidos). | `test_factor_dsl.py::TestTsRankEquivalence` (5 semillas + borde). |
| AC-AL5 | El dedup exacto del zoo no calcula similitud de AST. | `test_alpha_zoo.py::TestFormulaIndex`. |
| AC-AL6 | El ratchet de Ruff falla solo ante incrementos y baja al aplicar fixes seguros (1 326 → 1 272). | `test_check_ruff_ratchet.py` (9 tests) + baseline. |
| AC-AR4 | req/resp con `trace_id` y timeout tipado sin `sleep`. | `test_request_tracker.py` (8 tests). |
| AC-AGR1 | Nuevas funciones ≤ 30 líneas: F5 del ratchet no aumenta. | `check_architecture --gate --ratchet` = 0. |

## 4. Estado de la ola P1/P2

| Item | Estado | Evidencia |
|---|---|---|
| AC-KN5 (trace_id en run_commands/agent_dispatcher) | **Hecho** | `RequestTracker`, `command.start/end/error`, `agent.dispatch` |
| mypy strict incremental (kernel + domain) | **Hecho** | `[[tool.mypy.overrides]]` + CI bloqueante; 7 archivos strict-clean |
| mypy `-n auto` en CI | **Hecho** | job `type-check` (global informativo) |
| Ruff ratchet (preview PERF/FURB/RUF) | **Hecho** | `scripts/check_ruff_ratchet.py` + job `ruff-ratchet`; 54 fixes seguros aplicados |
| Escala 8N en el gate | **Hecho** | `SCALES=(10k,20k,40k,80k)`; 8 benchmarks, ~48 s local |
| mutación scoped por PR | **Parcial** | T2 muta 9 módulos fijos; el scoping por `git diff` sigue en P2 |
| seed determinista en runs | **Hecho (kernel)** | `seq` canónica + FIFO + `replay()` |

## 5. Siguientes pasos (P2)

- **P1 — AC-KN5**: migrar `run_commands` y `agent_dispatcher` a `KernelBus`
  con `trace_id` correlacionado y timeouts tipados (contrato externo intacto).
- **P1 — mypy strict incremental**: empezar por `harness/kernel/` y
  `harness/domain/` con `[[tool.mypy.overrides]]`; CI con `-n auto`.
- **P2 — ruff preview con allowlist**: activar `preview=true` solo en lint y
  bajar RUF069/PERF401 por módulo (el ratchet ya bloquea incrementos).
- **P2 — mutación scoped por PR**: generar `pytest_add_cli_args_test_selection`
  desde `git diff` y separar umbrales por paquete (kernel 90 %, domain 75 %).
- **P2 — Aho-Corasick**: evaluar cuando `AUDIT_RULES`/corpus de prompts crezcan
  (hoy k pequeño: la regla de decisión dice no refactorizar).

## 5. Referencias

- [NautilusTrader architecture](https://nautilustrader.io/docs/latest/concepts/architecture/)
- [iai-callgrind / gungraun regressions](https://gungraun.github.io/gungraun/latest/html/regressions.html)
- [ALGOBENCH (arXiv 2607.00062)](https://arxiv.org/pdf/2607.00062)
- [Fenwick 1994](https://doi.org/10.1002/spe.4380240306)
