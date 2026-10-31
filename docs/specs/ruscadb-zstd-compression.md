# Spec — Zstd Compression (RuscaDB) en SWARMIND

> Estado: blocked-upstream — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `zstd_compression.md`, `zstd_real.md`, `wal_compression.md`, `alp_compression.md`.

## 1. Objetivo
Reducir el tamano del WAL y de los datos usando compresion Zstd.

## 2. Diseno
- Activar feature `compression` en la DLL.
- Compresion de paginas en reposo.
- ALP compression para series temporales.

## 3. Integracion
- `setup_swarmind.py --features compression`.
- Configurable via env `RUSCADB_COMPRESSION=zstd`.

## 4. Outcome medible
- Tamano del WAL reducido en >= 50%.
- Overhead de compresion < 3%.

## 5. Esfuerzo: 2 dias.
