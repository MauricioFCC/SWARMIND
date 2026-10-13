> Migrado a references/ por politica focused beats comprehensive - SkillsBench 2026.

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
