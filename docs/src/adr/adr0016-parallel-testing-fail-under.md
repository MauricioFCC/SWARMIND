# ADR-0016: Parallel Test Execution & Fail-Under Progresivo

## Estado
**ACEPTADO** — Implementado en commit 2ef685f, pendiente extensión.

## Contexto
El suite de tests creció de 463 a 1068 tests (+605, 231%) en una semana. El tiempo de ejecución pasó de ~35s a ~85s (143% aumento). Sin paralelización, el ciclo de retroalimentación se degrada linealmente con el crecimiento del suite.

Además, `fail_under = 30` en `pyproject.toml` está desactualizado (coverage real: 43.69%), eliminando la protección contra regresiones.

## Decisión

### 1. pytest-xdist para ejecución paralela
- Instalar `pytest-xdist` y `pytest-split` como dependencias dev
- Configurar `-n auto` para usar todos los cores disponibles
- Estimación: 85s → ~22s en CPU 4-core (medido: 3.8x speedup)

### 2. Marcadores slow para categorización
- Tests >1s marcados como `@pytest.mark.slow` (actual: ~10 tests)
- Tests de integración con LanceDB real marcados como `@pytest.mark.integration`
- Por defecto: `pytest -m "not slow"` para CI rápido
- Jobs CI separados: `slow` e `integration` en schedule

### 3. Fail-Under progresivo
```toml
[tool.coverage.report]
fail_under = 44   # Jul 2026: coverage actual + 0.31% buffer
# fail_under = 55  # Next PR: +10%
# fail_under = 70  # Next+1 PR
# fail_under = 80  # Objetivo final
```

### 4. Fixtures optimizadas
- Fixtures de infraestructura pesada (LanceDB) → `scope="session"` con temp dirs aislados
- Fixtures de datos de prueba → `scope="module"` (inmutables)

## Consecuencias
- Positivas: CI 4x más rápido, detección temprana de regresiones, escalabilidad horizontal
- Negativas: Tests con estado compartido pueden fallar en paralelo (require `--pdb` o `-p no:xdist`)
- Mitigación: `xdist_group` para tests que requieren ejecución serial
