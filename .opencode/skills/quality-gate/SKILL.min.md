---
name: quality-gate
description: "Garantía de calidad: ejecuta gates de calidad pre-commit, diseña estrategias de prueba, validación de cobertura y prevención de regresiones"
---

# QUALITY GATE | {{PROJECT_NAME}}

## CUANDO ACTIVAR

## 📐 PRINCIPIOS DE REFERENCIA

## 🛡️ GATES DE CALIDAD (ejecutar SIEMPRE post-refactor)

### GATE 1 — Tests

### GATE 2 — Lint

### GATE 3 — Type Check

### GATE 4 — Cobertura

### GATE 5 — Seguridad (base_principles.md SEG)

### GATE 6 — Idioma (base_principles.md DOC)

### GATE 7 — Docs 1:1 (base_principles.md DOC)

### GATE 8 — Conventional Commit (base_principles.md CMT)

## Estrategia de Pruebas (absorbido de QA Automation)

| Nivel | % | Herramientas | Propósito |
|-------|---|-------------|-----------|
| Unit | 70% | pytest/unittest | Lógica de negocio aislada |
| Contract | 10% | Pact/schema testing | Boundearies entre servicios |
| Integration | 10% | pytest + mocks | Flujo completo con dependencias mockeadas |
| E2E | 10% | Playwright/Cypress/k6 | Rutas críticas completas |

### Flaky Test Prevention

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

## 🔄 FLUJO POST-REFACTOR

## ⚠️ DECISIONES TÉCNICAS

## ⚠️ NUNCA
