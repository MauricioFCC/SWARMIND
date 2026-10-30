# Investigación de frontera — Algoritmos O(n²)→O(n) y gates de calidad (2026-10-30)

> Dueño: harness — Estado: aplicado en ciclo 11.62.
> Método: investigación web en sesión (URLs leídas), contraste con el código
> real del repo y verificación por gate medido (`scripts/check_complexity.py`)
> + tests de equivalencia. Lo no aplicable se declara explícitamente.

## 1. Fórmulas aplicables (y su coste)

| # | Técnica | Fórmula | Antes → después | Cuándo aplica |
|---|---|---|---|---|
| 1 | Prefix sums / ventana móvil | `S_0=0`, `S_t=S_{t-1}+x_t`; `l..r = S_r−S_{l-1}`; `W_t=W_{t-1}+x_t−x_{t−W}` | O(n·W) → **O(n)** | operación invertible (suma, conteo, media) |
| 2 | Welford (media/varianza online) | `μ_n=μ_{n-1}+(x_n−μ_{n-1})/n`; `M2_n=M2_{n-1}+(x_n−μ_{n-1})(x_n−μ_n)` | O(n²) → **O(n)** | streaming sin guardar datos |
| 3 | Fenwick / BIT | `g(i)=i&(i+1)`; `T_i=Σ_{j=g(i)}^{i} A_j`; query/update `i|=i+1` | O(n) por query → **O(log n)** | updates y queries intercalados |
| 4 | Índice invertido / hash join | `H[k]={filas con clave k}`; join `⋃_k R[k]×S[k]` | O(n·m) → **O(n+m)** esperado | equijoin, lookup por clave, dedupe exacto |
| 5 | Ordenar una vez + `bisect` | `sort` O(n log n) + barrido O(n); `bisect_left` = ⌈log₂n⌉ | O(n²) → **O(n log n)** | dedupe/merge con colección estable |
| 6 | Aho-Corasick | `O(n + m + z)` (n texto, m patrones, z matches) | O(n·k·L) → **O(n+m+z)** | k patrones sobre el mismo texto |
| 7 | Karp-Rabin (rolling hash) | `h_{i+1}=((h_i−x_i·b^{L−1})·b+x_{i+L}) mod q` | O(n·L) → **O(n)** esperado | ventana fija / substrings |
| 8 | Count-Min / HyperLogLog | `w=⌈e/ε⌉`, `d=⌈ln(1/δ)⌉`; HLL error `≈1.04/√m` | memoria O(distintos) → **fija** | streams, cardinalidad aproximada |

**Qué NO cambia la asíntota** (verificado): free-threading (PEP 703→PEP 779) da
paralelismo real pero no reduce O; la especialización adaptativa (PEP 659) y el
JIT básico (PEP 744, experimental) solo bajan constantes.

