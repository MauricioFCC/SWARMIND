# Spec — Time Series en SWARMIND

> Estado: proposed — Dueño: harness/observability — Frontera: 2026-10.
> RuscaDB spec: `time_series.md`, `ts_advanced.md`, `ts_continuous_aggregates.md`,
> `ts_retention.md`, `ts_facade.md`, `timeseries_advanced.md`.

## 1. Objetivo
Usar las capacidades de time series de RuscaDB para analitica temporal de
metricas de agentes (latencia, throughput, error rate).

## 2. Capacidades RuscaDB
- time_bucket, ventanas tumbling/sliding.
- Resampling con relleno.
- percentile, rate, moving_average.
- Downsampling (avg/max/min).
- Continuous aggregates, retention policies.

## 3. Integracion
- Coleccion `agent_metrics` con time series.
- `RuscaDBStore` expone `ts_bucket`, `ts_window`, `ts_rate`.
- Dashboard de observabilidad usa time series.

## 4. Outcome medible
- Metricas temporales persistidas y consultables.
- Downsampling reduce volumen en >= 10x.

## 5. Esfuerzo: 1 semana.
