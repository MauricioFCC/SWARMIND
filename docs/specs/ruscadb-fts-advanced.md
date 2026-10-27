# Spec — FTS Avanzado (fuzzy, phrase, stemming) en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `fts_advanced.md`, `fts_fuzzy_scoring.md`, `fts_proximity.md`, `fts_prefix.md`.
> Feature RuscaDB: `fts-advanced` (SPEC-0117).

## 1. Objetivo

Aprovechar el FTS avanzado de RuscaDB (fuzzy Levenshtein, phrase matching,
stemming Snowball) para mejorar la recuperacion textual en SWARMIND.

## 2. Capacidades RuscaDB
- Fuzzy matching (Levenshtein) para tolerar typos.
- Phrase matching (secuencia exacta de terminos).
- Stemming Snowball (raices de palabras).
- Proximity search (terminos cercanos).

## 3. Integracion SWARMIND
- Activar feature `fts-advanced` en la DLL (setup_swarmind.py --features fts-advanced).
- `RuscaDBStore.full_text_search`: aceptar modo (exact/fuzzy/phrase/stem).
- `HybridRetriever._sparse_retrieve`: usar stemming para normalizar query.
- Agregar param `fts_mode` a `full_text_search`.

## 4. RQL
```sql
SELECT * FROM t WHERE MATCH(title, 'fox')           -- basico
SELECT * FROM t WHERE MATCH(title, '"quick fox"')   -- phrase
SELECT * FROM t WHERE MATCH(title, 'fx~2')          -- fuzzy (distancia 2)
```

## 5. Outcome medible
- Recall@10 mejora >= 15% en queries con typos.
- Latencia FTS p95 < 20ms.

## 6. Esfuerzo: 3 dias.
