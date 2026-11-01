# RuscaDB + SWARMIND — Investigación de frontera 2026-11-01

> Dueño: harness (memory_rag/alpha_mining) — Estado: aplicado el ciclo con
> evidencia. Método: upstream log leído en la sesión + papers (URLs leídas) +
> mejora O(n·W)→O(n) implementada con verificación de equivalencia y gate.

## 1. Upstream RuscaDB (HEAD `0984bb9`, 2026-11-01) — deltas desde `16a01c0`

Leído en la sesión: `git log` del repo local + `docs/RuscaDB-frontier-research.md`
+ `docs/RuscaDB-funcionalidades.md` de upstream.

| Delta upstream | SPEC | Impacto en SWARMIND | Estado |
|---|---|---|---|
| Lógica **3VL** en SQL (NULL comparaciones) | SPEC-0182 | Prepared/RQL devuelven tres-valued para col. NULLables | Documentar en specs; consume tras rebuild DLL |
| **Prepared statements API** (`prepare`/`execute_prepared`, `RuscaError.code()`) | SPEC-0184 | Ya existe capa Python `prepared_statements.py` (11.55); nueva API nativa reemplaza el path Python al hacer rebuild | Parcial (DLL 2026-10-29 no trae la API) |
| `KNN ... USING AUTO\|QUANTIZED\|FILTERED\|EXACT` + C-ABI `search_quantized`/`search_filtered` | SPEC-0181 | `ruscadb_search_bq` ya cableado (11.56); los modos FILTREADO/EXACT requieren rebuild | Después del rebuild |
| Formato columnar en disco `RCOL1` (ALP/FOR + bit-packing) | SPEC-0110 | Analytics sobre tablas grandes vía RQL; el harness no lo toca todavía | Watch |
| **Gate de mutación bloqueante MS≥85 %** en CI upstream | — | Doctrina igual a la nuestra (TST); alineado | OK |
| `CASE`, booleanos, vector relacional, executor modular en RQL | — | Queries complejas sin Python glue | Watch |
| **3VL + DISTINCT lineal** | — | Dedupe exacto sin sort (UP) | Watch |

**Decisión EDV**: NO pre-cablear la API nueva sin rebuild — el binario
`ruscadb_ffi.dll` (2026-10-29) no exporta los símbolos nuevos. Capa Python
sigue el contrato del C-ABI estable (44 funciones verificadas esta sesión).
Al reconstruir: ejecutar `scripts/setup_swarmind.py` (copia DLL) y correr
`test_ruscadb_store.py` + `test_ruscadb.py` para cerrar contrato.

## 2. Fórmulas aplicadas en este ciclo

### 2.1 Correlación rolling O(n·W) → O(n) (prefix sums)

```
S[t]      = S[t-1] + x_t            (0-padded; también ab, aa, bb, mask)
ventana W: suma_W    = S[t] - S[t-W]
corr      = (n·Sxy - Sx·Sy) / (sqrt(n·Sxx - Sx²) · sqrt(n·Syy - Sy²))
pares completos: x,y finitos simultáneos (mask; los NaN no contaminan)
```

- Implementación: `rolling_rank.ts_corr` (switch O(1) por ventana; W desaparece).
- Equivalencia: 11 tests contra referencia ingenua O(n·W) por columna
  (`test_ts_corr_prefix.py`) con NaN, mascaras cruzadas, ventanas extremas.
- Bug oral catch: el primer oráculo mezclaba columnas (ref sin loop por
  columna) → los 11 primeros test fallaban **contra el código viejo**:
  refactor先将 red flag antigos contra el oráculo corregido (11/11), luego
  implementar O(n) manteniendo verde (11/11). Nota Err: al variar la
  implementación mantener el oráculo CONGELADO y revisar su aritmética primero.
- Gate: benchmark `alpha.ts_corr` (ventana ∝ n, 5 % NaN) ratio medido **1.94 ≈
  linear ok**; la versión por ventanas dispararía a ~4.