Fuentes (leídas en sesión):
[Prefix sum](https://en.wikipedia.org/wiki/Prefix_sum) ·
[Welford](https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance) ·
[Fenwick (cp-algorithms)](https://cp-algorithms.com/data_structures/fenwick.html) ·
[Hash join](https://en.wikipedia.org/wiki/Hash_join) ·
[bisect](https://docs.python.org/3/library/bisect.html) ·
[Aho-Corasick](https://en.wikipedia.org/wiki/Aho%E2%80%93Corasick_algorithm) ·
[Karp-Rabin](https://en.wikipedia.org/wiki/Rabin%E2%80%93Karp_algorithm) ·
[Count-Min](https://en.wikipedia.org/wiki/Count%E2%80%93min_sketch) ·
[HyperLogLog](https://en.wikipedia.org/wiki/HyperLogLog) ·
[PEP 703](https://peps.python.org/pep-0703/) ·
[PEP 779](https://peps.python.org/pep-0779/) ·
[PEP 659](https://peps.python.org/pep-0659/) ·
[What's new 3.14](https://docs.python.org/3/whatsnew/3.14.html)

## 2. Reglas de decisión (anti-refactor innecesario)

1. **n < ~10³ y una sola pasada**: no refactorizar; `sum`/`in`/`set` en C
   ganan a un BIT o un heap en Python puro.
2. Refactorizar si hay **loop dentro de loop sobre la misma colección**, o
   `in`/`index`/`sum(slice)` dentro de un `for`.
3. Preferir **estructura de datos** a algoritmo: `set`/`dict` antes que
   ordenar; ordenar antes que comparar pares; heap antes que `sorted` completo.
4. Pagar O(log n) (Fenwick, `bisect`) solo con **consultas repetidas** sobre
   datos que mutan; con datos estáticos, prefix sums y un sort único ganan.
5. Medir antes/después con el tamaño real; un claim "ahora es O(n)" debe verse
   en el **crecimiento** (gate N/2N/4N/8N), no en un solo benchmark.

## 3. Aplicado en SWARMIND (ciclo 11.62)

| Hotspot | Técnica | Cambio | Evidencia |
|---|---|---|---|
| `factor_dsl._ts_rank` (rank rolling por columna) | Fenwick (#3) sobre valores comprimidos | O(T·W) → **O(T log m)** | `test_factor_dsl.py::TestTsRankEquivalence` (5 paneles con empates/NaN vs referencia ingenua) + benchmark `alpha.ts_rank` (ratio 2.10, clase `n_log_n`) |
| `AlphaZoo.is_similar` (dedup exacto por fórmula) | Índice invertido (#4) | O(n) → **O(1)** antes del loop de similitud | `test_alpha_zoo.py::TestFormulaIndex` (el duplicado exacto no calcula similitud) |
| `MCPManager.find_server_for_tool` | Índice invertido (#4) | O(n·m) → **O(1)** amortizado | `test_mcp_manager.py` (4 tests de invalidación) |
| `mcp_catalog.servers_for_task` | dict ordenado como set | O(n²) → **O(n)** | `test_mcp_catalog.py` |
| `KernelLoop`/`EventLog`/`KernelBus` | cola FIFO + log append-only | dispatch O(1) por mensaje | `test_kernel.py` (20), `test_kernel_bus.py` (11) |
| Gate de complejidad | escalas N/2N/4N/8N, mínimo de 5 × mediana de 2 rondas | detecta regresión a O(n²) | `scripts/check_complexity.py` (8 benchmarks) |

## 4. Evaluado y NO aplicado (con motivo)

- **Aho-Corasick** en `trajectory_audit`/`rust_policy`: k de reglas es pequeño
  (<30) y el texto corto; la regla #1 dice no refactorizar. Se deja como
  técnica del catálogo para cuando k o n crezcan.
- **Welford**: las medias de latencia ya se calculan sobre listas completas con
  NumPy (C, 2 pasadas); Welford solo gana en streaming real.
- **Count-Min / HLL**: los conteos del harness son exactos y acotados
  (`Counter` sobre sesiones), no hay stream infinito.
- **Fenwick para el token budget**: el presupuesto se recalcula por consulta
  (no hay updates intercalados), prefix sums sería equivalente y más simple.

## 5. Gates de calidad (estado del arte 2026)

- **mypy 2.x**: `strict` es opción por módulo; precedencia
  `inline > módulo > wildcard > CLI > global` → el contrato va en config, no en
  el comando. `-n auto` (cap 8 workers) acelera CI; `dmypy` ignora
  `num_workers`. Aplicado: `[[tool.mypy.overrides]]` strict en `harness.kernel`
  y `harness.domain` (bloqueante en CI), resto informativo con `-n auto`.
  [command_line](https://mypy.readthedocs.io/en/stable/command_line.html) ·
  [config_file](https://mypy.readthedocs.io/en/stable/config_file.html)
- **Ruff ratchet**: no hay baseline nativo (issue
  [#1149](https://github.com/astral-sh/ruff/issues/1149) abierto). Primitiva:
  `--output-format=json` + conteo por regla + baseline versionado. `preview`
  se activa solo en `[tool.ruff.lint]` y reglas preview se listan por código
  (una regla preview no se activa con `select = ["ALL"]`).
  [preview](https://docs.astral.sh/ruff/preview/) ·
  [versionado](https://docs.astral.sh/ruff/versioning/)
- **Buses request/reply**: correlación por `trace_id` + un único consumidor de
  respuestas (NATS `_INBOX.*`), timeout por operación y limpieza del mapa de
  correlación en `finally`. Aplicado: `harness/orchestrator/request_tracker.py`
  con reloj inyectado (tests sin `sleep`).
  [NATS request-reply](https://docs.nats.io/learn/core-nats/request-reply) ·
  [asyncio.timeout](https://docs.python.org/3/library/asyncio-task.html)
- **Mutación scoped**: mutmut 3.x usa `source_paths` +
  `pytest_add_cli_args_test_selection` (no `--paths-to-mutate`, que es 2.x);
  cachea por config y necesita `fork` (Windows → WSL).
  [README](https://raw.githubusercontent.com/boxed/mutmut/master/README.rst) ·
  [docs](https://mutmut.readthedocs.io/en/latest/)

## 6. Pendiente de la frontera (P2)

- Activar `preview = true` en lint con allowlist por código y `ruff` pinneado;
  el ratchet ya bloquea incrementos (baseline: 1 272 hallazgos / 20 reglas).
- Escalar mutación por módulo en 3 jobs (kernel 90 %, domain 75 %).
- Evaluar Aho-Corasick cuando `AUDIT_RULES` o el corpus de prompts crezcan.
