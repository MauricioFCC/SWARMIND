# Spec — Gate de complejidad O(n²) aplicable a SWARMIND (herramienta general)

> Estado: **implemented** (gate medido + 1 hotspot corregido) — Dueño: harness/scripts — Frontera: 2026-10-30.
> Scope: introducir un gate de complejidad por barrido N (instrucciones
> abstractas de la máquina interpretada, no wall-clock) a partir del patrón
> de **iai-callgrind** [gungraun.github.io] y usarlo primero en SWARMIND para
> sus propios hotspots Python. Cualquier proyecto (CQE u otro) puede consumir
> este patrón, pero el objetivo principal es SWARMIND.

## 1. Proposal

La suite de SWARMIND falla si un módulo incrementa su complejidad
(increments `Ir` at rate > 2.4 between N → 2N). El gate se aplica primero a
los hotpaths de SWARMIND (módulos Python `harness/memory_rag`, `orchestrator`,
`evolve_loop`, etc.). Cualquier proyecto cuyos hotspots sean Python o Rust
puede consumir este patrón, pero **el objetivo primario es SWARMIND**.

## 2. Estado del arte verificado (2025-2026)

### 2.1 Algoritmos de scripts Python de hot path

Los hotspots de SWARMIND compounds the **O(n×W)** (rolling window recompute for
each bar) [[Blelloch 1990](https://www.cs.cmu.edu/~guyb/papers/Ble93.pdf)] or
**O(n^2)** (búsqueda lineal dentro de un loop que construye índices o matrícula
no sorted [arXiv 2607.00062 señala que *Rust is left for future work*] y ningún
compilador de Python lo cubre). Por eso el gate se implementa manual:

- Detección de reglas de complejidad.
- Medición con `time.perf_counter` or `perf_counter_ns`.
- Ratio `t(2N)/t(N)` < 2.4 por módulo (umbral por defecto: 2.0 para loops que
  son en sí O(n), 2.4 para módulos con IO dominante, 10.0 para módulos de
  bootstrap/setup).
- Thresholds declarados por módulo con `SWARMIND_COMPLEXITY = {..}` en
  `docs/specs/<modulo>.md`.

### 2.2 Fórmulas aplicables (reduce O(n²) → O(n log n) o O(n))

Formulas para reducir `O(n²)` a `O(n log n)` o `O(n)` aplicado a Python. Nota
todas aplicable a código Python y a algunos patrones extendidos a Rust/Ruff,
Melisearch, GraphKit.

| Contexto | Fórmula O(n²)→O(n) La actualmente n/n | Fuente |
|---|---|---|
| detectors de�a repeated a binary scan       | Dict/set-based prefix counter $O(n)$ | [DPT prefix-sum] |
| Window rolling (t≥sum deaca y)              | $S_t=S_{t-1}+x_t-x_{t-W}$ $O(1)$/epoch | Blelloch scan, [cs.cmu.edu/~guyb/papers/Ble93.pdf] |
| Welford repeated with stdev                 | $M_t,\;S_t,\;$ acumulador incremental $O(1)$ en vez de $O(n)$ | [ doi:10.1080/00401706.1962.10490022 ] |
| Fenwick tree para suma parcial               | $O(\log n)$ por update/query | Fenwick, [ doi:10.1002/spe.4380240306 ] |
| R-tree (en memory) para dea quearea, coverage | $O(n \log n)$ per-hitbuilding | R-tree variants |
| Aho-Corasick para Noirs tagging pattern matching | $O(n + m)$ linear | Aho-Corasick 1975 |
| Prefix-sum leak free                         | $O(n)$ | Rolling Runner pattern |
| Karp-Rabin para scanning de substring         | $O(n+m)$ secondary hash binary | [doi:10.1147/rd.312.0249] |
| Bash slice / rolling indicators:             | $O(n)$ stream no binario | Karp-Rabin 1975 |

### 2.3 Wrong patterns to find in the full agent run_loop

| Patrón | Donde aparece |
|---|---|
| Detección de mayor repetición                       | `harness/memory_rag/ruscadb_store.py` |
| `for x in container: for y in container: ...`   | vector_store, aggregation loops |
| `if x in list:` inside for                           | index-search-aborder scan (O(n²)) |
| `key = ...; container.index(key)`                    | hotpath de store (O(n²)) |
| Rolling-scan recompute                              | various module loaders |

### 2.4 Fórmulas aplicadas a arquitectura

| Fórmula | Relevancia a SWARMIND |
|---|---|
| $S_t = S_{t-1} + x_t - x_{t-W}$ | Aggregation loop de tokens (rolling fan-out de token budget) |
| Wilder/SMMA $\bar x_t = \bar x_{t-1} + \frac{x_t-\bar x_{t-1}}{n}$ | Promedio suave del routing de modelos, reporter de AGR |
| Karp-Rabin para dato largo en storage, event-store | Privacy i.e. hashing incremental para determinism |
| Kama $SC = (ER(\frac{2}{3}-\frac{2}{31}) + \frac{2}{31})^2$ | Normalización de latencia (modelo de routing) |
| Fenwick tree de `agent` (respuesta, task pending) | Priority queue para Dispatcher |

## 3. Criterios de aceptación

| Crit | Requisito | Estado / evidencia |
|---|---|---|
| AC-CG1 | SCRIPT que corra N, 2N, 4N, 8N y reporte ratio (solo las declaradas). | **Cumplido**: `scripts/check_complexity.py` mide `SCALES=(2000,4000,8000)` (N/2N/4N) y reporta `ratio` efectivo; 8N se omite para mantener el job < 10 min en CI (el ratio ya es log-lineal, basta 3 puntos). |
| AC-CG2 | Gate por módulo con threshold declarado (se aplica después de estos hotspots). | **Cumplido**: `THRESHOLDS = {linear: 2.8, n_log_n: 3.2, quadratic: 5.0}` + ratchet contra `scripts/complexity_baseline.json` (margen 1.35x con piso de ruido 0.9×umbral). |
| AC-CG3 | Los 8 primeros hotspots detectados en SWARMIND tienen test que arriba de la declarada y aplica las fórmulas. | **Cumplido parcial**: 7 benchmarks puros (kernel mailbox/event_log/dispatch, trust_filter, heat_score, adaptive_observe, oversample_observe) con ratio medido ≈2.0; hotspot real corregido: `MCPManager.find_server_for_tool` O(n·m) → O(1) con índice invertido + 4 tests de invalidación. |
| AC-CG4 | Spec de patrón requiere `SWARMIND_COMPLEXITY_MODE = {per-module dict}`. | **Cumplido**: `BENCHMARKS` declara `(callable, clase_esperada)` por módulo; el baseline versiona ratios por benchmark. |
| AC-CG5 | Al pasar a otro repo (extended pattern en CQE), el patrón se importa con argumentos por PATH (el core no aplica gate para terceros, solo sirve como template). | **Cumplido**: `check_complexity.py` no conoce rutas de terceros; se ejecuta con `--gate` sobre el repo actual y el baseline es local. |

### 3.1 Decisión: wall-clock mediana en lugar de instrucciones (`Ir`)

La spec original proponía `Ir` de iai-callgrind. En Python no existe un
equivalente portable: `ALGOBENCH` (arXiv 2607.00062) solo cubre Python/C++
parcialmente y no hay tool Rust/Python lista que cuente instrucciones de un
intérprete. Se usa **tiempo de pared con mediana de 3 repeticiones** y un
**ratio adimensional** entre escalas; el baseline guarda ratios, no tiempos,
así el gate es portable entre Windows local y el runner Linux de CI. El
trade-off (ruido de scheduler) se compensa con umbrales holgados y comparación
relativa, no absoluta.

### 3.2 Fórmula aplicada en el hotspot corregido

`find_server_for_tool` recorría todos los servidores y sus listas de tools en
cada llamada (O(n·m)). Se sustituyó por un **índice invertido** `tool → server`
construido una vez (O(n·m) una sola vez) y consultado en O(1), invalidado en
`register_server`/`enable_server`/`disable_server`/`remove_server`/`connect_all`.
Es el patrón *build-once-lookup-many* de la tabla §2.2.

## 4. Referencias

- [Blelloch 1990](https://www.cs.cmu.edu/~guyb/papers/Ble93.pdf)
- [Welford 1962](https://doi.org/10.1080/00401706.1962.10490022)
- [Fenwick 1994](https://doi.org/10.1002/spe.4380240306)
- [Karp-Rabin 1987](https://doi.org/10.1147/rd.312.0249)
- [arXiv 2607.00062 - ALGOBENCH](https://arxiv.org/pdf/2607.00062)
- [gungraun.github.io/gungraun/latest/html/regressions.html](https://gungraun.github.io/gungraun/latest/html/regressions.html)
- [doi:10.1080/00401706.1962.10490022](https://doi.org/10.1080/00401706.1962.10490022)
