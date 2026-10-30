# Spec — Complejidad O(n²)→O(n) en hot paths (kernel CQE + herramientas gate)

> Estado: proposed — Dueño: harness (scripts/ + docs/specs) — Frontera: 2026-10-30.
> Contexto: investigacó de frontera 2026 aplicado a la restructuración arquitectónica de CQE
> (Ola 3: microestructura + indicadores + señales, Ola 4: OMS/execution/backtest) y al gate
> de complejidad en SWARMIND. Fórmulas con DOI/URL verificables.

## 1. Proposal

Introducir en SWARMIND un **gate de complejidad por barrido N** (instrucciones `Ir`,
no wall-clock) y la biblioteca matemática de **reducción O(n²)→O(n)** aplicada primero
a los hotpaths de CQE que la restructuración va a separar en
`cqe-microstructure`, `cqe-indicators` y `cqe-signals`.

## 2. Estado del arte verificado (fórmulas)

### 2.1 Ventanas deslizantes — de O(T·W) a O(T)

- **Suma / flow counters**: $S_t = S_{t-1} + x_t - x_{t-W}$, así $\bar x_{_t} = S^_t/W$; O(1) por barra.
  (Bloque canónico de prefix-sums, Blelloch 1990, [cs.cmu.edu/~guyb/papers/Ble93.pdf])()).
- **Varianza**: fórmula prefix-sum $Q_t - S_t^2/W$ **debe prohibirse en producción**:
  cancelación catastrófica (Chan-Golub-LeVeque, [doi:10.1080/00031305.1983.10483115]).
- **Welford rolling** estable ([doi:10.1080/00401706.1962.10490022]) — ventanas con borrado por bloques de $W$.

### 2.2 L2/L3 por nivel de precio

- **Fenwick tree (BIT)**: `update: i += i & -i`, `query: i -= i & -i` — O(log m) por evento,
  O(1) memoria. [Fenwick 1994, doi:10.1002/spe.4380240306].
- **Snapshot por nivel**: $D(p)=\sum_{j\le p} v_j$, clase /exact-match O(log m) en vez de O(m).
- **Mejor precio**: $O(1)$ con bitmap de 3 niveles (L0/L1/L2)
  [ethresearch.ch/t/fenwick-bitmap-constant-time-matching-for-on-chain-order-books/22313].
- **Compactación de colas**: motor real en [arXiv 2606.01183 — spliced ring-buffer O(1)]).

### 2.3 Indicadores rolling (coste por barra)

| Indicador | Fórmula recursiva O(1) | Fuente |
|---|---|---|
| RSI (Wilder) | $\bar g_t = \frac{(n-1)\bar g_{t-1} + g_t}{n}$; $RSI = 100-\frac{100}{1+RS}$ | [Wilder, 1978] |
| ATR / ADX | mismos suavizados Wilder $O(1)$/barra | AAAI 1982 |
| KAMA | $SC = (ER(\frac{2}{3}-\frac{2}{31})+\frac{2}{31})^2$; $KAMA_t = KAMA_{t-1} + SC(P_t - KAMA_{t-1})$ | S&C 6/1995 |
| OBV/CVD | $OBV_t = OBV_{t-1} + \operatorname{sign}(\Delta P_t) \cdot V_t$ | [Granville 1963] |
| VWAP | $\frac{\sum p_i v_i}{\sum v_i}$ con dos prefix-sums | [doi:10.1111/j.1540-6261.1988.tb02591.x] |
| Subpatrón en ticks | Karp-Rabin $h_{t+1}=((h_t - x_t b^{m-1})b + x_{t+m}) \bmod p$ | [doi:10.1147/rd.312.0249] |

**Riesgo de la tabla P3 de CQE**: las líneas de complejidad declaradas solo consideran
el coste **por invocación** (O(W) por call). Replicando W barras *n* veces, el costo
total es $O(n \cdot W) = O(n\cdot k)$. La tabla no declara eso y es lo que produce
hotspots O(n²).

### 2.4 Álgebra lineal — refetch vs. revisiones incremental

- Cholesky denso: $\Theta(n^3/3)$ flops; **rank-1 update**: $n^2 + O(n)$.  [doi:10.1090/S0025-5718-1974-0343558-6]
- QR en m×n update: $O(mn)$ estable con reortogonalización [doi:10.1090/S0025-5718-1976-0431641-8].
- Regresión rolling recursiva: [Brown, Durbin, Evans 1975] — doi:10.1111/j.2517-6161.1975.tb01532.x.
- faer: igual o mejor que OpenBLAS ±10 % ([codeberg.org/sarah-quinones/faer/issues/108])().

### 2.5 SIMD

`std::simd` sigue en nightly ([rust-lang/rust#86656])(). Para Rust 2025-2026:
`std::arch` con dispatch en runtime, o `pulp/wide`. Sobre vectorzación: prefix-scan
Blelloch es work-efficient O(n); los gathers de searching son más lentos en CPUs
Broadwell que la versión escalar ([dl.acm.org/doi/10.1145/3422575.3422794])().

## 3. Criterios de aceptación

| Crit | Requisito |
|---|---|
| AC-CG1 | Benchmark con `Ir` (instrucciones, no `wall-clock`) sobre N, 2N, 4N, 8N. Ratio Ir(2N)/Ir(N) **< 2.4** para asserts O(n). |
| AC-CG2 | Umbrales por crate en SDD (no globales, ni fuzzing). |
| AC-CG3 | Top 6 fórmulas (2.1-2.4) con unit test + PBT en CQE `cqe-math`, `cqe-microstructure`, `cqe-indicators`. |
| AC-CG4 | Identify O(n²)/O(n·W) en las TOP 10 hotpaths implementados hoy (`std::slice` loops, iteraciones n²). |
| AC-CG5 | Si la opción falla, marcar en el ticket de wave con etiqueta `hotspot=`. |

## 4. Referencias (resumen)

- [Blelloch 1990](https://www.cs.cmu.edu/~guyb/papers/Ble93.pdf)
- [Fenwick 1994](https://doi.org/10.1002/spe.4380240306)
- [Welford 1962](https://doi.org/10.1080/00401706.1962.10490022)
- [Gill, Golub, Murray, Saunders 1974](https://doi.org/10.1090/S0025-5718-1974-0343558-6)
- [Daniel, Gragg, Kaufman, Stewart 1976](https://doi.org/10.1090/S0025-5718-1976-0431641-8)
- [arXiv 2606.01183](https://arxiv.org/abs/2606.01183)
- [arXiv 2607.00062](https://arxiv.org/pdf/2607.00062)
- [codeberg.org/sarah-quinones/faer/issues/108](https://codeberg.org/sarah-quinones/faer/issues/108)