Evidencia upstream en papers: [Scan/Blelloch](https://www.cs.cmu.edu/~guyb/papers/Ble93.pdf),
[prefix-sums cov](https://imoz.jp/scraps/202607_mvar.en.html),
[Chan merge](https://dl.acm.org/doi/pdf/10.1145/3221269.3223036).

### 2.2 `_update_records_lancedb` 71→30 líneas legibles (funciones extraidas)

Refactor puramente estructural (comportamiento idéntico, tests existentes):
`_open_update_table`, `_read_existing_records`, `_validated_record_id`
(anti-inyección CWE-943 intacta), `_update_single_record` (fail-soft por
fila). Complejidad no cambia (O(k) updates por k resultados del filtro);
deuda F5 baja sin tocar baseline del ratchet.

## 3. Técnicas evaluadas NO aplicadas (con motivo)

| Técnica | Motivo de espera |
|---|---|
| RaBitQ extended (SIGMOD 2025), rotación Hadamard | Requiere cambios en `ruscadb-vector` (upstream); nuestra capa ya usa `ruscadb_search_bq`. Cuando el upstream trae 2-6 bits, cablear `KNN USING QUANTIZED` con recall medido 4-7 bits ≥ 90 %. |
| TRIM pruning por desigualdad triangular (−90 % distancias) | Motor Rust; lo decide upstream |
| Block-Max WAND / LazyBM en BM25 | El FTS de RuscaDB puntúa con BM25 propio; para top-k global el harness filtra `top_k` del engine. Cuándo: FTS con > 10⁵ postings |
| MinHash/LSH banding para dedupe de factor zoo | `AlphaZoo` ya es O(1) exacto por fórmula + Jaccard por buckets evalua; MinHash paga solo con n grande y firma k alta |
| Vacuum por ratio tombstone / TTL FADE | Upstream (ruscadb-txn); el harness ya evicciones por calor |
| Free-threaded / compression.zstd stdlib | Constantes, no O; evaluate el día que `requires-python` sube |

Decision rules (verificados en la investigación): cambios engine=upstream;
cambios cliente Python=our side solo cuando el algoritmo cambia el O, no la
medio constante.

## 4. Referencias (leídas en esta sesión)

- [RaBitQ (ICDE'24)](https://arxiv.org/pdf/2405.12497) ·
  [Extended RaBitQ (SIGMOD'25)](https://dl.acm.org/doi/10.1145/3725413)
- [FAISS v1.14.2 headroom pruning](https://github.com/facebookresearch/faiss/releases/tag/v1.14.2) ·
  [TRIM](https://arxiv.org/abs/2508.17828)
- [Block-Max WAND](https://research.engineering.nyu.edu/~suel/papers/bmw.pdf) ·
  [LazyBM](https://web2.qatar.cmu.edu/~mhhammou/SIGIR_20_LazyBM.pdf) ·
  [SPLATE](https://arxiv.org/html/2404.13950v1)
- [MinHash/LSH dedupe](https://arxiv.org/html/2501.01046v3)
- [VectorChord 0.5 DiskANN+RaBitQ](https://blog.vectorchord.ai/vectorchord-05-new-rabitq-empowered-diskann-index-and-continuous-recall-measurement) ·
  [IISWC 2025 vectordb](https://atlarge-research.com/pdfs/2025-iiswc-vectordb.pdf)
- [Prefix sums cov](https://imoz.jp/scraps/202607_mvar.en.html) ·
  [Chan](https://dl.acm.org/doi/pdf/10.1145/3221269.3223036) ·
  [VN howto rolling](https://dl.acm.org/doi/pdf/10.1145/3221269.3223036)
- [Lehte (FADE vacuum)](https://disc-projects.bu.edu/lethe/) ·
  [Tombstone bloom](https://arxiv.org/html/2502.08832) ·
  [Lethe-FADE](https://arxiv.org/html/2202.04522v2)
- [zstd parquet NVMe tradeoff](https://link.springer.com/article/10.1007/s00778-025-00911-1)
