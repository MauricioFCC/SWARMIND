# ADR-0062: GitHub Actions CI/CD con 3-tier gates

**Fecha**: 2026-08-26
**Estado**: Aceptado
**Decisor**: Coordinator (SWARMIND)
**Categoría**: CI/CD / Calidad

## Contexto

SWARMIND tiene pre-commit hooks (ruff + tests) pero no tiene CI/CD automatizado. Los gates son "recomendados" pero no "bloqueantes":
- Un PR puede merge aunque los tests fallen
- No hay mutation testing automatizado
- No hay regression testing nocturno
- No hay security scanning

El patrón **Pondero CI-for-Agents** (2026) define 3 tiers de gates:

| Tier | Tipo | Timeout | Bloquea merge |
|------|------|---------|---------------|
| T1 | Determinístico | <90s | ✅ |
| T2 | LLM-judge / Mutation | <10min | ✅ |
| T3 | Regression | <60min | ❌ (alert) |

## Decisión

Crear `.github/workflows/ci.yml` con 3 tiers:

### T1 — Determinístico (blocks merge)
- **lint**: `ruff check` → 0 errores
- **type-check**: `mypy` (allow failures temporalmente, ADR-0037)
- **test**: `pytest -x -q` (fail-fast)
- **security**: `pip-audit` (informational)
- **dead-code**: `vulture --min-confidence 80`
- **compile**: `python -m py_compile` en módulos core
- **agents**: validación de frontmatter de agentes

Trigger: push + pull_request
Timeout: 10 min

### T2 — Mutation Testing (PR only)
- **mutation**: `mutmut run` en harness/
- **coverage**: `pytest --cov --cov-fail-under=80`

Trigger: pull_request (no push)
Timeout: 30 min

### T3 — Regression (nightly)
- **regression**: suite completa verbose
- **benchmark**: tests de benchmark si existen

Trigger: schedule (02:00 UTC) + workflow_dispatch
Timeout: 60 min

### Infraestructura
- Python 3.12
- uv@v4 (astral-sh/setup-uv)
- Cache de .venv
- Concurrency group (cancel old runs)
- Permissions: contents read (minimal)

## Consecuencias

### Positivas
- PRs no pueden merge sin tests verdes (T1)
- Mutation testing detecta tests débiles (T2)
- Regression nocturna detecta degradación lenta (T3)
- Security scanning automático
- Status badge para README

### Negativas
- T2 agrega ~10 min a cada PR (mitigado: solo en PR, no en push)
- Mutation testing puede ser flaky (mitigado: retry)
- GitHub Actions tiene 2000 min/mes gratis (suficiente para este proyecto)

### Riesgos
- **Bajo**: T1 es rápido y confiable
- **Medio**: T2 puede fallar por timeout en proyectos grandes (mitigado: solo harness/)
- **Bajo**: T3 es alert-only, no bloquea

## Referencias

- Pondero "CI for Agents: Tiered Eval Gates" (2026)
- GitHub Actions docs: workflows, concurrency, permissions
- mutmut: mutation testing for Python

## Archivos afectados

- `.github/workflows/ci.yml` (nuevo)
