---
name: atdd-spec
domain: testing
description: "Usar cuando se desarrolla una feature con ciclo Spec→Test→Code: especificación de comportamiento primero, tests como prompt+verificación, implementación mínima, refactor. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
version: 1.0.0
project_agnostic: true
---

# ATDD-Spec (min)

Adaptacion de OpenSpec-ATDD (spec-driven + TDD/BDD guiado por IA) al stack SWARMIND.

## Ciclo
1. **Spec**: requerimiento → acceptance criteria + ejemplos concretos (proposal/specs/design/tasks)
2. **Tests**: escribir tests ANTES del codigo (spec ejecutable; 1 test = 1 criterio)
3. **Code**: implementacion minima para pasar (KISS, docstrings ES)
4. **Refactor**: limpiar con tests verdes como red de seguridad

## Reglas
- Tests = prompt + verificacion (Cui 2025, arXiv:2505.09027): el LLM implementa desde los tests; instruction following > habilidad general
- TDD prompting paradox: prompts largos degradan (instruction loss) → prompts CORTOS y progresivos (progressive disclosure)
- Red-Green-Refactor disciplinado: el test DEBE fallar primero (evidencia RED)
- Model routing (TKN): frontier para spec, small para implementacion repetitiva
- Prohibido parchear tests para "pintar verde"

## Checklist
- [ ] Acceptance criteria + ejemplos
- [ ] Tests ANTES del codigo
- [ ] Evidencia RED (falla con motivo correcto)
- [ ] Implementacion minima → GREEN
- [ ] Refactor sin romper verde
- [ ] pytest + ruff pasando (VER, evidencia mostrada)