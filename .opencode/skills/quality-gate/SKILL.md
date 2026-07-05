---
name: quality-gate
description: Gate de calidad para validar código, tests y seguridad antes de commit en Hermes
version: 1.0.0
domain: quality
trigger: "validar", "test", "cobertura", "calidad", "seguridad", "QA"
priority: 10
token_budget: 2000
requires_context: false
---

# QUALITY GATE | Hermes Memory Projects

## CUCUANDO ACTIVAR
Antes de cualquier commit o merge. Valida: sintaxis, tests, cobertura, seguridad.

## CHECKLIST OBLIGATORIO PRE-COMMIT

### 🧪 Testing (Mínimo 80% cobertura)
- [ ] Tests unitarios para funciones <50 líneas
- [ ] Tests de integración para boundaries
- [ ] Tests de edge cases (inputs vacíos, null, fuera de rango)
- [ ] Tests de error handling (timeouts, exceptions)

### 🔐 Seguridad
- [ ] Sin `OPENAI_API_KEY` hardcodeado
- [ ] Validación de inputs en funciones públicas
- [ ] SBOM actualizado si hay dependencias nuevas
- [ ] No expone información sensible en logs

### 📐 Calidad de Código
- [ ] Funciones ≤ 50 líneas
- [ ] Nesting ≤ 3 niveles
- [ ] Tipado estricto activado (`mypy --strict`)
- [ ] DRY: sin duplicación de lógica
- [ ] SRP: cada módulo una responsabilidad

### 🏗️ Arquitectura
- [ ] Contratos claros (schemas, interfaces)
- [ ] Cardinalidad de estados mínima
- [ ] Fallbacks documentados
- [ ] Autocontenido (imports, tipos)

## COMANDOS DE VALIDACIÓN

```bash
# Sintaxis
python -m py_compile scripts/*.py

# Tests
python -m pytest tests/ -v --cov=scripts

# Tipado
mypy scripts/ --strict

# Estilo
ruff check scripts/
```

## LLM-as-Judge EVALUACIÓN (1-5)

| Dimensión | Score |
|-----------|-------|
| Corrección | ? |
| Legibilidad | ? |
| Robustez | ? |
| Eficiencia | ? |
| Mantenibilidad | ? |

**Regla**: si < 4 en cualquier dimensión, NO pasa el gate.

## RESPUESTA
Lista todos los items fallidos y propone refactorización inmediata. Incluye:
- Qué test faltó
- Qué línea rompe el principio
- Qué security gap existe