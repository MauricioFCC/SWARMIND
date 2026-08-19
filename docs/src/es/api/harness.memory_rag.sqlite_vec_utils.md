<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->

# API — `harness.memory_rag.sqlite_vec_utils`

sqlite\_vec\_utils — Utilidades, excepciones y DTOs para SQLiteVecAdapter.

## `SQLiteVecError(Exception)`

Error base del adaptador SQLiteVec.

## `CollectionNotFoundError(SQLiteVecError)`

La coleccion solicitada no existe.

## `DimensionMismatchError(SQLiteVecError)`

La dimension del vector no coincide con la coleccion.

## `VectorNotFoundError(SQLiteVecError)`

El vector solicitado no existe en la coleccion.

## `VectorRecord`

Registro individual de vector con metadatos.

## `CollectionMeta`

Metadatos de una coleccion de vectores.
