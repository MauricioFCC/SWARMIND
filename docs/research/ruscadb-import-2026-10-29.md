# Importacion de RuscaDB actualizado (Ola 14) — 2026-10-29

> Verificacion post-import del repo `RuscaDB` (commit `dc640fc`, Ola 14).

## 1. Que trajo la actualizacion

8 modulos **reales** (no stubs) segun el gap register de RuscaDB:

| Modulo | Spec | Madurez | Relevancia para SWARMIND |
|---|---|---|---|
| PageChecksum (CRC-32C) | SPEC-0167 | real | Integridad operacional de backups/WAL |
| SsiTracker | SPEC-0170 | real | SSI para consistencia multi-agente |
| RabitqQuantizer (1-bit) | SPEC-0171 | real | Cuantizacion de embeddings (4-8x memoria) |
| LearnedIndex (PGM) | SPEC-0174 | real | Interno (lookups) |
| AlpCompressor | SPEC-0175 | real | Interno (columnar) |
| FastLanes | SPEC-0176 | real | Interno (bit-packing) |
| GorillaTs | SPEC-0178 | real | Compresion de series temporales |
| CrdtSyncReal (LWW + reloj vectorial) | SPEC-0179 | real | Sync federado entre proyectos |

Stubs (no listos): RQL (SPEC-0161..0165), PreparedStmtReal, SegmentedWal, MvccGcReal, AcornSearch, PersistentHnsw, BlockMaxWand. Placeholder: MlKem.

## 2. Verificacion del FFI (actualizado)

- `crates/ruscadb-ffi/src/lib.rs` expone **29 funciones**: 13 base + 16 extendidas.
- Las 14 funciones extendidas que SWARMIND usa (time travel, encryption, create_index,
  update/delete/get, blobs, integrity, backup, last_lsn, explain, open_opts, open_encrypted)
  fueron **re-aplicadas** al arbol actual (commit `0060119`) y el DLL se recompilo
  (`target/debug/ruscadb_ffi.dll`, 4.92 MB).
- **Ninguno** de los 8 modulos nuevos (RaBitQ, Gorilla, Ssi, etc.) esta expuesto via C-ABI.

## 3. Conclusion: que se debe cablear

**Nada es cableable hoy directamente**, porque los modulos nuevos viven dentro del crate Rust y no cruzan el FFI. SWARMIND solo puede consumir lo que el ABI expone.

Prioridad para futuras olas (cuando RuscaDB los exponga):
1. **RaBitQ** → `ruscadb-ivf-pq.md` (proposed): cuantizacion 1-bit de embeddings, recall@10 >= 0.90. Mayor ROI para memoria.
2. **GorillaTs** → `ruscadb-timeseries.md`: compresion de metricas de agentes.
3. **SsiTracker** → consistencia fuerte multi-agente (SWARMIND tiene fan-out concurrente).
4. **CrdtSyncReal** → `mcp_project_bridge` / federated memory entre proyectos.
5. **PageChecksum** → verificacion de backups (`integrity()` ya expuesto).

## 4. Accion recomendada (actualizada)

- Las extensiones del FFI ya estan re-aplicadas y commiteadas (`0060119`) en el repo RuscaDB;
  el DLL se recompilo y SWARMIND lo importo (14/14 capacidades `True`).
- **Esperar** a que RuscaDB exponga RaBitQ/Gorilla/Ssi/CRDT via FFI (o extenderlo nosotros)
  antes de cablear en SWARMIND.
- El spec `ruscadb-ivf-pq.md` sigue `proposed`; no iniciar hasta que el FFI lo soporte.

## 5. Estado actual de SWARMIND (post-import)

- DLL actual (4.92 MB) intacta y funcional: 14/14 capacidades `True`.
- `capabilities()` reporta todo disponible.
- Tests `test_ruscadb_store.py`: 11 passed.
- No se requiere cambio de codigo adicional en SWARMIND en este ciclo.
