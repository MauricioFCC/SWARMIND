---
name: atdd-spec
domain: testing
version: 1.0.0
project_agnostic: true
description: "Usar cuando se desarrolla una feature con ciclo Spec→Test→Code: especificación de comportamiento primero, tests como prompt+verificación, implementación mínima, refactor. | UPG·NAM·FRS (reglas en base_principles.md)"
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
## Doctrina

En un flujo guiado por LLM, el requisito vive en el chat y se pierde. La spec
añade una capa ligera y acordada: **acuerda ANTES de construir** (patron
OpenSpec: proposal → specs → design → tasks). El test es el contrato de la
feature: define el alcance sin ambiguedad y da al modelo una senal de exito
medible, no una opinion.

## El ciclo Spec→Test→Code→Refactor

### 1. Spec (requerimiento → acceptance criteria)
- Traduce el requerimiento a **acceptance criteria en lenguaje natural** +
  **ejemplos concretos** (entrada → salida esperada).
- Formato OpenSpec: `proposal.md` (por que/cambio), `specs/` (requirements y
  scenarios), `design.md` (enfoque tecnico), `tasks.md` (checklist).
- Sin ambiguedad: cada criterio debe ser comprobable por un test.

### 2. Tests (especificacion ejecutable ANTES del codigo)
- Escribe los tests **antes del codigo**: son la spec en forma ejecutable.
- Un test = un criterio de aceptacion. Nombres descriptivos
  (`test_validate_email_with_invalid_format_returns_false`).
- En Python: pytest; para invariantes usar PBT con `hypothesis` (`@given`).
- Los tests son **tanto prompt como verificacion** para el LLM.

### 3. Code (implementacion minima)
- Implementa **solo lo necesario** para pasar los tests (KISS, YAGNI).
- Docstrings ES obligatorias en toda funcion publica (DOC).
- Sin sobre-ingenieria: si el test no lo exige, no existe.

### 4. Refactor
- Con los tests verdes como red de seguridad, limpia: extrae helpers,
  aplica NAM/TYP/IMM/SOL, elimina duplicacion (DRY).
- Vuelve a ejecutar los tests: el verde debe mantenerse.

## Frontier 2026: tests como prompt+verificacion

Cui 2025 (arXiv:2505.09027, WebApp1K: 1000 challenges, 20 dominios,
19 frontier models) demuestra en TDD tasks que:

- **Los tests funcionan como prompt Y como verificacion**: el LLM recibe los
  tests y debe implementar la funcionalidad directamente a partir de ellos,
  sin descripcion en lenguaje natural.
- **Instruction following > habilidad general**: la capacidad de seguir
  instrucciones y el in-context learning diferencian el exito en TDD mas que
  la pericia general de programacion o el conocimiento de pretraining
  (modelos con bajo exito TDD tienen alto exito en tareas TLD hermanas).
- **Bottleneck: instruction loss en prompts largos** — mas test cases y
  prompts mas extensos **degradan** la performance (TDD prompting paradox).

### Consecuencia operativa (progressive disclosure)

- **Prompts CORTOS y progresivos**: no vuelques la spec completa de golpe.
  Primero contexto limpio (spec resumida + tests), despues implementa.
- Instrucciones largas = ruido: degradan el instruction following.
- Un test a la vez en loops complejos (patron Evaluator-Optimizer): fallo →
  ajuste → repite.

## Red-Green-Refactor disciplinado

1. **RED (evidencia)**: el test debe FALLAR primero, con el motivo correcto
   (assertion, no error de import). Si no falla, el test no prueba nada.
2. **GREEN**: implementacion minima que lo pasa.
3. **REFACTOR**: limpiar sin romper verde.
- Prohibido: parches cosmeticos a tests para "pintar verde" (el test debe
  poder fallar — doctrina VER/guardian).

## Model routing (TKN)

- **Spec**: modelos de alto razonamiento (frontier) — la traduccion
  requerimiento→criterios es donde se juega la calidad.
- **Implementacion repetitiva**: modelos small — tareas mecánicas de bajo
  costo (Token Economics: small para simple, frontier para complejo).

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

## Referencias

- OpenSpec-ATDD — spec-driven development con TDD/BDD workflows guiados por
  IA (github.com/zarzouram/OpenSpec-ATDD).
- Cui, Y. (2025). "Tests as Prompt: A Test-Driven-Development Benchmark for
  LLM Code Generation" — arXiv:2505.09027.
- Beck, K. (2022). "Test-Driven Development: By Example" — origen del ciclo
  red-green-refactor.