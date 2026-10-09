# Spec — Gate de evidencia de fix (SpecBench / anti-pintar-verde)

## Outcome medible

Un gate que, dado un fix de agente, verifica con evidencia que (1) existe una
spec, (2) hay un test de reproduccion que FALLABA antes y PASA despues, y
(3) ningun test fue debilitado para pasar (anti-pintar-verde, SpecBench
arXiv:2605.21384).

Criterio de exito: `verify_fix_evidence(...)` retorna `passed=True` solo con
las tres evidencias; `check_test_weakening` detecta aserciones eliminadas o
relajadas en diffs de tests.

## Contexto

SWARMIND ya tiene `cp_spec_gate` (checklist pre-codigo) y `tdd_strict` (fases
RED/GREEN). Falta el eslabon de EVIDENCIA: que el fix traiga prueba de que el
test fallaba antes (failing-first) y de que los tests no se tocaron para
pasar (anti-paint). Sin esto, un agente puede "resolver" editando el test.

## Requisitos funcionales

- FR1: `verify_fix_evidence(spec_path, repro_test, failed_before, passed_after,
  old_test_text, new_test_text)` -> `FixEvidenceReport(passed, reasons)`.
- FR2: `check_test_weakening(old, new)` -> lista de debilitamientos (assert
  eliminado, condicion relajada: `==`->`in`, `>`->`>=`, numero magico cambiado,
  `assert` convertido en comentario).
- FR3: el gate pasa solo si: spec existe y no vacia + repro fallo antes y pasa
  despues + cero debilitamientos.

## Requisitos no funcionales

- NF1: puro y determinista (sin LLM, sin red) para gate T1.
- NF2: falsos positivos ~0 en diffs legitimos (anadir asserts esta permitido).

## Invariantes (tests TDD)

1. Fix valido con spec + repro fail->pass + tests intactos -> passed.
2. Sin spec -> failed con razon "sin-spec".
3. Repro que no fallaba antes -> failed ("sin-fallo-previo").
4. Repro que no pasa despues -> failed ("sigue-fallando").
5. Assert eliminado -> debilitamiento detectado.
6. `==` relajado a `in`, o numero cambiado -> debilitamiento.
7. Anadir asserts nuevos -> NO es debilitamiento.
8. Report incluye razones accionables (WHAT/WHY/WHERE).

## Fuera de alcance

- Ejecutar pytest (el gate recibe resultados, no los produce).
- Juez LLM (eso es T2; esto es T1 determinista).
