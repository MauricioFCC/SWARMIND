# ADR 0094: Librería Compartida — Crecer `harness/common.py`, No Nueva Librería

## Estado
Aplicado | `short_hash` + `utc_now_iso` + `safe_json_loads` en `harness/common.py` + 6 migraciones | Propietario: @coordinator | Fecha: 2026-09-08

## Contexto
Pregunta: ¿qué tan viable es crear/actualizar librerías propias para eliminar duplicación y mejorar rendimiento? Medición: `sha256().hexdigest()[:N]` en 6 sitios, `datetime.now(UTC)` en 99, `try/except JSON` en 15, `_parse_meta` ×6 en agent_kpi_tracker (+2 vars muertas).

## Decisión
**NO crear librería separada** (packaging/versionado/deploy por cero ganancia runtime; el harness ya se sincroniza como unidad a global+mirrors). **Crecer `harness/common.py`** (ya es la lib compartida: 13+ archivos la usan):
1. `short_hash(content, length)` + `utc_now_iso()` + `safe_json_loads()` con tests.
2. Migrados 6 sitios de hash (artifact_store, cue_ledger ×2, session_snapshot, prompt_cache_builder, behavioral_tracer, got_planner) + `_parse_meta()` + 2 vars muertas eliminadas.

TDD: 4 tests nuevos; suites de módulos migrados verdes (56 kpi, 35 common); ruff 0.

## Consecuencias
### Positivas
- Cero duplicación nueva posible (el linter social es el import).
- Sin costo de packaging ni versionado.

### Negativas
- `common.py` crece (vigilar: si pasa 500L, partir por dominio).

## Alternatives Considered
1. **Paquete PyPI propio**: overhead sin beneficio (el deploy ya distribuye el harness).
2. **Dejar duplicados**: deriva garantizada (ya eran 6 y creciendo).

## Relacionado
- DRY/ARQ, ADR-0091 (fusiones), `harness/common.py`
