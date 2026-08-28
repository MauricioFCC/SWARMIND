# ADR-0063: Failure Registry (Socratic-SWE pattern)

**Fecha**: 2026-08-26
**Estado**: Aceptado
**Decisor**: Coordinator (SWARMIND)
**Categoría**: Aprendizaje / Evolución

## Contexto

SWARMIND tiene un `cognition_store` para lecciones y un `evolve` skill para auto-mejora, pero no tienen un registro estructurado de FALLOS. Cuando algo falla:

1. Se corrige y se olvida
2. El mismo error puede repetirse en otra máquina o contexto
3. No hay métricas de qué tipos de fallos son más comunes
4. El evolve loop no tiene datos de entrenamiento para mejorar skills

El paper **Socratic-SWE** (Qu 2026) demuestra que distilar failure traces en skills mejora +7.80 puntos en SWE-bench después de 3 iteraciones. El patrón es:

```
traces → failure registry → skill extraction → targeted tasks → new traces
```

## Decisión

Crear `harness/failure_registry/__init__.py` con:

### Data model
- `FailureRecord` (frozen dataclass, IMM): id, timestamp, task, failure_type, error_msg, root_cause, resolution, skill_derived, severity, file_path, function_name, tags
- `FailureType` (Enum): runtime, test, lint, security, performance, architecture, deploy, config
- `Severity` (Enum): low, medium, high, critical

### Persistence
- Formato JSONL (append-only, una línea por registro)
- Path: `harness/db/failures.jsonl` (gitignored, datos runtime)
- Thread-safe-ish (append mode)

### Queries
- `get_recent(n)`: N fallos más recientes
- `get_by_type(type)`: filtrar por categoría
- `get_by_severity(level)`: filtrar por severidad
- `get_unresolved()`: fallos pendientes (resolution == "pending")
- `get_skills_derived()`: nombres de skills extraídos (deduplicados)
- `stats()`: agregaciones para dashboards

### Integration con evolve
- Evolve loop lee `failure_registry.stats()` para identificar gaps de capability
- Skills derivados se registran en `skill_derived` field
- El loop puede generar tareas dirigidas basadas en fallos recurrentes

## Consecuencias

### Positivas
- Cada fallo se captura con root cause y resolution (ERR principle)
- Métricas de fallos para dashboards y alertas
- Evolve loop tiene datos de entrenamiento estructurados
- Skills derivados se deduplican automáticamente
- Formato JSONL es portable y grep-eable

### Negativas
- Overhead de registro: ~2s por fallo (aceptable)
- Requiere que los agentes utilicen el registry (adopción gradual)
- Datos voluminosos a largo plazo (mitigado: gitignore + rotación futura)

### Riesgos
- **Bajo**: append-only, no destructivo
- **Bajo**: fallback a logger si disco falla

## Referencias

- Qu et al. "Socratic-SWE: Self-Evolving Coding Agents via Trace-Derived Agent Skills" (2026)
- SWARMIND FAIL principle (base_principles.md v2.7.0)
- Harness DB conventions (harness/db/ gitignored)

## Archivos afectados

- `harness/failure_registry/__init__.py` (nuevo)
- `harness/tests/test_failure_registry.py` (nuevo, 21 tests)
- `.gitignore` (+`harness/db/failures.jsonl`)
