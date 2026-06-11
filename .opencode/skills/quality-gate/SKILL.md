---
name: quality-gate
description: "Garantía de calidad: ejecuta gates de calidad pre-commit, diseña estrategias de prueba, validación de cobertura y prevención de regresiones"
version: 3.1.0
project_agnostic: true
inherit:
  - core/base_skill_template.md
  - core/fde_principles.md
variables:
  - PROJECT_NAME
  - TECH_STACK
keywords: [commit, quality gate, pre-commit, test, lint, typecheck, cobertura, coverage, seguridad, refactor, qa, automation, testing]
priority: 10
requires_context: true
token_budget: 2000
---

# QUALITY GATE | {{PROJECT_NAME}}

## CUANDO ACTIVAR
Skill universal. Siempre activo para validar calidad de código pre-commit y diseñar estrategias de prueba. No requiere chequeo de dominio.

⚡ ROL: Quality Gate Engineer • 🏢 DEPARTAMENTO: Aseguramiento de Calidad
🎯 MISIÓN: Garantizar que cada refactor o feature pase todos los gates antes de producción y que las estrategias de prueba cubran adecuadamente la funcionalidad

---

## 📐 PRINCIPIOS DE REFERENCIA

Ver `.opencode/core/base_principles.md` para las 7 categorías (ARQ, SEG, DOC, TST, OPS, CMT, QLT) con 3 niveles de detalle.

---

## 🛡️ GATES DE CALIDAD (ejecutar SIEMPRE post-refactor)

Orden: 1. tests → 2. lint → 3. typecheck → 4. coverage → 5. security (SEG) → 6. language (DOC) → 7. docs 1:1 (DOC) → 8. commit (CMT)

### GATE 1 — Tests
`pytest <test_dir> -v --tb=short` → 0 failed, 0 errors.

### GATE 2 — Lint
`<linter> <src_dir> <test_dir>` → 0 errores.

### GATE 3 — Type Check
`<type_checker> <src_dir>` → 0 errores. Type ignores con justificación.

### GATE 4 — Cobertura
`pytest --cov=<src_dir> --cov-report=term` → Global ≥30%, core ≥80%.

### GATE 5 — Seguridad (base_principles.md SEG)
- `git diff --cached | grep -P "(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{8,}['\"]"` → BLOQUEAR

### GATE 6 — Idioma (base_principles.md DOC)
- Código EN: `git diff --cached | grep -P "def [a-z]+_[a-z]+"` → verificar nombres ingleses
- Docstrings ES: `git diff --cached | grep -P '"""[A-Z]'` → verificar español

### GATE 7 — Docs 1:1 (base_principles.md DOC)
- `git diff --cached --name-only` → si cambia API, docs obligatorio
- Nuevas clases públicas → docstrings actualizados

### GATE 8 — Conventional Commit (base_principles.md CMT)
Formato: `^(feat|fix|docs|style|refactor|test|chore|build|ci)(\(.+\))?: .{1,72}#[0-9]+$`

---

## Estrategia de Pruebas (absorbido de QA Automation)

Para nuevas features, diseña la estrategia de prueba antes de codificar:

| Nivel | % | Herramientas | Propósito |
|-------|---|-------------|-----------|
| Unit | 70% | pytest/unittest | Lógica de negocio aislada |
| Contract | 10% | Pact/schema testing | Boundearies entre servicios |
| Integration | 10% | pytest + mocks | Flujo completo con dependencias mockeadas |
| E2E | 10% | Playwright/Cypress/k6 | Rutas críticas completas |

### Flaky Test Prevention
- Si (test_no_determinista) → Retry con jitter → Si persiste → Quarantine + ticket
- Si (API_inestable) → WireMock/MockServer con contratos versionados
- Si (E2E_lento) → Parallelización + headless + sharding por ruta crítica

## Inner Loop Evaluation (Dev-Time)

| # | Gate | Herramienta | Criterio | Propósito |
|---|------|------------|----------|-----------|
| IL-1 | Lint Rápido | `ruff check --select=E9,F` | 0 errores fatales | Catch syntax/import errors instantly |
| IL-2 | Type Narrow | `mypy --strict --follow-imports=skip` | 0 nuevos errores type | Catch type mismatches pre-commit |
| IL-3 | Test Unitarios | `pytest -x --timeout=30 -m "not slow"` | 0 failed, 0 errors | Fast feedback en <30s |
| IL-4 | Diff Review | Revisar diff estructural | Sin cambios rotos en contratos API | Detectar breaking changes |
| IL-5 | Conventional Commit | Validar mensaje draft | Formato `tipo(scope): descripción` | Preparar commit message |

## Outer Loop Evaluation (CI/Production)

| # | Gate | Herramienta | Criterio | Propósito |
|---|------|------------|----------|-----------|
| OL-1 | Test Full Suite | `pytest -v --tb=long --cov=` | 0 failed, cobertura ≥80% core | Validación completa |
| OL-2 | Lint Completo | `ruff check .` | 0 errores | Code style completo |
| OL-3 | Type Check Full | `mypy --strict` | 0 errores | Type safety |
| OL-4 | Seguridad | `bandit -r .` + secret scan | 0 secrets, 0 altos | Security hardening |
| OL-5 | Performance | `pytest --benchmark-only` (si config) | Sin regresión >5% | Performance regression |
| OL-6 | Integración | Smoke test contra sandbox | Endpoints responden 200 | Integration health |
| OL-7 | Doc Sync | `git diff --name-only` + check docs | API changes have doc updates | Documentation currency |

## Pairwise & Pointwise Evaluation

- **Pairwise**: Comparar candidate vs baseline usando Model-as-a-Judge. Criterios: correctness, efficiency, readability, security.
- **Pointwise**: Evaluar candidate contra rúbrica fija en escala 1-5. Dimensiones: groundedness, clarity, completeness, safety.

Ambos modos generan un score de calidad que se registra en el **Cognition Store**.

---

## 🔄 FLUJO POST-REFACTOR

`Refactor → [GATE 1..8 secuencial] → ✅ COMMIT SEGURO | ↓ ❌ → Devuelve al desarrollador`

---

## ⚠️ DECISIONES TÉCNICAS

- test_fails → block + report + suggest fix
- lint_error → block + show line
- security_leak → block + CRITICAL alert + location
- coverage_below_threshold → warn + allow if core covered
- all_gates_pass → approve + generate conventional message
- test_no_determinista → retry with jitter → quarantine if persists
- E2E_lento → parallelize + headless + sharding

---

## ⚠️ NUNCA

`sleep()` hardcodeado • Aserciones visuales sin baseline • Gatear CI en tests frágiles • Depender de entorno externo sin mock • Ignorar flaky tests (siempre quarantine primero)
