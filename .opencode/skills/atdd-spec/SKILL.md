---
name: atdd-spec
domain: testing
version: 1.0.0
project_agnostic: true
description: "Usar cuando se desarrolla una feature con ciclo Spec→Test→Code: especificación de comportamiento primero, tests como prompt+verificación, implementación mínima, refactor. Alcance: ciclo Spec->Test->Code; para disciplina pre-merge ver agent-rigor. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Python 3.12+; pytest; aplicable a cualquier lenguaje con test runner'
---

# ATDD-Spec | Spec→Test→Code guiado por IA

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **Test-first practitioner senior (10+ anos): specs como contratos ejecutables, ATDD/TDD clasico y tests que no pasan por construccion.**
- **CANON** (estudiar ANTES de generar, regla RSF):
  - Growing Object-Oriented Software (GOOS) — https://www.gocd.org
  - Test-Driven Development — https://martinfowler.com/bliki/TestDrivenDevelopment.html
- **ANTI-HEDGING**: Especifica el comportamiento observable ANTES del test; un criterio por spec.

## Doctrina (esencial)

El requisito vive en el chat y se pierde; la spec es una capa ligera acordada
(**acuerda ANTES de construir**: proposal → specs → design → tasks). El test es
el contrato de la feature: alcance sin ambiguedad + senal de exito medible
(tests como prompt Y como verificacion). Detalle en
[`references/ciclo-spec-test-code.md`](references/ciclo-spec-test-code.md).

## El ciclo Spec→Test→Code→Refactor

1. **Spec**: requerimiento → acceptance criteria en lenguaje natural + ejemplos
   concretos (entrada → salida esperada); cada criterio comprobable por un test.
2. **Tests** (ANTES del codigo): 1 test = 1 criterio; nombres descriptivos;
   pytest; PBT con `hypothesis` para invariantes. Los tests son prompt + verificacion.
3. **Code**: implementacion minima para pasar (KISS/YAGNI); docstrings ES.
4. **Refactor**: con tests verdes, limpiar (NAM/TYP/IMM/SOL, DRY) sin romper verde.

## Red-Green-Refactor disciplinado

1. **RED (evidencia)**: el test debe FALLAR primero, con el motivo correcto
   (assertion, no error de import). Si no falla, el test no prueba nada.
2. **GREEN**: implementacion minima que lo pasa.
3. **REFACTOR**: limpiar sin romper verde.
- Prohibido: parches cosmeticos a tests para "pintar verde" (doctrina VER/guardian).

## Checklist ATDD

- [ ] Acceptance criteria en lenguaje natural + ejemplos concretos
- [ ] Spec aprobada ANTES de escribir codigo (proposal/specs/design/tasks)
- [ ] Tests escritos ANTES del codigo (1 test = 1 criterio)
- [ ] Evidencia RED: el test falla con el motivo correcto
- [ ] Implementacion minima (KISS) → GREEN
- [ ] Refactor con tests verdes, sin parches cosmeticos
- [ ] Prompt corto y progresivo (progressive disclosure, no volcar spec entera)
- [ ] Modelo small para implementacion repetitiva, frontier para spec
- [ ] Docstrings ES en codigo nuevo
- [ ] Evidencia mostrada: pytest + ruff pasando (VER)

## Anti-patrones (prohibidos)

- Implementar antes de escribir el test (rompe el ciclo).
- Spec en lenguaje vago sin ejemplos concretos.
- Prompts larguisimos con toda la spec (instruction loss — Cui 2025).
- Test que no puede fallar (parche cosmetico).
- Over-engineering en Code (implementar mas de lo que el test exige).
- Refactor sin tests verdes previos.

## Ejemplo trabajado

```
# 1) Spec: "POST /users rechaza email invalido con 422"
# 2) Test ANTES del codigo -> RED
def test_create_user_with_invalid_email_returns_422(client):
    assert client.post("/users", json={"email": "sin-arroba"}).status_code == 422
$ pytest -q   # FAILED (404) -> RED con motivo correcto
# 3) implementacion minima -> GREEN - 4) refactor con tests verdes
```

## Referencias (bajo demanda)

> Migrado a `references/` por política "focused beats comprehensive" (SkillsBench 2026).
> Cargar solo cuando la tarea requiera el detalle del ciclo o la frontera.

- [Ciclo Spec→Test→Code completo](references/ciclo-spec-test-code.md) — doctrina OpenSpec, los 4 pasos en detalle.
- [Frontier 2026 — tests como prompt+verificación](references/frontier-2026.md) — Cui 2025 (arXiv:2505.09027), instruction loss, model routing.
